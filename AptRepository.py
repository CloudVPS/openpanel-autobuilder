import re
import subprocess

from mx.Tools import verscmp

class AptRepository:
    path = None
    
    def __init__( self, path ):
        self.path = path
        
    def Include( self, distribution, changesfile, component=None ):
        print "### Including %s" % changesfile
        c = subprocess.Popen( 
            ["reprepro"]  +
            ["--waitforlock", "12"] +
            (["--component", component] if component else []) +
            ["--basedir", self.path] +
            ["include", distribution , changesfile]
            )
        c.wait()        

        if c.returncode:
            raise "Process exit with code: %s" % c.returncode

    def Exists( self, distribution, architecture, sourcename, version ):

        arch_filter = "Architecture (==%s)," % architecture if architecture else ""

        # for packages that were part
        pkg_filter = [
            "(%s Source (==%s))" % (arch_filter,sourcename),
            "(%s !Source,Package(==%s))" % (arch_filter,sourcename)
        ]
        pkg_filter = "|".join(pkg_filter)
        
        print pkg_filter
    
        c = subprocess.Popen( 
            ["reprepro"]  +
            ["--waitforlock", "12"] +
            ["--basedir", self.path] +
            ( ["-A", architecture] if architecture else [] ) +
            ["listfilter", distribution , pkg_filter ], 
            stdout=subprocess.PIPE)
            
        output = c.communicate()[0]
        
        if c.returncode:
            raise "Process exit with code: %s" % c.returncode
                
        for match in _regex_parse_list.finditer(output):
            if verscmp(match.group("version"), version) >= 0:
                print version
                return True

        return False
        
_regex_parse_list = re.compile( 
    "^" +
    "(?P<distribution>  [-+.a-z0-9]+ ) \| " +
    "(?P<section>       [-+.a-z0-9]+ ) \| " +
    "(?P<architecture>  [-+.a-z0-9]+ ): \s+ " +
    "(?P<package>       [-+.a-z0-9]+ ) \s+" +
    "(?P<version>       [-+.a-z0-9]+ )$", re.X | re.M | re.I ) 
        
