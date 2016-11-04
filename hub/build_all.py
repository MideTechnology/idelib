""" 
Utility script to do multiple builds. Makes the build number and other info
available to the built apps by modifying `build_info.py`.
"""

import argparse
from datetime import datetime
from glob import glob
import json
import logging
import os
from shutil import copyfile
import socket
import subprocess
import sys
import time
import zipfile

from docutils.examples import html_body
from git import InvalidGitRepositoryError
from git.repo import Repo

from assembly import birth_utils as util

HOME_DIR = os.getcwd()
VERSION_INFO_FILE = 'updater files/slam_stick_lab.json'
BETA_INFO_FILE = 'updater files/slam_stick_lab_beta.json'
RELEASE_NOTES_FILE = 'updater files/slam_stick_lab_changelog.txt'
RELEASE_NOTES_HTML = util.changeFilename(RELEASE_NOTES_FILE, ext=".html")
logger = logging.getLogger('SlamStickLab.BuildAll')

INFO_FILE = 'hub_build_info.py'

builds = (
    r'C:\Python27\Scripts\pyinstaller.exe %(options)s --noconfirm --onefile --distpath="%(dist_32)s" timehub-win-onefile.spec',
    r'c:\Python27_64\Scripts\pyinstaller --noconfirm --onefile --distpath="%(dist_64)s" --workpath=build_64 timehub-win-onefile.spec',
)

#===============================================================================
# 
#===============================================================================

def writeInfo(version, debug, beta, buildNum, buildTime, buildMachine, branch=None, commit=None):
    with open(INFO_FILE, 'wb') as f:
        f.write('# AUTOMATICALLY UPDATED FILE: EDIT WITH CAUTION!\n')
        f.write('VERSION = %s\n' % str(version))
        f.write('DEBUG = %s\n' % debug)
        f.write('BETA = %s\n' % beta)
        f.write('\n# AUTOMATICALLY-GENERATED CONTENT FOLLOWS; DO NOT EDIT MANUALLY!\n')
        f.write('BUILD_NUMBER = %d\n' % buildNum)
        f.write('BUILD_TIME = %d\n' % buildTime)
        f.write('BUILD_MACHINE = %r\n' % buildMachine)
        f.write('REPO_BRANCH = %r\n' % branch)
        f.write('REPO_COMMIT_ID = %r' % commit)


def updateJson(version, filename=VERSION_INFO_FILE, preview=False):
    with open(VERSION_INFO_FILE, 'r') as f:
        info = json.load(f)
     
    info["version"] = version
    info["date"] = int(thisTime)
    
    if not args.preview:
        with open(filename,'w') as f:
            json.dump(info, f)
    
    return info


def makeReleaseNotes(textfile=RELEASE_NOTES_FILE, output=None):
    """ Use docutils to generate HTML release notes.
    """
    if output is None:
        output = util.changeFilename(textfile, ext=".html")

    with open(textfile, "rb") as f:
        txt = unicode(f.read(), encoding="utf8")
        html = html_body(txt).replace("h1>", "h2>")
        
    with open(output, "wb") as f:
        f.write("<html><body>\n")
        f.write("<!-- automatically generated; edits will be lost! -->\n")
        f.write(html)
        f.write("</body></html>\n")
    
    return output
    

def compressFiles(args):
    """ Create zips of the executables, ready for upload.
    """
    for k,v in args.items():
        if not k.startswith('dist_'):
            continue
        exes = glob(os.path.join(v, '*.exe'))
        for ex in exes:
            path, zipname = os.path.split(ex)
            zipname = zipname.replace(' ','_').replace('(','').replace(')','')
            zipname = os.path.splitext(zipname)[0] + '.zip'
            zipname = os.path.join(path, zipname)
            if os.path.exists(zipname):
                print "Skipping existing file %s" % zipname
                continue
            else:
                print "Creating zip %s" % zipname
            z = zipfile.ZipFile(zipname, 'w', zipfile.ZIP_DEFLATED)
            z.write(ex)
            z.close()
            
        # Only one directory of exes
        break
                

#===============================================================================
# 
#===============================================================================

parser = argparse.ArgumentParser(description="Multi-Target Builder")
parser.add_argument('-v', '--version',  
                    help="A new version number, as 'x.y.z'. Note: editing build_info.py is better.")
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

if repo is not None:
    if repo.is_dirty:
        if args.allowDirty:
            logger.warning("Repository is dirty, but ignoring it.")
        else:
            print("*** Repository is dirty! Commit all changes before building!")
            exit(1)

try:
    sys.path.append(HOME_DIR)
    from build_info import VERSION, BETA, DEBUG
    from hub_build_info import BUILD_NUMBER, BUILD_MACHINE, BUILD_TIME
    from hub_build_info import REPO_BRANCH, REPO_COMMIT_ID
    
    if args.version is not None:
        thisVersion = map(int, filter(len, args.version.split('.')))
        thisVersion = tuple(thisVersion + ([0] * (3-len(thisVersion)))) 
    else:
        thisVersion = VERSION
    
    thisBuildNumber = BUILD_NUMBER - 1 if args.noincrement else BUILD_NUMBER
    thisBeta = args.beta is True
    thisDebug = not (args.release or thisBeta)
    thisTime = time.time()
    
    thisBranch = thisCommit = None
    if repo is not None:
        try:
            thisBranch = repo.active_branch
            thisCommit = repo.commits()[0].id
        except (AttributeError, IndexError):
            pass 
    
    if not args.preview:
        writeInfo(thisVersion, thisDebug, thisBeta, thisBuildNumber, thisTime, socket.gethostname(), thisBranch, thisCommit)
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
    'dist_32': 'Slam Stick Time Hub v%s.%04d%s' % (versionString, thisBuildNumber, buildType),
    'dist_64': 'Slam Stick Time Hub v%s.%04d%s' % (versionString, thisBuildNumber, buildType),
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
        writeInfo(VERSION, DEBUG, BETA, BUILD_NUMBER, BUILD_TIME, BUILD_MACHINE, REPO_BRANCH, REPO_COMMIT_ID)
else:
    print "Version: %s, build %s, DEBUG=%s, BETA=%s" % (versionString, thisBuildNumber, thisDebug, thisBeta)
    # Reset the DEBUG variable in the info file (local runs are always DEBUG)
    if not args.preview:
        writeInfo(thisVersion, True, True, thisBuildNumber+1, thisTime, socket.gethostname(), thisBranch, thisCommit)

if args.release and bad == 0:
    print "*"*78
    print "Everything is okay; updating version info file '%s'" % VERSION_INFO_FILE
    info = updateJson(thisVersion, VERSION_INFO_FILE, preview=args.preview)
    if args.preview:
        print "PREVIEW of info file:", json.dumps(info)
    else:
        compressFiles(buildArgs)

    # TEST
    compressFiles(buildArgs)
        
print "*"*78
