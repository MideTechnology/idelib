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
import pprint
import string
import tempfile
import time
import zipfile

from docutils.examples import html_body

# from idelib import xml2ebml
# import idelib.ebml.schema.mide as schema_mide
# import idelib.ebml.schema.manifest as schema_manifest

from idelib.ebmlite import loadSchema
import idelib.ebmlite.util as ebml_util

from assembly import birth_utils as util

#===============================================================================
# 
#===============================================================================

schema_mide = loadSchema('mide.xml')
schema_manifest = loadSchema('manifest.xml')

#===============================================================================
# 
#===============================================================================

PACKAGE_FORMAT_VERSION = 1
PACKAGE_EXT = "fw"

PRODUCT_ROOT_PATH = os.path.realpath("R:/LOG-Data_Loggers/LOG-0002_Slam_Stick_X/")
BIRTHER_PATH = os.path.realpath(os.path.join(PRODUCT_ROOT_PATH, "Design_Files/Firmware_and_Software/Manufacturing/LOG-XXXX-SlamStickX_Birther/"))

FIRMWARE_PATH = os.path.join(BIRTHER_PATH, "firmware")
TEMPLATE_PATH = os.path.join(BIRTHER_PATH, "data_templates")

BOOT_FILE = os.path.join(FIRMWARE_PATH, "boot.bin")
BOOT_VER_FILE = os.path.join(FIRMWARE_PATH, "boot_version.txt")
APP_FILE = os.path.join(FIRMWARE_PATH, "app.bin")
APP_VER_FILE = os.path.join(FIRMWARE_PATH, "app_version.txt")
NOTES_FILE = os.path.join(FIRMWARE_PATH, 'release_notes.txt')
NOTES_HTML_FILE = util.changeFilename(NOTES_FILE, ext=".html")

UPDATE_DIR = os.path.realpath(os.path.join(PRODUCT_ROOT_PATH, 'Design_Files/Firmware_and_Software/Release/Firmware/updates/'))
UPDATE_BUILD_FILE = os.path.join(UPDATE_DIR, "updater_package_build_num.txt")

#===============================================================================
# 
#===============================================================================

def getTemplates():
    names = "manifest.template.xml", "cal.template.xml", "recprop.template.xml"
    templates = []
    for root, dirs, files in os.walk(TEMPLATE_PATH): 
        for d in dirs[:]:
            if d.startswith('.') or 'TEST' in d or d=='bak' or d=='OLD':
                dirs.remove(d)
        templates.extend(map(lambda x: os.path.join(root, x), 
                             filter(lambda x: x.lower() in names, files)))
    return templates


def addTemplates(z, templates=None):
    """ Add EBML versions of all templates.
    """
    for t in templates:
        schema = schema_manifest if 'manifest' in t else schema_mide
        ebmlName = util.changeFilename(t, 'ebml', tempfile.gettempdir())
        ebml_util.xml2ebml(t, ebmlName, schema)
#         with open(ebmlName, 'wb') as f:
#             f.write(xml2ebml.readXml(t, schema))
        zipName = util.changeFilename(t, 'ebml')[len(TEMPLATE_PATH)+1:]
        zipName = zipName.strip('\\/').replace('\\', '/')
        z.write(ebmlName, "templates/%s" % zipName)


def addBinaries(z, boot=False):
    """ Add firmware and bootloader binaries.
    """
    if boot:
        z.write(BOOT_FILE, os.path.basename(BOOT_FILE))
    z.write(APP_FILE, os.path.basename(APP_FILE))

    
def addJson(z, appVersion, appName="app.bin", boot=False, preview=False):
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
    data['app_name'] = appName
    data['app_version'] = appVersion
    data['app_hash'] = hash(util.readFile(APP_FILE))
    if boot:
        if isinstance(boot, basestring):
            data['boot_name'] = boot
        data['boot_version'] = util.readFileLine(BOOT_VER_FILE, str)
        data['boot_hash'] = hash(util.readFile(BOOT_FILE))

    buildNum = util.readFileLine(UPDATE_BUILD_FILE, last=True)
    if buildNum is not None:
        data['package_build_number'] = buildNum

    with open(temp, 'wb') as f:
        json.dump(data, f)

    if not preview:
        with open(UPDATE_BUILD_FILE, 'wb') as f:
            f.write("# This is incremented each time a .FW package is built. Don't edit!\n")
            f.write('%d\n' % (buildNum + 1))

    z.write(temp, 'fw_update.json')
    return data


def getRevNum(app, default):
    """ Parse the revision number out of the app name.
    """
    for s in app.lower().replace('-','_').split('_'):
        s = s.strip()
        if s.startswith('rev') and s[-1].isdigit():
            try:
                return int(s.strip(string.ascii_letters + string.punctuation))
            except None:#ValueError:
                continue
    return default


def makeReleaseNotes(textfile, output=None):
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
    

def makePackage(app, boot=False, preview=False, useHtml=True):
    """ Main function to generate an updater package.
    """
    fwRev = util.readFileLine(APP_VER_FILE, int)
    notesFile = NOTES_FILE
    now = datetime.now()
    if os.path.basename(app).lower() == 'app.bin':
        nowStr = now.strftime("%Y%m%d")
        basename = "firmware_r%d_%s" % (fwRev, nowStr)
    else:
        basename = os.path.splitext(os.path.basename(app))[0]
        fwRev = getRevNum(basename, fwRev)
        nf = util.changeFilename(app, ext=".txt")
        if os.path.exists(nf):
            notesFile = nf
    filename = "%s.%s" % (os.path.join(UPDATE_DIR, basename), PACKAGE_EXT)
    
    if preview is True:
        print "Previewing package build:", filename
        filename = os.path.join(tempfile.gettempdir(), 'preview.fw')
    
    templates = getTemplates()
    
    aborted = False
    print "Writing to file %s" % filename
    with zipfile.ZipFile(filename, "w", zipfile.ZIP_DEFLATED) as f:
        print "Generating JSON..."
        info = addJson(f, fwRev, appName=os.path.basename(app), boot=boot, preview=preview)
        if preview:
            pprint.pprint(info)
        print "Adding app binary %s..." % app
        f.write(app, os.path.basename(app))
        if boot:
            print "Adding bootloader binary %s..." % BOOT_FILE
            f.write(BOOT_FILE, os.path.basename(BOOT_FILE))
        if os.path.exists(notesFile):
            print "Adding release notes:", notesFile
            f.write(notesFile, os.path.basename(NOTES_FILE))
            print "Generating HTML release notes..."
            f.write(makeReleaseNotes(notesFile), os.path.basename(NOTES_HTML_FILE))
            
        print "Adding %d templates..." % len(templates)
        addTemplates(f, templates)
        print "Done!"
        if preview:
            print "Files added:"
            for n in f.namelist():
                print " %s" % n
        
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
    
    parser = argparse.ArgumentParser(description="Slam Stick Firmware Package Maker")
    parser.add_argument("--app", "-a", default=APP_FILE, metavar="APP.BIN",
                        help="Full path to the application binary.")
    parser.add_argument("--bootloader", "-b", action="store_true", 
                        help="Include the bootloader.")
    parser.add_argument("--nohtml", "-n", action="store_true", 
                        help="Do not generate HTML release notes.")
    parser.add_argument("--preview", '-p', action="store_true", 
                        help="Preview the package and its rendered release notes.")
    
    args = parser.parse_args() 
    makePackage(args.app, boot=args.bootloader, preview=args.preview,
                useHtml=(not args.nohtml))

