# -*- mode: python -*-

from datetime import datetime
import glob
import os
import socket
import sys
import time


# HOME_DIR = 'C:\\Users\\dstokes\\workspace\\SSXViewer'
HOME_DIR = os.getcwd()

startTime = datetime.now()

logging.logger.setLevel(logging.WARN)


# HOME_DIR = 'C:\\Users\\dstokes\\workspace\\SSXViewer'
HOME_DIR = os.getcwd()

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

# This is a moderately kludgey auto-incrementing build number.
try:
    import socket, sys, time
    sys.path.append(HOME_DIR)
    from build_info import BUILD_NUMBER, DEBUG, VERSION
    versionString = '.'.join(map(str,VERSION))
    BUILD_NUMBER += 1
    writeInfo(VERSION, DEBUG, int(time.time()), socket.gethostname())
except Exception:
    BUILD_NUMBER = versionString = VERSION = "Unknown"
    DEBUG = True
    logging.logger.warning("*** Couldn't read and/or change build number!")


# Collect data files (needed for getting schema XML)
# Modified version of http://www.pyinstaller.org/wiki/Recipe/CollectDatafiles
def Datafiles(*filenames, **kw):
    import os
    
    allnames = []
    for f in filenames:
        allnames.extend(glob.glob(f))
    filenames = map(lambda x: os.path.abspath(x).replace('\\','/'), set(allnames))
#    filenames = list(set(allnames))
    
    def datafile(path, strip_path=True):
        #print path
        #parts = path.split('/')
        #path = name = os.path.join(*parts)
        name = path
        if strip_path:
            name = os.path.basename(path)
        return name, path, 'DATA'

    strip_path = kw.get('strip_path', True)
    return TOC(
        datafile(filename, strip_path=strip_path)
        for filename in filenames
        if os.path.isfile(filename))

#schemas = Datafiles('../mide_ebml/ebml/schema/mide.xml', 
#                    '../mide_ebml/ebml/schema/manifest.xml', 
#                    '../mide_ebml/ebml/schema/matroska.xml',
#                    strip_path=True)#False)
schemas = Tree('../mide_ebml/ebml/schema', 'mide_ebml/ebml/schema')
        
a = Analysis(['ide2mat.py'],
             pathex=['..', HOME_DIR, os.path.abspath(os.path.join(HOME_DIR,'..'))],
             hiddenimports=[],
             hookspath=None,
             runtime_hooks=None)

# Hack to suppress the 'pyconfig.h already exists' warning
for d in a.datas:
    if 'pyconfig' in d[0]: 
        a.datas.remove(d)
        break
        
pyz = PYZ(a.pure)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          schemas,
          exclude_binaries=False,
          name='ide2mat.exe',
          icon='ssx.ico',
          debug=False, #DEBUG,
          strip=None,
          upx=True,
          console=True
          )
print "finishing."
logging.logger.info("*** Completed building version %s, Build number %s, DEBUG=%s" % (versionString,BUILD_NUMBER,DEBUG))
logging.logger.info("*** Elapsed build time: %s" % (datetime.now()-startTime))
