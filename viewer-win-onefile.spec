# -*- mode: python -*-

from datetime import datetime
import glob
import os

# HOME_DIR = 'C:\\Users\\dstokes\\workspace\\SSXViewer'
HOME_DIR = os.getcwd()

startTime = datetime.now()
print "what?"

# This is a moderately kludgey auto-incrementing build number.
try:
    import socket, sys, time
    sys.path.append(HOME_DIR)
    from build_info import BUILD_NUMBER, DEBUG, VERSION
    versionString = '.'.join(map(str,VERSION))
    BUILD_NUMBER += 1
    logging.logger.info("*** Building Version %s, Build number %d" % (versionString,BUILD_NUMBER))
    with open('build_info.py', 'wb') as f:
        f.write('# AUTOMATICALLY UPDATED FILE: EDIT WITH CAUTION!\n')
        f.write('VERSION = %s\n' % str(VERSION))
        f.write('DEBUG = %s\n' % DEBUG)
        f.write('\n# AUTOMATICALLY-GENERATED CONTENT FOLLOWS; DO NOT EDIT MANUALLY!\n')
        f.write('BUILD_NUMBER = %d\n' % BUILD_NUMBER)
        f.write('BUILD_TIME = %d\n' % time.time())
        f.write('BUILD_MACHINE = %r\n' % socket.gethostname())
except Exception:
    BUILD_NUMBER = "Unknown"
    VERSION = "Unknown"
    DEBUG = True
    logging.logger.warning("*** Couldn't read and/or change build number!")


# Collect data files (needed for getting schema XML)
# http://www.pyinstaller.org/wiki/Recipe/CollectDatafiles
def Datafiles(*filenames, **kw):
    import os
    
    allnames = []
    for f in filenames:
        allnames.extend(glob.glob(f))
    filenames = list(set(allnames))
    
    def datafile(path, strip_path=True):
        parts = path.split('/')
        path = name = os.path.join(*parts)
        if strip_path:
            name = os.path.basename(path)
        return name, path, 'DATA'

    strip_path = kw.get('strip_path', True)
    return TOC(
        datafile(filename, strip_path=strip_path)
        for filename in filenames
        if os.path.isfile(filename))

schemas = Datafiles('mide_ebml/ebml/schema/mide.xml', 
                    'mide_ebml/ebml/schema/manifest.xml', 
                    'mide_ebml/ebml/schema/matroska.xml',
                    'LICENSES/*.txt',
                    'ABOUT/*',
                    strip_path=False)
        
a = Analysis(['viewer.py'],
             pathex=[HOME_DIR],
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
          name='Slam Stick Lab.exe',
          icon='ssl.ico',
          debug=False,
          strip=None,
          upx=True,
          console=DEBUG
          )

logging.logger.info("*** Completed building version %s, Build number %d, DEBUG=%s" % (versionString,BUILD_NUMBER,DEBUG))
logging.logger.info("*** Build time: %s" % (datetime.now()-startTime))
