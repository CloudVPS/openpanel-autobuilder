from __future__ import with_statement # for python 2.5 compat

import os
import re
import subprocess

import shutil
import tempfile # Building is done in a temporary folder
import xml.etree.ElementTree as ET # to parse hg log output

from mx.DateTime.ISO import ParseDateTimeUTC
import mx.DateTime
from mx.Tools import verscmp

from collections import defaultdict

import build # import self. Need this to determine own path
import codecs


class Build:
    tmpbasedir="/tmp/"
    findsource  = re.compile('^Source:\s*(?P<sourcename>.*)\s*$', re.IGNORECASE | re.MULTILINE)
    findarch    = re.compile('^Architecture:\s*(?P<arch>.*)\s*$', re.IGNORECASE | re.MULTILINE)
    findversion = re.compile('^[-a-z0-9]+ \s+ \( (?P<version> [^)]+ ) \)', re.IGNORECASE | re.X)
    findhgtags  = re.compile('^(?P<tagname> [-a-z0-9.]+ ) \s+ (?P<rev>\d+) : [a-f0-9]+ $', re.IGNORECASE | re.X | re.MULTILINE)


    tmpdir = None # Build location
    sourcename = None # Name of the source package
    architectures = None
    version = None
    dscpath = None
    lasttag = None
    buildtag = None
    targetdistribution = None
    

    def __init__( self, hgurl, targetdistribution ):
        self.hgurl = hgurl
        if isinstance(targetdistribution,str) or isinstance(targetdistribution,unicode): 
            self.targetdistribution = [targetdistribution]
        else:
            self.targetdistribution = targetdistribution

    
    def __del__( self ):
        self.CleanUp()
        pass

    def CleanUp( self ):
        # remove the tmp directory
        if self.tmpdir:
            shutil.rmtree( self.tmpdir )
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
            lasttag = "0.0.0"
            for match in self.findhgtags.finditer( taglist ):
                if match.group("tagname") != 'tip':
                    self.lasttag = lasttag = match.group("tagname")
                    break
                else:
                    tiprev = long(match.group("rev"))

            split_tag = lasttag.split(".")
            while len(split_tag) < 3:
                split_tag.append("0")
                lasttag = ".".join(split_tag)

            if tip: #checking out the tip version to build
                subprocess.check_call( ["hg", "update", "--clean"], cwd=hgdir )
                self.buildtag = lasttag + "." + str(tiprev) + "+tip"
            elif self.lasttag: # checking out the last tag
                subprocess.check_call( ["hg", "update", "--clean", self.lasttag], cwd=hgdir )
                self.buildtag = lasttag
            else:
                self.buildtag = None        

    def GetBuildTag(self):
        return self.buildtag
    

    def GetSourceName( self ):
        ''' Determine the name for the source package, and return it '''
        if not self.sourcename:
            self.Clone()
            with codecs.open( self.tmpdir + "/hg/debian/control", 'r', 'utf-8') as f:
                match = Build.findsource.search( f.read() )
                self.sourcename = match.group("sourcename")
        return self.sourcename


    def GetArchitectures( self ):
        ''' Determine the name for the source package, and return it '''
        if not self.architectures:
            self.Clone()
            self.architectures = set()

            with codecs.open( self.tmpdir + "/hg/debian/control", 'r', 'utf-8') as f:
                for match in Build.findarch.finditer( f.read() ):
                    self.architectures.update( match.group("arch").split() )
        
        return self.architectures


    def GenerateChangelog( self ):
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
    
        versions = defaultdict( ChangelogVersion )

        for logentry in etlog:
            if logentry.find("tag") != None:

                version = logentry.find("tag").text
                
                if version != 'tip':
                    version_s = version.split('.',2)
                    if len(version_s) == 2:
                        version += '.0'
            
                currentversion = versions[version]
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
                taggedversion = versions[ tag.group("version") ]
                taggedversion.author = "%s <%s>" % ( logentry.find("author").text, logentry.find("author").attrib["email"] )                                
                taggedversion.date = ParseDateTimeUTC(logentry.find("date").text)
            else:
                # this is a regular changelog item. Add it to the message
                currentversion.messages.append( msg )
            
        if not self.buildtag in versions:
            versions[ self.buildtag ].author = "OpenPanel packager <packages@openpanel.com>"
            versions[ self.buildtag ].description = self.buildtag
            versions[ self.buildtag ].date = mx.DateTime.now()
            versions[ self.buildtag ].messages += ["Rebuilt from hg tip"]
            versions[ self.buildtag ].sourcename = sourcename
            
        return versions
        
        
    def WriteVersion( self ):
        versions = self.GenerateChangelog()
        
        # determine last version in changelog
        lastchangelogversion = '0.0.0'
        
        tail = ''
        try:
            with codecs.open( self.tmpdir + "/hg/debian/changelog",'r', 'utf-8') as f:
                tail = f.read()
                match = Build.findversion.search( tail )
                if match:
                    lastchangelogversion = match.group("version")
        except:
            pass

        with codecs.open( self.tmpdir + "/hg/debian/changelog", 'w', 'utf-8') as f:
        
            nversions = 0
            for version in sorted( versions, reverse=True, cmp=verscmp ):
                if verscmp(version, lastchangelogversion) > 0 and versions[version].HasChanges():
                    if version == 'tip':
                        versions[version].description = self.buildtag

                    f.write( versions[version].GetDebianFormatted( distributions=self.targetdistribution ) )
                    nversions += 1
            
            if nversions == 0:
                if versions[self.buildtag]:
                    f.write( versions[self.buildtag].GetDebianFormatted( distributions=self.targetdistribution ) )
                else:
                    self.buildtag = lastchangelogversion
            
            f.write(tail)
        
        # write version.id with the tag to be built
        with codecs.open( self.tmpdir + "/hg/version.id", 'w', 'utf-8') as f:
            f.write( self.buildtag )
    
                            
    def BuildSource( self ):
        if not self.dscpath:
            self.WriteVersion()
            
            environ = {}
            environ.update( os.environ )
            environ["DEBFULLNAME"]="OpenPanel packager"
            environ["DEBEMAIL"]= "packages@openpanel.com"
            
            sourcedir = self.GetSourceName() + "-" + self.buildtag
            os.rename( self.tmpdir + "/hg", self.tmpdir + "/" + sourcedir )
            
            """
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
                cwd=self.tmpdir + "/" + sourcedir)
                """
                
            c = subprocess.Popen( 
                ["debuild", 
                    "-S", # Source build
                    "-i", # use default file ignores
                    "-I", # use default dir ignores
                    "-d",  # ignore build-dependencies
                    "-k4EAC69B9",  # use gpg key for OpenPanel packager <packages@openpanel.com>
                    "-epackages@openpanel.com",
                ], 
                env=environ,
                cwd=self.tmpdir + "/" + sourcedir)
                                
            c.wait()
            shutil.rmtree( self.tmpdir + "/" + sourcedir )
            
            self.dscpath = "%s/%s_%s.dsc" % (self.tmpdir, self.GetSourceName(), self.buildtag)
            
        return self.dscpath
        
    
    def Build( self, architecture, binary_only=False, repository=None ):
        dscpath = self.BuildSource()
        
        if architecture != 'source':
            # jikes. I really don't want to do this, but I don't know how to prevent it...
            # Hopefully, an answer will appear at http://stackoverflow.com/q/4386672/266042
            c = subprocess.Popen( 
                    ["pbuilder"] + 
                    ["update"] +
                    ["--basetgz", "/var/cache/pbuilder/%s-%s.tgz" % (self.targetdistribution[0],architecture) ] +
                    ["--bindmounts", "/root/repository"]
                )
            c.wait()
                
            if os.path.exists( self.tmpdir + "/results" ):
                shutil.rmtree( self.tmpdir + "/results" )

                
            os.makedirs(self.tmpdir + "/results")
    
            c = subprocess.Popen( 
                    ["pbuilder"] + 
                    ["build"] +
                    ["--basetgz", "/var/cache/pbuilder/%s-%s.tgz" % (self.targetdistribution[0],architecture) ] +
                    ["--bindmounts", "/root/repository"] +
                    ["--buildresult", self.tmpdir + "/results"] + 
                    ["--autocleanaptcache" ] +
                    ( ["--binary-arch"] if binary_only else [] ) +
                    [ dscpath ]
                )
            
            c.wait()
            changesfile = "%s/results/%s_%s_%s.changes" % (self.tmpdir, self.GetSourceName(), self.buildtag, architecture )
        else:
            changesfile = "%s/%s_%s_%s.changes" % (self.tmpdir, self.GetSourceName(), self.buildtag, architecture )
            
        return changesfile


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


    
