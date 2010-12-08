import re
import subprocess

from mx.Tools import verscmp

class AptRepository:
	path = None
	
	def __init__( self, path ):
		self.path = path
		
	def Include( self, distribution, changesfile ):
		c = subprocess.Popen( 
			["reprepro"]  +
			["--waitforlock", "12"] +
			["--basedir", self.path] +
			["include", distribution , changesfile]
			)
		c.wait()		

	def IncludeDsc( self, distribution, dscfile ):
		c = subprocess.Popen( 
			["reprepro"]  +
			["--waitforlock", "12"] +
			["--basedir", self.path] +
			["includedsc", distribution , dscfile]
			)
		c.wait()		

	def Exists( self, distribution, architecture, sourcename, version ):
		args = []
		args += [ "--waitforlock", "12" ]
		
		c = subprocess.Popen( 
			["reprepro"]  +
			["--waitforlock", "12"] +
			["--basedir", self.path] +
			( ["-A", architecture] if architecture else [] ) +
			["list", distribution , sourcename], 
			stdout=subprocess.PIPE)
			
		output = c.communicate()[0]
				
		for match in _regex_parse_list.finditer(output):
			if verscmp(match.group("version"), version) >= 0:
				return True

		return False
		
_regex_parse_list = re.compile( 
	"^" +
	"(?P<distribution> 	[-+.a-z0-9]+ ) \| " +
	"(?P<section> 		[-+.a-z0-9]+ ) \| " +
	"(?P<architecture> 	[-+.a-z0-9]+ ): \s+ " +
	"(?P<package> 		[-+.a-z0-9]+ ) \s+" +
	"(?P<version> 		[-+.a-z0-9]+ )$", re.X | re.M | re.I ) 
		
