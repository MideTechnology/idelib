'''
Reader for the Live Rocket Test telemetry data. 

Note: the data is in a preliminary format and does not contain much of 
anything beyond the raw sensor data as SimpleChannelDataBlocks. 

@todo: Create a more general-purpose file reader, probably part of the
    Dataset's __init__().

Created on Oct 4, 2013

@author: dstokes


FOR TESTING: 

import rocket_test; doc = rocket_test.openFile(); l = doc.channels[0].getSession(0)

Time to read file:
From Slam Stick X: 0:06:47.506000
'''

from datetime import datetime
import os
import struct
import sys

from dataset import Dataset
import parsers

#===============================================================================
# 
#===============================================================================

# testFile = r"e:\test.dat"
# testFile = r"test_full_cdb.DAT"
# testFile = r"P:\WVR_RIF\04_Design\Electronic\Software\testing\test_ebml_files\test_full_cdb_huge.dat"
testFile = r"test_full_cdb_huge.dat"

#===============================================================================
# Some experiments in modularizing things
#===============================================================================

# Parser importer. These are taken from the module by type. We probably want
# to create the list of parser types 'manually' in the real app; it's safer.
elementParserTypes = parsers.getElementHandlers()

# Hard-coded sensor/channel mapping. Will eventually be read from EBML file.
sensors = {
    0x00: {"name": "SlamStick Combined Sensor", 
           "channels": {
                0x00: {"name": "Accelerometer XYZ",
                       "parser": struct.Struct(">HHH"), 
                       "subchannels":{0: {"name": "X"},
                                      1: {"name": "Y"},
                                      2: {"name": "Z"}
                                      },
                       },
                0x40: {"name": "Pressure/Temperature",
                       "parser": parsers.MPL3115PressureTempParser(),
                       "subchannels": {0: {"name": "Pressure"},
                                       1: {"name": "Temperature"}
                                       },
                       },
                0x43: {"name": "Crystal Drift",
                       "parser": struct.Struct(">II") 
                       },
                0x45: {"name": "Gain/Offset",
                       "parser": struct.Struct("<i"), 
                       },
                },
           },
}

#===============================================================================
# Progress indicators, because I'm impatient.
#===============================================================================

class ASCIIProgressBar(object):
    """ The file loader will eventually have a callback function (or 
        function-like object) like this as a parameter, which will be called 
        at specified intervals. A callback function should expect a 
        normalized float value, roughly the percentage of the file read. A 
        value of -1 ends the progress bar.
    """
    def __init__(self, *args, **kwargs):
        self.action = kwargs.pop('action',('Reading','Read'))
        self.filename = kwargs.pop('filename', "(something)")
        self.startTime = None
    
    def start(self, val, count=None, total=None):
        self.startTime = datetime.now()
        print "%s file %s" % (self.action[0], os.path.realpath(self.filename))
    
    def stop(self, val, count=None, total=None):
        sys.stdout.write(" Done!\n%s %s elements in %s\n" % \
                         (self.action[1], count, datetime.now() - self.startTime))
        sys.stdout.flush()
    
    def update(self, val, count=None, total=None):
        sys.stdout.write('\x0d%s samples read ' % val)
#         sys.stdout.write(".")
        sys.stdout.flush()
    
    def __call__(self, val, count=None, total="some"):
        """ Draw/update a progress bar. 
        """
        if self.startTime == None:
            self.start(val, count, total)
        elif val == -1:
            self.stop(val, count, total)
        else:
            self.update(val, count, total)


import Tkinter as tk; import ttk

class TkProgressBar(object):
    def __init__(self, *args, **kwargs):
        self.root = None
        
    def _createUi(self):
        self.root = tk.Tk()
        dialogWidth = 400
        self.root.title("WVR Reader")
        frame = tk.Frame(self.root)
        self.label1 = ttk.Label(frame, text="Reading EBML file...")
        self.label2 = ttk.Label(frame, text="")
        self.pb = ttk.Progressbar(frame, length=dialogWidth)
        self.pb.config(maximum=70)
        self.label1.pack(fill=tk.X, anchor="w")
        self.label2.pack(fill=tk.X, anchor="w")
        self.pb.pack(anchor='sw')
        frame.pack(side=tk.TOP)

    def _destroyUi(self):
        self.root.destroy()
        self.root = None

    def start(self, val, count=None, total=None):
        self._createUi()
        pass

    def stop(self, val, count=None, total=None):
        self._destroyUi()

    def update(self, val, count=None, total=None):
        self.label2.config(text="Imported %s samples" % val)
        self.pb.step()
        self.pb.update()

    def __call__(self, val, count=None, total="some"):
        if self.root is None:
            self.start(val, count, total)
        elif val == -1:
            self.stop(val, count, total)
        else:
            self.update(val, count, total)



