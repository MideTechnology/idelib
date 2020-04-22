# -*- mode: python -*-

from datetime import datetime
import glob
import os
import platform
import socket
import sys
import time


startTime = datetime.now()
logging.logger.setLevel(logging.WARN)
HOME_DIR = os.getcwd()

NAME = "raw2fid"
#===============================================================================
#
#===============================================================================

# This is a moderately kludgey auto-incrementing build number.
try:
    import socket, sys, time
    sys.path.append(HOME_DIR)
    from build_info import BUILD_NUMBER, DEBUG, VERSION
    versionString = '.'.join(map(str,VERSION))
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
        name = path
        if strip_path:
            name = os.path.basename(path)
        return name, path, 'DATA'

    strip_path = kw.get('strip_path', True)
    return TOC(
        datafile(filename, strip_path=strip_path)
        for filename in filenames
        if os.path.isfile(filename))

#schemas = Datafiles('../idelib/ebml/schema/mide.xml',
#                    '../idelib/ebml/schema/manifest.xml',
#                    '../idelib/ebml/schema/matroska.xml',
#                    strip_path=True)#False)
schemas = Tree('../idelib/ebml/schema', 'idelib/ebml/schema')

a = Analysis(['%s.py' % NAME],
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
          name='%s_%s.exe' % (NAME, platform.architecture()[0][:3]),
          icon='ssx.ico',
          debug=False, #DEBUG,
          strip=None,
          upx=True,
          console=True
          )
print "finishing."
logging.logger.info("*** Completed building version %s, Build number %s, DEBUG=%s" % (versionString,BUILD_NUMBER,DEBUG))
logging.logger.info("*** Elapsed build time: %s" % (datetime.now()-startTime))
