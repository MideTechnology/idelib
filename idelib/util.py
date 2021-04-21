"""
Utility functions for doing low-level, general-purpose EBML reading and writing.

Note: Most of the functionality that was here is now part of ebmlite. This
    module now contains little besides the 'Attribute' handling functions.

Created on Dec 10, 2013

:author: dstokes

"""

from collections import OrderedDict
import datetime
import time

from ebmlite import loadSchema


# ==============================================================================
# 
# ==============================================================================

def verify(data, schema=None):
    """ Basic sanity-check of data validity. If the data is bad an exception
        will be raised. The specific exception varies depending on the problem
        in the data.
        
        :keyword schema: The full module name of the EBML schema.
        :return: `True`. Any problems will raise exceptions.
    """
    if schema is None:
        schema = loadSchema('mide_ide.xml')
    return schema.verify(data)


# ==============================================================================
# 
# ==============================================================================

def decode_attributes(data, withTypes=False):
    """ Convert a set of Attributes (as a list of dictionaries containing an
        `AttributeName` and one of the Attribute value elements (`IntAttribute`,
        `FloatAttribute`, etc.) to a proper dictionary. Attributes are tagged
        as 'multiple,' so they become lists when the EBML is parsed.
    """
    result = OrderedDict()
    for atts in data:
        k = atts.pop('AttributeName', None)
        if k is None:
            continue
        t, v = list(atts.items())[0]
        if withTypes:
            att = (v, t)
        else:
            att = v
        result.setdefault(k, []).append(att)
    return result

    
def encode_attributes(data):
    """ Construct a set of `Attribute` dicts from a dictionary or list of
        tuples/lists. Each value should be either a simple data type or a
        tuple containing the value and the specific value element name
        (IntAttribute, FloatAttribute, etc.). The value element type will 
        otherwise be inferred.
    """
    datetimeTypes = (datetime.datetime, datetime.date)
    attTypes = ((str, 'UnicodeAttribute'),
                (bytes, 'StringAttribute'),
                (float, 'FloatAttribute'),
                (int, 'IntAttribute'),
                (time.struct_time, 'DateAttribute'),
                (datetimeTypes, 'DateAttribute'))
    
    if isinstance(data, dict):
        data = list(data.items())
    
    result = []
    elementType = None

    for d in data:
        if isinstance(d[1], (tuple, list)) and not isinstance(d[1], time.struct_time):
            k = d[0]
            v, elementType = d[1]
        else:
            k, v = d
            for t, elementType in attTypes:
                if isinstance(v, t):
                    break
                elementType = 'BinaryAttribute'
        
        if elementType == 'DateAttribute':
            if isinstance(v, (int, float)):
                v = int(v)
            elif isinstance(data, datetimeTypes):
                v = int(time.mktime(data.timetuple()))
            elif isinstance(data, time.struct_time):
                v = int(time.mktime(v))
                
        result.append({'AttributeName': k, elementType: v})

    return result
    

def build_attributes(data):
    """ Construct `Attribute` EBML from dictionary or list of key/value pairs. 
        Each value should be either a simple data type or a tuple containing 
        the value and the specific value element name (`IntAttribute`, 
        `FloatAttribute`, etc.). The value element type will otherwise be 
        inferred.
    """
    mideSchema = loadSchema('mide_ide.xml')
    return mideSchema['Attribute'].encode(encode_attributes(data))
