'''
Created on Jul 1, 2014

@author: dstokes
'''

from mide_ebml import importer
import dataset
import parsers

# Hard-coded sensor/channel mapping for the Slam Stick Classic.
# TODO: Base default sensors on the device type UID.
default_sensors = {
    0x00: {"name": "ADXL345 Accelerometer", 
           "channels": {
                0x00: {"name": "Accelerometer XYZ",
                       "parser": parsers.AccelerometerParser(),
                       "subchannels":{0: {"name": "X", 
                                          "units":('Acceleration','g'),
                                          "displayRange": (-16.0,16.0),
                                         },
                                      1: {"name": "Y", 
                                          "units":('Acceleration','g'),
                                          "displayRange": (-16.0,16.0),
                                          },
                                      2: {"name": "Z", 
                                          "units":('Acceleration','g'),
                                          "displayRange": (-16.0,16.0),
                                          },
                                    },
                       },
                },
           },
}


def createDefaultSensors(doc, sensors=default_sensors):
    """ Given a nested set of dictionaries containing the definition of one or
        more sensors, instantiate those sensors and add them to the dataset
        document.
    """
    for sensorId, sensorInfo in sensors.iteritems():
        doc.addSensor(sensorId, sensorInfo.get("name", None))
        for chId, chInfo in sensorInfo['channels'].iteritems():
            channel = doc.addChannel(chId, chInfo['parser'],
                                        name=chInfo.get('name',None),
                                        channelClass=dataset.Channel)
            if 'subchannels' not in chInfo:
                continue
            for subChId, subChInfo in chInfo['subchannels'].iteritems():
                channel.addSubChannel(subChId, channelClass=dataset.SubChannel,
                                      sensorId=sensorId,
                                      **subChInfo)



def openFile(stream, parserTypes=None, defaultSensors=default_sensors, 
             name=None, quiet=False):
    """ Create a `Dataset` instance and read the header data (i.e. non-sample-
        data). When called by a GUI, this function should be considered 'modal,' 
        in that it shouldn't run in a background thread, unlike `readData()`. 
        
        For Slam Stick Classic files (which are small), this function actually 
        does the entirety of the import, instead of splitting the work between
        this function and `readData()`.
        
        @todo: Actually split the header reading from the data reading.
            Reading directly from a Slam Stick is slow enough to make a
            difference, even though the files are only 16MB. Low priority.
    """
    # Classic files are small, so the entirety of the file-parsing is done
    # here, instead of splitting it between this and `readData()`. 
    doc = dataset.Dataset(stream)
    if defaultSensors is not None:
        createDefaultSensors(doc, defaultSensors)
    parser = parsers.RecordingParser(doc)
    parser.parse()
    return doc
    
    
def readData(doc, updater=importer.nullUpdater, numUpdates=500, 
             updateInterval=1.0, parserTypes=None, 
             defaultSensors=default_sensors, sessionId=0):
    """ Import the data from a file into a Dataset.
    
        For Slam Stick Classic files, this function is a stub; they are small,
        and all the importing is actually performed by the `openFile()` 
        function.

        @todo: Actually split the header reading from the data reading.
            Reading directly from a Slam Stick is slow enough to make a
            difference, even though the files are only 16MB. Low priority.
    
        @param doc: The Dataset document into which to import the data.
        @keyword updater: A function (or function-like object) to notify as 
            work is done. It should take four keyword arguments: `count` (the 
            current line number), `total` (the total number of samples), `error` 
            (an unexpected exception, if raised during the import), and `done` 
            (will be `True` when the export is complete). If the updater object 
            has a `cancelled` attribute that is `True`, the import will be 
            aborted. The default callback is `None` (nothing will be notified).
        @keyword numUpdates: The minimum number of calls to the updater to be
            made. More updates will be made if the updates take longer than
            than the specified `updateInterval`. 
        @keyword updateInterval: The maximum number of seconds between calls to 
            the updater. More updates will be made if indicated by the specified
            `numUpdates`.
        @keyword parserTypes: A collection of `parsers.ElementHandler` classes.
        @keyword defaultSensors: A nested dictionary containing a default set 
            of sensors, channels, and subchannels. These will only be used if
            the dataset contains no sensor/channel/subchannel definitions. 
    """

    numSamples = len(doc.channels.values()[0].getSession(sessionId)._data)*3
    updater(0)
    updater(count=numSamples, percent=1.0)
    updater(done=True)#, total=eventsRead)
    doc.loading = False
    return doc


def importFile(f, defaultSensors=default_sensors):
    """ Create a new Dataset object and import the data from a Classic file. 
        Primarily for testing purposes. The GUI does the file creation and 
        data loading in two discrete steps, as it will need a reference to 
        the new document before the loading starts.
        @see: `openFile()` and `readData()`
    """
    if isinstance(f, basestring):
        f = open(f, 'rb')
    doc = openFile(f, defaultSensors=defaultSensors)
    readData(doc, defaultSensors=defaultSensors)
    return doc