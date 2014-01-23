# -*- mode: python -*-

import os
# HOME_DIR = 'C:\\Users\\dstokes\\workspace\\SSXViewer'
HOME_DIR = os.getcwd()

# This is a kludgey auto-incrementing build number. Remove later!
try:
	import sys
	sys.path.append(HOME_DIR)
	from dev_build_number import BUILD_NUMBER
	BUILD_NUMBER += 1
	logging.logger.info("*** Build number %d" % BUILD_NUMBER)
	with open('dev_build_number.py', 'wb') as f:
		f.write('# DO NOT CHANGE THE FOLLOWING LINE MANUALLY!\n')
		f.write('BUILD_NUMBER = %d\n' % BUILD_NUMBER)
except Exception:
	logging.logger.warning("*** Couldn't read and/or change build number!")


# Collect data files (needed for getting schema XML)
# http://www.pyinstaller.org/wiki/Recipe/CollectDatafiles
def Datafiles(*filenames, **kw):
    import os
    
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
					strip_path=False)
		
a = Analysis(['viewer.py'],
             pathex=[HOME_DIR],
             hiddenimports=[],
             hookspath=None,
             runtime_hooks=None)
pyz = PYZ(a.pure)
exe = EXE(pyz,
          a.scripts,
          exclude_binaries=True,
          name='viewer.exe',
		  icon='ssx.ico',
          debug=False,
          strip=None,
          upx=True,
          console=False )
coll = COLLECT(exe,
				a.binaries,
                a.zipfiles,
                a.datas,
			    schemas,
                strip=None,
                upx=True,
                name='viewer')
