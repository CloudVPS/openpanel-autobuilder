from __future__ import with_statement # for python 2.5 compat

import os
import re
import subprocess

import shutil
import tempfile # Building is done in a temporary folder
import xml.etree.ElementTree as ET # to parse hg log output

from mx.DateTime.ISO import ParseDateTimeUTC
import mx.DateTime

from collections import defaultdict

import build # import self. Need this to determine own path

class Build:
	tmpbasedir="/tmp/"
	findsource  = re.compile('^Source:\s*(?P<sourcename>.*)$', re.IGNORECASE | re.MULTILINE)
	findversion = re.compile('^[-a-z0-9]+ \s+ \( (?P<version> [^)]+ ) \)', re.IGNORECASE | re.X)
	findhgtags  = re.compile('^(?P<tagname> [-a-z0-9.]+ ) \s+ (?P<rev>\d+) : [a-f0-9]+ $', re.IGNORECASE | re.X | re.MULTILINE)

	tmpdir = None # Build location
	sourcename = None # Name of the source package
	version = None
	versions = None
	dscpath = None
	lasttag = None
	buildtag = None

	def __init__( self, hgurl ):
		self.hgurl = hgurl

	
	def __del__( self ):
		self.CleanUp()


	def CleanUp( self ):
		# remove the tmp directory
		if self.tmpdir:
			#shutil.rmtree( self.tmpdir )
			self.tmpdir = None
			

	def Clone( self, force = False, tip = False ):
		''' Create a hg checkout in a temporary folder, if none is available or force '''
		if force:
			self.CleanUp()
			
		if self.tmpdir == None:
			# find a nice place to put everything
			self.tmpdir = tempfile.mkdtemp( dir=self.tmpbasedir, prefix="bld" )
			hgdir = self.tmpdir + "/hg"
	

			# perform the checkout
			subprocess.check_call( ["hg", "clone", "--noupdate", self.hgurl, hgdir] )
			
			# determine the latest tag
			c = subprocess.Popen( ["hg", "tags" ], cwd=hgdir, stdout=subprocess.PIPE )
			taglist = c.communicate()[0]
			
			tiprev = 0
			
			for match in self.findhgtags.finditer( taglist ):
				if match.group("tagname") != 'tip':
					self.lasttag = match.group("tagname")
					break
				else:
					tiprev = long(match.group("rev"))

			if tip: #checking out the tip version to build
				subprocess.check_call( ["hg", "update", "--clean"], cwd=hgdir )
				self.buildtag = (self.lasttag or "0.0.0") + "." + str(tiprev)
			elif self.lasttag: # checking out the last tag
				subprocess.check_call( ["hg", "update", "--clean", self.lasttag], cwd=hgdir )
				self.buildtag = self.lasttag
			else: # No tags available, checking out the tip
				subprocess.check_call( ["hg", "update", "--clean"], cwd=hgdir )
				self.buildtag = "0.0.00." + str(tiprev)

		print "Buildtag =%s/%s" % (self.buildtag,self.lasttag)


	def GetBuildTag(self):
		return self.buildtag
	

	def GetSourceName( self ):
		''' Determine the name for the source package, and return it '''
		if not self.sourcename:
			self.Clone()
			with open( self.tmpdir + "/hg/debian/control") as f:
				match = Build.findsource.search( f.read() )
				self.sourcename = match.group("sourcename")
		return self.sourcename


	def GenerateChangelog( self ):
		if self.versions == None:
			self.Clone()
			sourcename = self.GetSourceName()

			stylepath = os.path.join( os.path.dirname(build.__file__) , "mercurial_xml_style" )

			# Request the changelog from mercurial
			c = subprocess.Popen( ["hg", "log", "--follow", "--style", stylepath], cwd=self.tmpdir + "/hg" , stdout=subprocess.PIPE)
			xmllog = c.communicate()[0]

			# work around a bug in mercurial 1.0.1, which ignores the footer declaration from the style
			if xmllog.find( "</log>" ) == -1:
				xmllog += "</log>"
		
			etlog = ET.fromstring( xmllog )
		
			tagend=None
			taghead=None
			anychanges=False
			currentversion=None
		
			self.versions = defaultdict( ChangelogVersion )

			for logentry in etlog:
				if logentry.find("tag") != None:

					version = logentry.find("tag").text
				
					currentversion = self.versions[version]
					currentversion.sourcename = sourcename
					currentversion.description = version
					if not currentversion.author:
						currentversion.author = "%s <%s>" % ( logentry.find("author").text, logentry.find("author").attrib["email"] )					
					if not currentversion.date:
						currentversion.date = ParseDateTimeUTC(logentry.find("date").text)

				msg = logentry.find("msg").text
				tag = _regex_tagging_message.match(msg)
				if tag:
					# This is a "Added tag <version> for changeset <hash>" message.
					# Use the author and date for the specified version
					taggedversion = self.versions[ tag.group("version") ]
					taggedversion.author = "%s <%s>" % ( logentry.find("author").text, logentry.find("author").attrib["email"] )								
					taggedversion.date = ParseDateTimeUTC(logentry.find("date").text)
				else:
					# this is a regular changelog item. Add it to the message
					currentversion.messages.append( msg )
				
		return self.versions
		
		
	def WriteVersion( self, distributions=[] ):
		versions = self.GenerateChangelog()
		
		# determine last version in changelog
		lastchangelogversion = '0.0.0'
		
		tail = ''
		try:
			with open( self.tmpdir + "/hg/debian/changelog") as f:
				tail = f.read()
				match = Build.findversion.search( tail )
				if match:
					lastchangelogversion = match.group("version")
		except:
			pass

		with open( self.tmpdir + "/hg/debian/changelog", 'w') as f:
		
			nversions = 0
			 # FIXME: need to use version compare, otherwise 1.15.0 will sort before 1.2.0
			for version in sorted( versions, reverse=True ):
				if version > lastchangelogversion and versions[version].HasChanges():
					if version == 'tip':
						versions[version].description = self.buildtag

					f.write( versions[version].GetDebianFormatted( distributions=distributions ) )
					nversions += 1
			
			if nversions == 0 and versions[self.buildtag]:
				f.write( versions[self.buildtag].GetDebianFormatted( distributions=distributions ) )
			else:
				self.buildtag = lastchangelogversion
			
			f.write(tail)
		
		# write version.id with the tag to be built
		with open( self.tmpdir + "/hg/version.id", 'w') as f:
			f.write( self.buildtag )
	
							
	def BuildSource( self, distributions=[] ):
		if not self.dscpath:
			self.WriteVersion( distributions=distributions )
			
			environ = {}
			environ.update( os.environ )
			environ["DEBFULLNAME"]="OpenPanel packager"
			environ["DEBEMAIL"]= "packages@openpanel.com"
			
			print len(environ)
			
			c = subprocess.Popen( 
				["dpkg-buildpackage", 
					"-S", # Source build
					"-i", # use default file ignores
					"-I", # use default dir ignores
					"-d",  # ignore build-dependencies
					"-k4EAC69B9",  # use gpg key for OpenPanel packager <packages@openpanel.com>
					"-epackages@openpanel.com",
				], 
				env=environ,
				cwd=self.tmpdir + "/hg")
				
			c.wait()
			
			self.dscpath = "%s/%s_%s.dsc" % (self.tmpdir, self.GetSourceName(), self.buildtag)
			
		return self.dscpath
		
	
	def Build( self, distribution, architecture, binary_only=False, repository=None ):
		dscpath = self.BuildSource()

		if binary_only:
			c = subprocess.Popen( 
				["pbuilder", 
					"build",
					"--basetgz","/var/cache/pbuilder/%s-%s.tgz" % (distribution,architecture) ,
					"--buildresult", self.tmpdir , 
					"--binary-arch",
					dscpath
				])
		else:
			c = subprocess.Popen( 
				["pbuilder", 
					"build",
					"--basetgz","/var/cache/pbuilder/%s-%s.tgz" % (distribution,architecture) ,
					"--buildresult", self.tmpdir , 
					dscpath
				])
			
		c.wait()
		
		changesfile = "%s/%s_%s_%s.changes" % (self.tmpdir, self.GetSourceName(), self.buildtag, architecture )
		
		if repository:
			c = subprocess.Popen( 
				["reprepro", 
					"--waitforlock", "12",
					"--basedir", repository,
					"include", distribution , changesfile,
				])
			c.wait()		


