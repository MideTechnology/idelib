# -*- mode: python -*-

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
             pathex=['C:\\Users\\dstokes\\workspace\\wvr'],
             hiddenimports=[],
             hookspath=None,
             runtime_hooks=None)
pyz = PYZ(a.pure)
exe = EXE(pyz,
          a.scripts,
          exclude_binaries=True,
          name='viewer.exe',
          debug=False,
          strip=None,
          upx=True,
          console=True )
coll = COLLECT(exe,
				a.binaries,
                a.zipfiles,
                a.datas,
			    schemas,
                strip=None,
                upx=True,
                name='viewer')
