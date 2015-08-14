'''
Module for reading and writing 'Slam Stick Classic' configuration files.

@todo: Move everything into SSXViewer/devices.py ? The other recorder-specific
    stuff resides there, since it's not really part of the data. Or do the
    opposite and move more of the recorder-specific stuff into the library.

From the firmware `configs.h` file:
-----------------------------------
The config file is read/written through the margarine layer and so contains 
some dynamic content. Please read the descriptions below carefully!

Key to the below:

Items with an (R) and/or (W) are dynamically handled. (R) = Read (reading this 
value returns dynamic / custom value), (W) = Write (writing this value triggers 
a realtime action). 

Anything marked "reserved" or "future" etc., is unimplemented. To maintain 
back/forward compatibility, these must not be removed (even if they will never 
be implemented), nor may new values be added except at the end or replacing an 
unimplemented value (that is, the byte positions of any currently-used config 
item may not change!).

Items marked with [REV2] indicate features only supported by the Rev2+ firmware 
(2014 refresh of Slam Stick).


@var CONFIG_FIELDS: An `OrderedDict` of tuples containing field names and the
    `struct` format for parsing them. These are in the expected order.
@var CONFIG_PARSER: A `struct.Struct` to parse (or pack) a config file's
    contents.
'''
from collections import OrderedDict
from datetime import datetime
import struct
import time

