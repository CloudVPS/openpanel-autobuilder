
import tempfile
import shutil
import os
import subprocess
import re
from xml.dom import minidom  
import xml.etree.ElementTree as ET
from mx.DateTime.ISO import ParseDateTimeUTC
from datetime import datetime
from collections import defaultdict

class Build:
	tmpbasedir="/tmp/"
	findsource = re.compile('^Source:\s*(?P<sourcename>.*)$', re.IGNORECASE | re.MULTILINE)
	findversion = re.compile('^[-a-z0-9]+ \s+ \( (?P<version> [^)]+ ) \)', re.IGNORECASE | re.X)

	def __init__( self, hgurl ):
		self.hgurl = hgurl
		self.tmpdir = None
		self.sourcename = None
		self.version = None

	
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

			# work in a subdirectory, because dpkg-buildpackage will put their results one dir below.
			os.mkdir( self.tmpdir + "/hg" )
			
			# perform the checkout
			subprocess.check_call( ["/usr/bin/hg", "clone", self.hgurl, self.tmpdir + "/hg"] )

			
	def GetSourceName( self ):
		''' Determine the name for the source package, and return it '''
		if self.sourcename == None:
			self.Clone()
			with open( self.tmpdir + "/hg/debian/control") as f:
				match = Build.findsource.search( f.read() )
				self.sourcename = match.group("sourcename")
		return self.sourcename


	def GenerateChangelog( self ):
		self.Clone()
		sourcename = self.GetSourceName()

		lastversion = '0'
		
		with open( self.tmpdir + "/hg/debian/changelog") as f:
			match = Build.findversion.search( f.read() )
			if match:
				lastversion = match.group("version")

		# Request the changelog from mercurial
		c = subprocess.Popen( ["/usr/bin/hg", "log", "--style=xml"], cwd=self.tmpdir + "/hg" , stdout=subprocess.PIPE)
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
				if version != 'tip' and version > lastversion:
					lastversion = version
				
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
				
		# give tip a special version
		# substitute 'tip' for last version with patchno incremented
		if 'tip' in versions:
			major,minor,patch = lastversion.split('.')

			# strip the build until the first non-numeric char		
			for i in range(0,len(patch)-1):
				if not patch[i].isdigit():
					patch = patch[0:i]

			versions['tip'].description = major + "." + minor + "." + str(long(patch)+1)

		return versions
		
	def NeedsBuild( self ):
		changes = self.GenerateChangelog()
		return ('tip' in changes) and changes['tip'].HasChanges()
							

	def _xmltext( nodelist ):
		''' Helper function to get the concatenated text of a node or nodelist '''
		rc = []
	
		todo = [nodelist]
	
		while todo:
			node = todo.pop()
		
			if isinstance(node, minidom.NodeList):
				for subnode in node:
					todo.append(subnode)
			elif node.nodeType == node.ELEMENT_NODE:
				for subnode in node.childNodes:
					todo.append(subnode)
			elif node.nodeType == node.TEXT_NODE:
				rc.append(node.data)
				
		return ''.join(rc)


class ChangelogVersion:
	isTip = False
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
			newmsg = _rewriteEntry(msg)
			if newmsg:
				result += "  * %s\n" % newmsg.replace("\n","\n    ")
			
		result += "-- %s %s\n\n" % ( overrideauthor or self.author, self.date.strftime("%a, %d %B %Y %H:%M:%S %z") )
		return result

	def _rewriteEntry( msg ):
		''' helper function to rewrite the log message to be used in a debian changelog '''
		# Drop short one-word messages
		if _regex_short_message.match( msg ):
			return "";
	
		# remove bug references, as they could interfere with the debiab BTS
		msg = _regex_bt_ref.sub( "", msg )
		# style: remove trailing period
		msg = _regex_trailing_period.sub( "", msg )
	
		return msg;


_regex_tagging_message = re.compile("Added tag (?P<version>.*) for changeset [a-z0-9]{12}")
_regex_short_message = re.compile("^[a-z]{0,12}$", re.I)
_regex_bt_ref = re.compile("(Refs|Closes|Resolves|Mantis|) \s* (bug)? \s* \# \d+ \s* \.?", re.I | re.X)
_regex_trailing_period = re.compile("\s*\.\s*$")


	