class ChangelogVersion:
	description = ""
	messages = None
	date = None
	sourcename = None
	author = None

	
	def __init__(self):
		self.messages = []
		
		
	def HasChanges( self ):
		return len( self.messages ) > 0
	
	
	def GetDebianFormatted( self, distributions, urgency="Low", overrideauthor=None ):
	
	
		result = "%s (%s) %s; urgency=%s\n" % (self.sourcename, self.description, " ".join(distributions), urgency)
		
		for msg in self.messages:
			newmsg = self._rewriteEntry(msg)
			if newmsg:
				result += "  * %s\n" % newmsg.replace("\n","\n    ")
			
		result += " -- %s  %s\n\n" % ( overrideauthor or self.author, self.date.strftime("%a, %d %B %Y %H:%M:%S %z") )
		return result
		

	def _rewriteEntry( self, msg ):
		''' helper function to rewrite the log message to be used in a debian changelog '''
		# remove bug references, as they could interfere with the debiab BTS
		msg = _regex_bt_ref.sub( "", msg )
		# style: remove trailing period
		msg = _regex_trailing_period.sub( "", msg )

		# Drop short one-word messages
		if _regex_short_message.match( msg ):
			return ""
	
		return msg


_regex_tagging_message = re.compile("Added tag (?P<version>.*) for changeset [a-z0-9]{12}")
_regex_short_message = re.compile("^[a-z]{0,12}$", re.I)
_regex_bt_ref = re.compile("(Refs|Closes|Resolves|Mantis|) \s* (bug)? \s* \# \d+ \s* \.?", re.I | re.X)
_regex_trailing_period = re.compile("\s*\.\s*$")


	