# Comments are (mostly) verbatim from the C code.
CONFIG_FIELDS = OrderedDict((
    ('MAGIC_NUMBER', '4s'),       # Must be "VC20" to indicate valid Slam Stick config file
    ('CONFIGFILE_VER', 'H'),      # 0x0001 for rev1, 0x0002 for rev2 support
    ('HWREV', 'H'),               # (R) Hardware revision code (e.g. 0x0001 for rev1)
    ('SWREV', 'H'),               # (R) Firmware revision code (e.g. 0x0001 for rev1)
    ('VERSION_STR', '8s'),        # (R) Firmware-reported version string. x.yUz where x.y = major/minor version, z = storage capacity. E.g. "1.0U4" for 4MByte device.
    
    # offset: 18
    ('SYSUID_RESERVE', '8s'),     # reserved for future use - hardcoded hardware ID
    ('USERUID_RESERVE', '8s'),    # space for user-set hardware ID
    
    # Offset: 34
    ('CALOFFSX', 'h'),            # 
    ('CALOFFSY', 'h'),            # 
    ('CALOFFSZ', 'h'),            # 
    ('CALGAINX', 'H'),            # if not present; else gain = val+32767/65535; gain scaling rage ~ 0.5x - 1.5x
    ('CALGAINY', 'H'),            # ...
    ('CALGAINZ', 'H'),            # 
    ('RTCCAL', 'B'),              # 
    
    # offset: 47
    ('DATA_AREA_UNCLEAN', 'B'),   # flag if data area is cleanly erased / written (formerly DATA_ERASED). 0 = clean; 1 = erasing (interrupted during erase).
    ('BATT_STATUS', 'B'),         # reserved for future use. (R)
    ('X86_PADDING', 'B'),         # dummy byte; enforce word alignment for following variables
    ('SELFTEST', 'H'),            # reserved for future use. (R)
    ('REALTIME_X', 'h'),          # reserved for future use. (R)
    ('REALTIME_Y', 'h'),          # reserved for future use. (R)
    ('REALTIME_Z', 'h'),          # reserved for future use. (R)
    
    # offset: 58
    ('PRESERVE_DATA', 'B'),       # Unimplemented. Initial intention was a mechanism to prevent accidental erase operations to preserve important data (for rental "mail back for processing" business model). Not relevant now that the user buys it and can download on their own...
    ('CONFIG_FLAGS', 'B'),        # [x x x x x x x x]
                                  # 7: CONFIG_FLAGS_DEFAULT_CFG: allow to determine default (wiped?) vs. customized cfgs. 1=default; 0=customized. NOTE: The remaining bits are only valid if DEFAULT_CFG = 0.
                                  # 6: CONFIG_FLAGS_AUTO_REARM: If 'customized', 1=enable auto-ream, 0=disable auto re-arm. [REV2]
                                  # ^^^ Bit 6 added 20140508 . Confirmed as of this date the Python, Matlab and C configurators have all been initializing the remaining bits to 0, so "0"=disabled is a safe default.
    # offset: 60
    ('RTCC_TIME', '7s'),          # (R) Get time (W) Set time to this value if indicated by WR_RTCC byte (see below) [REV2]
    
    # offset: 67
    ('BW_RATE_PWR', 'B'),         # Sample rate code (bits 3..0) + power save bit (bit 4), directly matching the ADXL345's BW_RATE register contents. The power save bit doesn't really save enough to be relevant for us.
    ('RECORD_DELAY', 'H'),        # Recording pre-delay in units of 2 seconds.
                                  # NOTE: Conversion from/to 2 second units is done automatically at read/write time! 
    ('SAMPLES_PER_TRIGGER', 'H'), # Terminate recording if this many (XYZ) samples have been recorded (actual number of samples recorded will be rounded up to the nearest sector).
    ('SECONDS_PER_TRIGGER', 'H'), # Terminate recording if this many seconds have elapsed since start (actual number of samples recorded will be rounded up to the nearest sector). In units of 2 seconds.
                                  # NOTE: Conversion from/to 2 second units is done automatically at read/write time! 

    # offset: 74
    ('TRIGGER_FLAGS', '2s'),      # Four nibbles, MSB..LSB, provide trigger rules for each of 4 possible trigger sources (extA, extB, shock, RTCC).
                                  # UNIMPLEMENTED - for extA,B: [XXXX] = [enabled, edge/level FUTURE, rising/falling (edge), terminateBy]  *terminateByX indicates this signal can both start and stop the recording.
                                  # for shock: [enabled, x, x, x]
                                  # for RTCC Alarm: [enabled, x, x, x] [REV2]
    ('TRIG_THRESH_ACT', 'B'),     # G-level magnitude (unsigned) of g-level trigger; 62.5 mg/LSB. WARNING: Due to noise, settings at/near 0 may cause undesired operation.
    ('TRIG_THRESH_INACT', 'B'),   # reserved for future
    ('TRIG_TIME_INACT', 'B'),     # reserved for future
    ('TRIG_SLEEP_MODE', 'B'),     # POWER_CTL reg. Sets full resolution g-level wait or nap mode. 0x00 = full; (0x04, 0x05, 0x06, 0x07) = (8, 4, 2, 1)Hz nap mode. All other values reserved.
    ('TRIG_ACT_INACT_REG', 'B'),  # Register setting of ACT_INACT_CTL reg. Bits 7~0 are [AXYZxxxx]. A: 1=AC coupled (else DC coupled), XYZ: 1= axis participates, else axis is ignored for g-level trigger.
    ('TRIG_THRESH_FF', 'B'),      # 
    ('TRIG_TIME_FF', 'B'),        # using "TRIG_" names because register names already taken in adxl345.h
    ('TRIG_RESERVED_TAP_FF', '5s'), # reserved for (remaining) tap and freefall reg settings, if ever desired
    
    # REV2 fields. A fresh config file should always be 512b, so these will
    # just be zero if a REV1 file is read.
    # offset: 88
    ('RTCC_ENA', 'B'),            # (W)Enables the RTCC module on the device (R)Module is enabled. [REV2]
    ('RTCC_IS_SET', 'B'),         # (R) RTCC value is set / considered valid [REV2]
    ('WR_RTCC', 'B'),             # (W) if byte value = 0x5A, the RTCC_TIME[7] in this file (above) is written to the hardware RTCC, and the peripheral enabled. [REV2]
    ('TZ_OFFSET', 'b'),           # Timezone offset from UTC in integer hours. If 0, RTCC/alarm are in local time (and/or local time == UTC)
    ('ALARM_TIME', '7s'),         # Same format as RTCC_TIME[7], except the 1st byte is reserved/unimplemented: alarm does not use year. MUST be set to a valid alarm time if triggering on RTCC enabled in TRIGGER_FLAGS.
    ('REPEATS', 'B'),             # Number of times to repeat. 0 = single-shot, 255 = 255 repeats (256 total alarms). Ignored if CHIME_EN is set.
    ('ROLLPERIOD', 'B'),          # Alarm rollover period (every minute, etc.). Bit patterns defined in rtcc.h.
    ('CHIME_EN', 'B'),            # Bit 0 = "chime mode" (alarm repeats indefinitely; REPEATS setting ignored).
    
    # The firmware REV2 only supports fields up to CHIME_EN.
    # offset: 102
    ('_padding', '26s'),
    
    # User-defined fields, not used by the recorder itself
    # offset 128
    ('USER_NAME', '64s'),
    ('USER_NOTES', '256s'),
))

