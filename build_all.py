import argparse
from datetime import datetime
import json
import logging
import os
import subprocess
import socket
import sys
import time

from updater import CHANGELOG_URL

HOME_DIR = os.getcwd()
VERSION_INFO_FILE = 'updater files/slam_stick_lab.json'
logger = logging.getLogger('SlamStickLab.BuildAll')

builds = (
    r'C:\Python27\Scripts\pyinstaller.exe --noconfirm --onefile --distpath="%(dist_32)s" -i .\ssl.ico viewer-win-onefile.spec',
    r'c:\Python27_64\Scripts\pyinstaller --noconfirm --onefile --distpath="%(dist_64)s" --workpath=build_64 -i .\ssl.ico viewer-win-onefile.spec',
)

#===============================================================================
# 
#===============================================================================

def writeInfo(version, debug, buildNum, buildTime, buildMachine):
    with open('build_info.py', 'wb') as f:
        f.write('# AUTOMATICALLY UPDATED FILE: EDIT WITH CAUTION!\n')
        f.write('VERSION = %s\n' % str(version))
        f.write('DEBUG = %s\n' % debug)
        f.write('\n# AUTOMATICALLY-GENERATED CONTENT FOLLOWS; DO NOT EDIT MANUALLY!\n')
        f.write('BUILD_NUMBER = %d\n' % buildNum)
        f.write('BUILD_TIME = %d\n' % buildTime)
        f.write('BUILD_MACHINE = %r\n' % buildMachine)

#===============================================================================
# 
#===============================================================================

parser = argparse.ArgumentParser(description="Multi-Target Builder")
parser.add_argument('-v', '--version',  
                    help="A new version number, as 'x.y.z'.")
parser.add_argument('-r', '--release', action="store_true",
                    help="Builds are for release; build without DEBUG.")
parser.add_argument('-n', '--noincrement', action="store_true",
                    help="Don't increase the build number.")
args = parser.parse_args()
print args

#===============================================================================
# 
#===============================================================================

t0 = datetime.now()

try:
    sys.path.append(HOME_DIR)
    from build_info import BUILD_NUMBER, DEBUG, VERSION, BUILD_TIME, BUILD_MACHINE
    
    if args.version is not None:
        thisVersion = map(int, filter(len, args.version.split('.')))
        thisVersion = tuple(thisVersion + ([0] * (3-len(thisVersion)))) 
    else:
        thisVersion = VERSION
    
    thisBuildNumber = BUILD_NUMBER if args.noincrement else BUILD_NUMBER + 1
    thisDebug = not args.release
    thisTime = time.time()
    
    writeInfo(thisVersion, thisDebug, thisBuildNumber, thisTime, socket.gethostname())
    versionString = '.'.join(map(str,thisVersion))

except ImportError:
    print "import error"
    logger.warning("*** Couldn't read and/or change build number!")
    thisBuildNumber = thisVersion = versionString = "Unknown"
    thisDebug = True


print "*"*78
print ("*** Building Version %s, Build number %d," % (versionString,thisBuildNumber)),
if thisDebug:
    print "DEBUG version"
else:
    print "Release version"

buildArgs = {
    'dist_32': 'Slam Stick Lab v%s.%04d (32 bit)%s' % (versionString, thisBuildNumber, ' experimental' if thisDebug else ''),
    'dist_64': 'Slam Stick Lab v%s.%04d (64 bit)%s' % (versionString, thisBuildNumber, ' experimental' if thisDebug else ''),
}

bad = 0
for i, build in enumerate(builds):
    print("="*78),("\nBuild #%d: %s\n" % (i+1, build % buildArgs)),("="*78)
    bad += subprocess.call(build % buildArgs, stdout=sys.stdout, stdin=sys.stdin, shell=True)

print "*"*78
print "Completed %d builds, %d failures in %s" % (len(builds), bad, datetime.now() - t0)

if bad == len(builds):
    print "Everything failed; restoring old build_info."
    writeInfo(VERSION, DEBUG, BUILD_NUMBER, BUILD_TIME, BUILD_MACHINE)
else:
    print "Version: %s, build %s, DEBUG=%s" % (versionString, thisBuildNumber, thisDebug)

if args.release and bad == 0:
    print "*"*78
    print "Everything is okay; updating version info file '%s'" % VERSION_INFO_FILE
    with open(VERSION_INFO_FILE,'w') as f:
        json.dump({"version": thisVersion, 
                   "changelog": CHANGELOG_URL, 
                   "date": int(thisTime)},
                  f)
        
print "*"*78
