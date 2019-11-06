# -*- mode: python -*-

block_cipher = None

from datetime import datetime
import glob
import os
import platform
import sys

# HOME_DIR = 'C:\\Users\\dstokes\\workspace\\SlamStickLab'
HOME_DIR = os.getcwd()
startTime = datetime.now()

# logging.logger.setLevel(logging.WARN)

# This is a moderately kludgey auto-incrementing build number.
try:
    import socket, sys, time
    sys.path.append(HOME_DIR)
    from build_info import APPNAME, BUILD_NUMBER, DEBUG, VERSION
    versionString = '.'.join(map(str,VERSION))
except Exception:
    BUILD_NUMBER = versionString = VERSION = "Unknown"
    DEBUG = True
    print("*** Couldn't read and/or change build number!")

name='%s %s (%s).exe' % (APPNAME, versionString, platform.architecture()[0][:3])

# Collect data files (needed for getting schema XML)
# Modified version of https://github.com/pyinstaller/pyinstaller/wiki/Recipe-Collect-Data-Files
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
                    'mide_ebml/ebmlite/schemata/*.xml',
                    'LICENSES/*.txt',
                    'ABOUT/*',
                    'resources/*',
                    'config_dialog/defaults/*.xml',
                    strip_path=False)



a = Analysis(['viewer.py'],
             pathex=[HOME_DIR],
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             binaries=[],
             datas=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)

# Hack to suppress the 'pyconfig.h already exists' warning
for d in a.datas:
   if 'pyconfig' in d[0]:
       a.datas.remove(d)
       break

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          schemas,
          exclude_binaries=False,
          name=name,
          icon='endaq_lab.ico',
          debug=DEBUG,
          strip=None,
          upx=True,
          bootloader_ignore_signals=False,
          runtime_tmpdir=None,
          console=DEBUG
          )

print("*** Completed building version %s, Build number %d, DEBUG=%s" % (versionString,BUILD_NUMBER,DEBUG))
print("*** Elapsed build time: %s" % (datetime.now()-startTime))
