'''
Utility to build firmware update packages: zip format files containing firmware
and bootloader binaries, userpage templates, and metadata. These are generated
from the binaries and templates in the SSX manufacturing directories.

Created on Sep 3, 2015

@author: dstokes
'''
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

PRODUCT_ROOT_PATH = "R:/LOG-Data_Loggers/LOG-0002_Slam_Stick_X/"
BIRTHER_PATH = os.path.join(PRODUCT_ROOT_PATH, "Design_Files/Firmware_and_Software/Manufacturing/LOG-XXXX-SlamStickX_Birther/")

FIRMWARE_PATH = os.path.join(BIRTHER_PATH, "firmware")
TEMPLATE_PATH = os.path.join(BIRTHER_PATH, "data_templates")

BOOT_FILE = os.path.join(FIRMWARE_PATH, "boot.bin")
BOOT_VER_FILE = os.path.join(FIRMWARE_PATH, "boot_version.txt")
APP_FILE = os.path.join(FIRMWARE_PATH, "app.bin")
APP_VER_FILE = os.path.join(FIRMWARE_PATH, "app_version.txt")


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
    if templates is None:
        templates = getTemplates()
    for t in templates:
        schema = schema_manifest if 'manifest' in t else schema_mide
        ebmlName = util.changeFilename(t, 'ebml', tempfile.gettempdir())
        with open(ebmlName, 'wb') as f:
            f.write(xml2ebml.readXml(t, schema))
        zipName = util.changeFilename(t, 'ebml')[len(TEMPLATE_PATH)+1:]
        zipName = zipName.strip('\\/').replace('\\', '/')
        z.write(ebmlName, zipName)


def addBinaries(z):
    """ Add firmware and bootloader binaries.
    """
    z.write(BOOT_FILE, os.path.basename(BOOT_FILE))
    z.write(APP_FILE, os.path.basename(APP_FILE))

    
def addJson(z):
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
    data['boot_version'] = util.readFileLine(BOOT_VER_FILE, str)
    data['boot_hash'] = hash(util.readFile(BOOT_FILE))
    data['app_version'] = util.readFileLine(APP_VER_FILE, int)
    data['app_hash'] = hash(util.readFile(APP_FILE))
    
    with open(temp, 'wb') as f:
        json.dump(data, f)

    z.write(temp, 'fw_update.json')
    

