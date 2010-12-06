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
	findsource = re.compile('^Source:\s*(?P<sourcename>.*)$', re.IGNORECASE | re.MULTILINE)
	findversion = re.compile('^[-a-z0-9]+ \s+ \( (?P<version> [^)]+ ) \)', re.IGNORECASE | re.X)


	def __init__( self, hgurl ):
		self.hgurl = hgurl
		self.tmpdir = None
		self.sourcename = None
		self.version = None
		self.dscpath = None

	
	def __del__( self ):
		self.CleanUp()


	def CleanUp( self ):
		# remove the tmp directory
		if self.tmpdir:
			shutil.rmtree( self.tmpdir )
			self.tmpdir = None
			

	def Clone( self, force = False ):
		''' Create a hg checkout in a temporary folder, if none is available or force '''
		if force:
			self.CleanUp()
			
		if self.tmpdir == None:
			# find a nice place to put everything
			self.tmpdir = tempfile.mkdtemp( dir=self.tmpbasedir, prefix="bld" )

			# perform the checkout
			subprocess.check_call( ["hg", "clone", self.hgurl, self.tmpdir + "/hg"] )

			
	def GetSourceName( self ):
		''' Determine the name for the source package, and return it '''
		if not self.sourcename:
			self.Clone()
			with open( self.tmpdir + "/hg/debian/control") as f:
				match = Build.findsource.search( f.read() )
				self.sourcename = match.group("sourcename")
		return self.sourcename


	def GenerateChangelog( self ):
		self.Clone()
		sourcename = self.GetSourceName()

		stylepath = os.path.join( os.path.dirname(build.__file__) , "mercurial_xml_style" )

		# Request the changelog from mercurial
		c = subprocess.Popen( ["hg", "log", "--style", stylepath], cwd=self.tmpdir + "/hg" , stdout=subprocess.PIPE)
		xmllog = c.communicate()[0]
		
		etlog = ET.fromstring( xmllog )
		
		tagend=None
		taghead=None
		anychanges=False
		currentversion=None
		
		versions = defaultdict( ChangelogVersion )

		for logentry in etlog:
			if logentry.find("tag") != None:

				version = logentry.find("tag").text
				
				currentversion = versions[version]
				currentversion.sourcename = sourcename
				currentversion.description = version
				if not currentversion.author:
					currentversion.author = logentry.find("author").text + " <" + logentry.find("author").attrib["email"] + ">"					
				if not currentversion.date:
					currentversion.date = ParseDateTimeUTC(logentry.find("date").text)

			msg = logentry.find("msg").text
			tag = _regex_tagging_message.match(msg)
			if tag:
				# This is a "Added tag <version> for changeset <hash>" message.
				# Use the author and date for the specified version
				versions[ tag.group("version") ].author = logentry.find("author").text + " <" + logentry.find("author").attrib["email"] + ">"					
				versions[ tag.group("version") ].date = ParseDateTimeUTC(logentry.find("date").text)
			else:
				# this is a regular changelog item. Add it to the message
				currentversion.messages.append( msg )
				
		return versions
		
		
	def BumpVersion( self, rewrite_changelog=False ):
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
			
		# determine last version in HG
		lastversion = lastchangelogversion
		
		for version in versions:
			if version > lastversion and version != 'tip':
				lastversion = version

		major,minor,patch = lastversion.split('.')
		# strip the build until the first non-numeric char		
		for i in range(0,len(patch)-1):
			if not patch[i].isdigit():
				patch = patch[0:i]

		newver = major + "." + minor + "." + str(long(patch)+1)
		
		if 'tip' in versions:
			versions['tip'].description = newver
			versions[newver] = versions['tip']
			del versions['tip']
		else:
			version[newver].description = newver
			version[newver].date = DateTime.now()
			version[newver].author = "OpenPanel packager <packages@openpanel.com>"
			version[newver].sourcename = self.GetSourceName()

		with open( self.tmpdir + "/hg/debian/changelog", 'w') as f:
			for version in sorted( versions, reverse=True ):
				if version > lastchangelogversion:
					f.write( versions[version].GetDebianFormatted() )
			f.write(tail)
			
		# perform the checkout
		c = subprocess.Popen( ["hg", "tag", newver], cwd=self.tmpdir + "/hg")
		c.wait()
		
		return newver
		
		
	def NeedsBuild( self ):
		changes = self.GenerateChangelog()
		return ('tip' in changes) and changes['tip'].HasChanges()
							
							
	def BuildSource( self ):
		if not self.dscpath:
			newver = self.BumpVersion()
			c = subprocess.Popen( 
				["dpkg-buildpackage", 
					"-S", # Source build
					"-i", # use default file ignores
					"-I", # use default dir ignores
					"-d",  # ignore build-dependencies
					"-k4EAC69B9",  # use gpg key for OpenPanel packager <packages@openpanel.com>
					"-epackages@openpanel.com",
				], 
				env={
					"PATH": os.environ['PATH'],
					"HOME": os.environ['HOME'],
					"DEBFULLNAME": "OpenPanel packager",
					"DEBEMAIL": "packages@openpanel.com",
				},
				cwd=self.tmpdir + "/hg")
			c.wait()
			self.dscpath = "%s/%s_%s.dsc" % (self.tmpdir, self.GetSourceName(), newver)
			
		return self.dscpath
	
	def Build( self, distribution, architecture ):
		dscpath = self.BuildSource()

		c = subprocess.Popen( 
			["pbuilder", 
				"build",
				"--basetgz","/var/cache/pbuilder/%s-%s.tgz" % (distribution,architecture) ,
				dscpath
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
	
	
	def GetDebianFormatted( self, distributions = "stable", urgency="Low", overrideauthor=None ):
		result = "%s (%s) %s; urgency=%s\n" % (self.sourcename, self.description, distributions, urgency)
		
		for msg in self.messages:
			newmsg = self._rewriteEntry(msg)
			if newmsg:
				result += "  * %s\n" % newmsg.replace("\n","\n    ")
			
		result += " -- %s  %s\n\n" % ( overrideauthor or self.author, self.date.strftime("%a, %d %B %Y %H:%M:%S %z") )
		return result
		

	def _rewriteEntry( self, msg ):
		''' helper function to rewrite the log message to be used in a debian changelog '''
		# Drop short one-word messages
		if _regex_short_message.match( msg ):
			return ""
	
		# remove bug references, as they could interfere with the debiab BTS
		msg = _regex_bt_ref.sub( "", msg )
		# style: remove trailing period
		msg = _regex_trailing_period.sub( "", msg )
	
		return msg


_regex_tagging_message = re.compile("Added tag (?P<version>.*) for changeset [a-z0-9]{12}")
_regex_short_message = re.compile("^[a-z]{0,12}$", re.I)
_regex_bt_ref = re.compile("(Refs|Closes|Resolves|Mantis|) \s* (bug)? \s* \# \d+ \s* \.?", re.I | re.X)
_regex_trailing_period = re.compile("\s*\.\s*$")


	