class LoaderUpdater(ASCIIProgressBar):
    pass

def nullUpdater(*args, **kwargs):
    pass


#===============================================================================
# ACTUAL FILE READING HAPPENS BELOW
#===============================================================================

def createDefaultSensors(doc, defaultSensors):
    """ Given a nested set of dictionaries containing the definition of one or
        more sensors, instantiate those sensors and add them to the dataset
        document.
    """
    for sensorId, sensorInfo in defaultSensors.iteritems():
        sensor = doc.addSensor(sensorId, sensorInfo.get("name", None))
        for channelId, channelInfo in sensorInfo['channels'].iteritems():
            channel = sensor.addChannel(channelId, channelInfo['parser'],
                                        name=channelInfo.get('name',None))
            if 'subchannels' not in sensorInfo:
                continue
            for subChId, subChInfo in sensorInfo['subchannels'].iteritems():
                channel.addSubChannel(subChId, **subChInfo)
    
    

def openFile(filename=testFile, updater=LoaderUpdater, 
             parserTypes=elementParserTypes, defaultSensors=sensors,
             numTics=70, maxBlocks=None):
    """
    """
    global doc    
    
    if updater is None:
        updater = nullUpdater
    else:
        updater = LoaderUpdater(filename=filename)
        
    stream = open(filename, "rb")
    doc = Dataset(stream)
    
    elementParsers = dict([(f.elementName, f(doc)) for f in parserTypes])

    if defaultSensors is not None:
        createDefaultSensors(doc, defaultSensors)         

    doc.addSession()

    count = 0
    events = 0
    
    # Progress display stuff
    filesize = os.path.getsize(filename)
    lastOffset = 0
    ticSize = None
    updater(0, count)

    try:    
        for r in doc.ebmldoc.iterroots():
    #     for r in doc.ebmldoc.roots:
            
            # More progress display stuff
            offset = r.stream.offset
            if ticSize is None:
                dataSize = filesize - r.stream.offset
                ticSize = dataSize / numTics
                dataSize += 0.0
            if offset-lastOffset > ticSize:
                updater(offset/dataSize)
                updater(events)
                lastOffset = offset
    
                
            if r.name in elementParsers:
                added = elementParsers[r.name](r)
                if added is not None:
                    events += added
            else:
                print "unknown block %r, continuing" % r.name
            
            # Emergency ejector seat. Not for production!            
            count += 1
            if maxBlocks is not None and count > maxBlocks:
                break
        
    except IOError:
        doc.fileDamaged = True
        
    doc.endSession()
    
    # finish progress bar
    updater(-1, events)
        
    doc.loading = False
    return doc


import csv
def dumpCsv(data, filename="my_export.csv"):
    """ Experimental CSV export timing.
        Typical time: 0:02:03.247000
    """
    f = open(filename,'wb')
    writer = csv.writer(f)
    t0 = datetime.now()
    writer.writerows(data)
    f.close()
    return datetime.now() - t0



def dumpTestCsv(data, filename="my_export.csv"):
    """ CSV dump with flat data.
        Typical time: 0:01:59.916000
    """
    exportProgressBar = ASCIIProgressBar(action=('Exporting','Exported'), filename=filename)
    idx = 1
    m = len(data)/100
    f = open(filename,'wb')
    writer = csv.writer(f)
    exportProgressBar(0, len(data))
    t0 = datetime.now()
    for d in data:
        # Assumes value is a list
        writer.writerow((d[0],) + d[1])
        idx+=1
        if idx % m == 0:
            exportProgressBar(idx)
    f.close()
    exportProgressBar(-1, len(data))
    return datetime.now() - t0