CONFIG_PARSER = struct.Struct('<' + "".join(CONFIG_FIELDS.values()))

def getFieldOffsets(fields=CONFIG_FIELDS):
    """ Get the offsets from the start of the file for each configuration
        field. For testing/debugging/verification.
    """
    offset = 0
    result = OrderedDict()
    for k,v in fields.iteritems():
        result[k] = offset
        offset += struct.calcsize(v)
    return result

#===============================================================================
# 
#===============================================================================

def packTime(t=None):
    """ Convert a time into the BCD format used in the config file.
        
        @keyword t: The time to encode, or `None` for the current time.
        @return: A string of 7 bytes (BCD encoded year, month, day, day of week,
            hour, minute, second).
    """
    def bin2bcd(val):
        return chr((int(val/10)<<4) + (val%10))
    
    if t == 0:
        return '\0' * 7
    
    if t is None:
        t = datetime.now().timetuple()
    elif isinstance(t, datetime):
        t = t.timetuple()
    else:
        t = time.gmtime(t)
    
    result = (t[0]-2000, t[1], t[2], t[6], t[3], t[4], t[5])
    return ''.join(map(bin2bcd, result))


def unpackTime(t):
    """ Convert an encoded time from the config file into a standard
        `datetime.datetime` object.
        
        @param t: The encoded time as a 7-byte string.
        @return: The time as a `datetime.datetime`.
    """
    def bcd2bin(val):
        return (val & 0x0F) + ((val >> 4) * 10)
    
    d = map(bcd2bin, bytearray(t))
    try:
        return datetime(d[0]+2000, d[1], d[2], d[4], d[5], d[6])
    except ValueError:
        return 0

def packStr(s):
    if not s:
        return ''
    if isinstance(s, bytearray):
        return str(s)
    return s.encode('utf-8')

def unpackStr(s):
    if not isinstance(s, basestring):
        return ''
    if '\x00' in s:
        s = s.split('\x00')[0]
    return s.rstrip('\x00\xff').decode('utf-8')


def _clampVal(v, loVal, hiVal):
    if v is None:
        return 0
    return max(loVal, min(hiVal, v))


#===============================================================================
# 
#===============================================================================

CONFIG_ENCODERS = {'RECORD_DELAY': lambda x: _clampVal(int(x/2), 0, 2**16-2),
                   'SECONDS_PER_TRIGGER': lambda x: _clampVal(int(x/2), 0, 2**16-2),
                   'ALARM_TIME': packTime,
                   'RTCC_TIME': packTime,
                   'TRIGGER_FLAGS': str,
                   'TRIG_RESERVED_TAP_FF': str,
                   'SYSUID_RESERVE': str,
                   'USERUID_RESERVE': str,
                   'TRIG_THRESH_ACT': lambda x: _clampVal(int(x/0.0625), 0, 254),
                   'USER_NAME': packStr,
                   'USER_NOTES': packStr,
                   '_padding': str,
                   }
