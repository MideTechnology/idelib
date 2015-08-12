import argparse
from datetime import datetime
import json
import logging
import os
import subprocess
import socket
import sys
import time

from git import InvalidGitRepositoryError
from git.repo import Repo

from updater import CHANGELOG_URL

HOME_DIR = os.getcwd()
VERSION_INFO_FILE = 'updater files/slam_stick_lab.json'
logger = logging.getLogger('SlamStickLab.BuildAll')

builds = (
    r'C:\Python27\Scripts\pyinstaller.exe %(options)s --noconfirm --onefile --distpath="%(dist_32)s" -i .\ssl.ico viewer-win-onefile.spec',
    r'c:\Python27_64\Scripts\pyinstaller --noconfirm --onefile --distpath="%(dist_64)s" --workpath=build_64 -i .\ssl.ico viewer-win-onefile.spec',
)

#===============================================================================
# 
#===============================================================================

def writeInfo(version, debug, beta, buildNum, buildTime, buildMachine, branch=None):
    with open('build_info.py', 'wb') as f:
        f.write('# AUTOMATICALLY UPDATED FILE: EDIT WITH CAUTION!\n')
        f.write('VERSION = %s\n' % str(version))
        f.write('DEBUG = %s\n' % debug)
        f.write('BETA = %s\n' % beta)
        f.write('\n# AUTOMATICALLY-GENERATED CONTENT FOLLOWS; DO NOT EDIT MANUALLY!\n')
        f.write('BUILD_NUMBER = %d\n' % buildNum)
        f.write('BUILD_TIME = %d\n' % buildTime)
        f.write('BUILD_MACHINE = %r\n' % buildMachine)
        if branch is not None:
            f.write('REPO_BRANCH = %r\n' % branch)

#===============================================================================
# 
#===============================================================================

parser = argparse.ArgumentParser(description="Multi-Target Builder")
parser.add_argument('-v', '--version',  
                    help="A new version number, as 'x.y.z'.")
parser.add_argument('-b', '--beta', action='store_true',
                    help="Builds a 'beta' release; sets BETA flag.")
parser.add_argument('-r', '--release', action="store_true",
                    help="Builds are for release; build without DEBUG.")
parser.add_argument('-n', '--noincrement', action="store_true",
                    help="Don't increase the build number.")
parser.add_argument('-c', '--clean', action="store_true",
                    help="Clean the PyInstaller cache (fix 'end of file' errors)")
parser.add_argument('-a', '--allowDirty', action="store_true",
                    help=("Allow builds if the git repo is 'dirty' (i.e. has "
                          "uncommitted changes)"))
parser.add_argument('-p', '--preview', action="store_true",
                    help="Don't build, just preview.")
args = parser.parse_args()

#===============================================================================
# 
#===============================================================================

t0 = datetime.now()

try:
    repo = Repo('.')
except InvalidGitRepositoryError:
    repo = None

try:
    sys.path.append(HOME_DIR)
    from build_info import BUILD_NUMBER, DEBUG, BETA, VERSION, BUILD_TIME, BUILD_MACHINE, REPO_BRANCH
    
    if args.version is not None:
        thisVersion = map(int, filter(len, args.version.split('.')))
        thisVersion = tuple(thisVersion + ([0] * (3-len(thisVersion)))) 
    else:
        thisVersion = VERSION
    
    thisBuildNumber = BUILD_NUMBER - 1 if args.noincrement else BUILD_NUMBER
    thisBeta = args.beta is True
    thisDebug = not (args.release or thisBeta)
    thisTime = time.time()
    
    if repo is not None:
        thisBranch = repo.active_branch
        if repo.is_dirty:
            if args.allowDirty:
                logger.warning("Repository is dirty, but ignoring it.")
            else:
                logger.error("*** Repository is dirty! Commit all changes before building!")
                exit(1)
    else:
        thisBranch = None
    
    if not args.preview:
        writeInfo(thisVersion, thisDebug, thisBeta, thisBuildNumber, thisTime, socket.gethostname(), thisBranch)
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
elif thisBeta:
    print "BETA version"
else:
    print "Release version"

buildType = ''
if thisDebug:
    buildType = ' experimental'
elif thisBeta:
    buildType = ' beta'
    
buildArgs = {
#     'dist_32': 'Slam Stick Lab v%s.%04d (32 bit)%s' % (versionString, thisBuildNumber, ' experimental' if thisDebug else ''),
#     'dist_64': 'Slam Stick Lab v%s.%04d (64 bit)%s' % (versionString, thisBuildNumber, ' experimental' if thisDebug else ''),
    'dist_32': 'Slam Stick Lab v%s.%04d%s' % (versionString, thisBuildNumber, buildType),
    'dist_64': 'Slam Stick Lab v%s.%04d%s' % (versionString, thisBuildNumber, buildType),
    'options': '--clean' if args.clean else ''
}


bad = 0
for i, build in enumerate(builds):
    print("="*78),("\nBuild #%d: %s\n" % (i+1, build % buildArgs)),("="*78)
    if args.preview:
        bad = 0
    else:
        bad += subprocess.call(build % buildArgs, stdout=sys.stdout, stdin=sys.stdin, shell=True)

print "*"*78
print "Completed %d builds, %d failures in %s" % (len(builds), bad, datetime.now() - t0)

if bad == len(builds):
    print "Everything failed; restoring old build_info."
    if not args.preview:
        writeInfo(VERSION, DEBUG, BETA, BUILD_NUMBER, BUILD_TIME, BUILD_MACHINE, REPO_BRANCH)
else:
    print "Version: %s, build %s, DEBUG=%s, BETA=%s" % (versionString, thisBuildNumber, thisDebug, thisBeta)
    # Reset the DEBUG variable in the info file (local runs are always DEBUG)
    if not args.preview:
        writeInfo(thisVersion, True, True, thisBuildNumber+1, thisTime, socket.gethostname(), thisBranch)

if args.release and bad == 0:
    print "*"*78
    print "Everything is okay; updating version info file '%s'" % VERSION_INFO_FILE
    info = {"version": thisVersion, "changelog": CHANGELOG_URL, "date": int(thisTime)}
    if not args.preview:
        with open(VERSION_INFO_FILE,'w') as f:
            json.dump(info, f)
    else:
        print "PREVIEW of info file:", json.dumps(info)
        
print "*"*78
