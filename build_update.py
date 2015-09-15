'''
Utility to build firmware update packages: zip format files containing firmware
and bootloader binaries, userpage templates, and metadata. These are generated
from the binaries and templates in the SSX manufacturing directories.

Created on Sep 3, 2015

@author: dstokes
'''
from datetime import datetime
import json
import os
import tempfile
import time
import zipfile

from mide_ebml import xml2ebml
import mide_ebml.ebml.schema.mide as schema_mide
import mide_ebml.ebml.schema.manifest as schema_manifest

from assembly import birth_utils as util

#===============================================================================
# 
#===============================================================================

PACKAGE_FORMAT_VERSION = 1
PACKAGE_EXT = "fw"

PRODUCT_ROOT_PATH = "R:/LOG-Data_Loggers/LOG-0002_Slam_Stick_X/"
BIRTHER_PATH = os.path.join(PRODUCT_ROOT_PATH, "Design_Files/Firmware_and_Software/Manufacturing/LOG-XXXX-SlamStickX_Birther/")

FIRMWARE_PATH = os.path.join(BIRTHER_PATH, "firmware")
TEMPLATE_PATH = os.path.join(BIRTHER_PATH, "data_templates")

BOOT_FILE = os.path.join(FIRMWARE_PATH, "boot.bin")
BOOT_VER_FILE = os.path.join(FIRMWARE_PATH, "boot_version.txt")
APP_FILE = os.path.join(FIRMWARE_PATH, "app.bin")
APP_VER_FILE = os.path.join(FIRMWARE_PATH, "app_version.txt")
NOTES_FILE = os.path.join(FIRMWARE_PATH, 'release_notes.txt')

UPDATE_DIR = os.path.join(PRODUCT_ROOT_PATH, 'Design_Files/Firmware_and_Software/Release/Firmware/updates/')

#===============================================================================
# 
#===============================================================================

def getTemplates():
    names = "manifest.template.xml", "cal.template.xml", "recprop.template.xml"
    templates = []
    for root, dirs, files in os.walk(TEMPLATE_PATH): 
        for d in dirs:
            if d.startswith('.') or 'TEST' in d or d=='bak':
                dirs.remove(d)
        templates.extend(map(lambda x: os.path.join(root, x), filter(lambda x: x.lower() in names, files)))
    return templates


def addTemplates(z, templates=None):
    """ Add EBML versions of all templates.
    """
    for t in templates:
        schema = schema_manifest if 'manifest' in t else schema_mide
        ebmlName = util.changeFilename(t, 'ebml', tempfile.gettempdir())
        with open(ebmlName, 'wb') as f:
            f.write(xml2ebml.readXml(t, schema))
        zipName = util.changeFilename(t, 'ebml')[len(TEMPLATE_PATH)+1:]
        zipName = zipName.strip('\\/').replace('\\', '/')
        z.write(ebmlName, "templates/%s" % zipName)


def addBinaries(z, boot=False):
    """ Add firmware and bootloader binaries.
    """
    if boot:
        z.write(BOOT_FILE, os.path.basename(BOOT_FILE))
    z.write(APP_FILE, os.path.basename(APP_FILE))

    
def addJson(z, boot=False):
    """ Generate and add JSON metadata.
    """
    source = os.path.join(FIRMWARE_PATH, 'fw_update.json')
    temp = os.path.join(tempfile.gettempdir(), 'fw_update.json')
    if os.path.exists(source):
        with open(source, 'rb') as f:
            data = json.load(f)
    else:
        data = {}
    
    # TODO: Add any generated data

    data['created'] = time.time()
    data['package_format'] = PACKAGE_FORMAT_VERSION
    data['app_version'] = util.readFileLine(APP_VER_FILE, int)
    data['app_hash'] = hash(util.readFile(APP_FILE))
    if boot:
        data['boot_version'] = util.readFileLine(BOOT_VER_FILE, str)
        data['boot_hash'] = hash(util.readFile(BOOT_FILE))

    with open(temp, 'wb') as f:
        json.dump(data, f)

    z.write(temp, 'fw_update.json')


def makePackage(app, boot=False, preview=False):
    """
    """
    fwRev = util.readFileLine(APP_VER_FILE, int)
    now = datetime.now()
    nowStr = now.strftime("%Y%m%d")
    basename = "firmware_r%d_%s.%s" % (fwRev, nowStr, PACKAGE_EXT)
    filename = os.path.join(UPDATE_DIR, basename)
    
    if preview is True:
        filename = os.path.join(tempfile.gettempdir(), 'preview.fw')
    
    templates = getTemplates()
    
    aborted = False
    print "Writing to file %s" % filename
    with zipfile.ZipFile(filename, "w", zipfile.ZIP_DEFLATED) as f:
        print "Generating JSON..."
        addJson(f, boot)
        print "Adding app binary %s..." % app
        f.write(app, os.path.basename(app))
        if boot:
            print "Adding bootloader binary %s..." % BOOT_FILE
            f.write(BOOT_FILE, os.path.basename(BOOT_FILE))
        if os.path.exists(NOTES_FILE):
            print "Adding release notes..."
            f.write(NOTES_FILE, os.path.basename(NOTES_FILE))
        print "Adding %d templates..." % len(templates)
        addTemplates(f, templates)
        print "Done!"
        
    if aborted is True:
        print "Removing bad/incomplete zip..."
        os.remove(filename)
    
    if preview is True:
        pass
    
#===============================================================================
# 
#===============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="SSX/SSC Firmware Package Maker")
    parser.add_argument("--app", "-a", default=APP_FILE, help="Full path to the application binary.")
    parser.add_argument("--bootloader", "-b", action="store_true", help="Include the bootloader.")
    parser.add_argument("--preview", '-p', help="Preview the package and its rendered release notes.")
    
    args = parser.parse_args() 
    makePackage(args.app, boot=args.bootloader)