CONFIG_DECODERS = {'RECORD_DELAY': lambda x: x*2,
                   'SECONDS_PER_TRIGGER': lambda x: x*2,
                   'ALARM_TIME': unpackTime,
                   'RTCC_TIME': unpackTime,
                   'TZ_OFFSET': lambda x: 0 if x > 24 else x,
                   'TRIGGER_FLAGS': bytearray,
                   'TRIG_RESERVED_TAP_FF': bytearray,
                   'SYSUID_RESERVE': unpackStr,
                   'USERUID_RESERVE': unpackStr,
                   'TRIG_THRESH_ACT': lambda x: x*0.0625,
                   'USER_NAME': unpackStr,
                   'USER_NOTES': unpackStr,
                   '_padding': unpackStr,
                   }

GENERIC_ENCODERS = {'b': lambda x: _clampVal(x, -128, 127),
                    'B': lambda x: _clampVal(x, 0, 2**8-2),
                    'h': lambda x: _clampVal(x, -32768, 32767),
                    'H': lambda x: _clampVal(x, 0, 2**16-2),
                    }

#===============================================================================
# 
#===============================================================================

def decodeConfig(data):
    """ Apply the `CONFIG_DECODERS` to the configuration data. Used internally
        after reading a config file.
    """ 
    result = data.copy()
    for name, decoder in CONFIG_DECODERS.iteritems():
        if name in result:
            result[name] = decoder(result[name])
    return result
            

def encodeConfig(data):
    """ Apply the `CONFIG_ENCODERS` to the configuration data. Used internally
        before writing a config file.
    """ 
    result = data.copy()
    for name, dtype in CONFIG_FIELDS.iteritems():
        val = result[name]
        if name in CONFIG_ENCODERS:
            # Use special case encoder for the data
            result[name] = CONFIG_ENCODERS[name](val)
        elif dtype in GENERIC_ENCODERS:
            # Use generic encoder for the type (out of range values can break
            # a struct).
            result[name] = GENERIC_ENCODERS[dtype](val)
    return result


#===============================================================================
# 
#===============================================================================

def verify(data):
    """ Stub for config file verification. 
    """
    if data.keys() != CONFIG_FIELDS.keys():
        return False
    try:
        CONFIG_PARSER.pack(*encodeConfig(data).values())
    except struct.error:
        return False
    return True


def readConfig(source):
    """ Read configuration data from a file, presumably on a Slam Stick Classic
        device.
        
        @param source: Either a (file-)stream from which to read, or the 
            path/name of a file to read.
    """
    if isinstance(source, basestring):
        with open(source, 'rb') as f:
            return readConfig(f)
        
    data = source.read(CONFIG_PARSER.size)
    return decodeConfig(OrderedDict(zip(CONFIG_FIELDS.keys(), 
                                        CONFIG_PARSER.unpack_from(data))))


def writeConfig(dest, data, validate=True):
    """ Save the configuration data to a file, presumably on a Slam Stick
        Classic device. 
        
        @param dest: Either a (file-)stream to which to write, or the path/name
            of a file to which to save.
        @param data: An ordered dictionary with the configuration data
        @keyword validate: If `True`, the data is validated before being saved.
            Doesn't do anything here; validation just packs the data, which is
            being done anyway.
        @return: `True` if the data was saved, `False` if not.
    """
    if isinstance(dest, basestring):
        with open(dest, 'wb') as f:
            return writeConfig(f, data, validate)
    
    if validate and not verify(data):
        return False
    
    try:
        c = CONFIG_PARSER.pack(*encodeConfig(data).values())
        dest.write(c)
    except struct.error:
        return False
    
    return True


