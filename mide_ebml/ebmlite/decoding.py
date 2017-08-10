"""
"""

import datetime
import struct
import sys

_struct_uint32 = struct.Struct(">I")
_struct_uint64 = struct.Struct(">Q")
_struct_int64 = struct.Struct(">q")
_struct_float32 = struct.Struct(">f")
_struct_float64 = struct.Struct(">d")

DEFAULT_FLOAT_SIZE = 4 if sys.maxsize <= 2147483647 else 8

#===============================================================================
#--- Reading and Decoding
#===============================================================================

def decodeIntLength(byte):
    """ Extract the encoded size from an initial byte.

        @return: The size, and the byte with the size removed (it is the first
            byte of the value).
    """
    # An inelegant implementation, but it's fast.
    if byte >= 128:
        return 1, byte & 0b1111111
    if byte >= 64:
        return 2, byte & 0b111111
    if byte >= 32:
        return 3, byte & 0b11111
    if byte >= 16:
        return 4, byte & 0b1111
    if byte >= 8:
        return 5, byte & 0b111
    if byte >= 4:
        return 6, byte & 0b11
    if byte >= 2:
        return 7, byte & 0b1
    return 8, 0


def decodeIDLength(byte):
    """ Extract the encoded ID size from an initial byte.

        @return: The size and the original byte (it is part of the ID).
    """
    if byte >= 128:
        return 1, byte
    if byte >= 64:
        return 2, byte
    if byte >= 32:
        return 3, byte
    if byte >= 16:
        return 4, byte

    length, _ = decodeIntLength(byte)
    raise IOError('Invalid length for ID: %d' % length)


def readElementID(stream):
    """ Read an element ID from a file (or file-like) stream.

        @param stream: The source file-like object.
        @return: The decoded element ID and its length in bytes.
    """
    ch = stream.read(1)
    length, id_ = decodeIDLength(ord(ch))

    if length > 4:
        raise IOError('Cannot decode element ID with length > 4.')
    if length > 1:
        id_ = _struct_uint32.unpack((ch + stream.read(length-1)).rjust(4,'\x00'))[0]
    return id_, length


def readElementSize(stream):
    """ Read an element size from a file (or file-like) stream.

        @param stream: The source file-like object.
        @return: The decoded size (or `None`) and the length of the
            descriptor in bytes.
    """
    ch = stream.read(1)
    length, size = decodeIntLength(ord(ch))

    if length > 1:
        size = _struct_uint64.unpack((chr(size) + stream.read(length-1)).rjust(8,'\x00'))[0]

    if size == (2**(7*length)) - 1:
        # EBML 'unknown' size
        size = None

    return size, length


def readUInt(stream, size):
    """ Read an unsigned integer from a file (or file-like) stream.

        @param stream: The source file-like object.
        @return: The decoded value.
    """

    if size == 0:
        return 0
    data = stream.read(size)
    return _struct_uint64.unpack_from(data.rjust(_struct_uint64.size,'\x00'))[0]


def readInt(stream, size):
    """ Read a signed integer from a file (or file-like) stream.

        @param stream: The source file-like object.
        @return: The decoded value.
    """

    if size == 0:
        return 0
    data = stream.read(size)
    if ord(data[0]) & 0b10000000:
        pad = '\xff'
    else:
        pad = '\x00'
    return _struct_int64.unpack_from(data.rjust(_struct_int64.size,pad))[0]


def readFloat(stream, size):
    """ Read an floating point value from a file (or file-like) stream.

        @param stream: The source file-like object.
        @return: The decoded value.
    """
    if size == 4:
        return _struct_float32.unpack(stream.read(size))[0]
    if size == 8:
        return _struct_float64.unpack(stream.read(size))[0]
    if size == 0:
        return 0.0

    raise IOError('Cannot read floating point values with lengths other than 0, 4, or 8 bytes.')


def readString(stream, size):
    """ Read an ASCII string from a file (or file-like) stream.

        @param stream: The source file-like object.
        @return: The decoded value.
    """


    if size == 0:
        return ''

    value = stream.read(size)
    value = value.partition('\x00')[0]
    return value


def readUnicode(stream, size):
    """ Read an UTF-8 encoded stringfrom a file (or file-like) stream.

        @param stream: The source file-like object.
        @return: The decoded value.
    """

    if size == 0:
        return u''

    data = stream.read(size)
    data = data.partition('\x00')[0]
    return unicode(data, 'utf_8')


def readDate(stream, size):
    """ Read an EBML encoded date (nanoseconds since UTC 2001-01-01T00:00:00)
        from a file (or file-like) stream.

        @param stream: The source file-like object.
        @return: The decoded value.
    """
    if size != 8:
        raise IOError('Cannot read date values with lengths other than 8 bytes.')
    data = stream.read(size)
    nanoseconds = _struct_int64.unpack(data)[0]
    delta = datetime.timedelta(microseconds=(nanoseconds // 1000))
    return datetime.datetime(2001, 1, 1, tzinfo=None) + delta


#===============================================================================
#--- Encoding
#===============================================================================

def encodeId(val, length=None):
    """ Encode an element ID.

        @param val: The EBML ID to encode.
        @keyword length: An explicit length for the encoded data. A `ValueError`
            will be raised if the length is too short to encode the value.
    """
    if length is not None:
        if length <= 0 or length >= 8:
            raise ValueError("Cannot encode an ID to length %d" % length)
    return encodeUInt(val, length)


def encodeUInt(val, length=None):
    """ Encode an unsigned integer.

        @param val: The unsigned integer value to encode.
        @keyword length: An explicit length for the encoded data. A `ValueError`
            will be raised if the length is too short to encode the value.
    """
    packed = _struct_uint64.pack(val).lstrip('\x00')
    if length is None:
        return packed
    if len(packed) > length:
        raise ValueError("Encoded length (%d) greater than specified length (%d)" %
                         (len(packed), length))
    return packed.rjust(length, '\x00')


def encodeInt(val, length=None):
    """ Encode a signed integer.

        @param val: The signed integer value to encode.
        @keyword length: An explicit length for the encoded data. A `ValueError`
            will be raised if the length is too short to encode the value.
    """
    pad = "\xff" if val < 0 else "\x00"
    packed = _struct_int64.pack(val).lstrip(pad)
    if length is None:
        return packed
    if len(packed) > length:
        raise ValueError("Encoded length (%d) greater than specified length (%d)" %
                         (len(packed), length))
    return packed.rjust(length, pad)


def encodeFloat(val, length=None):
    """ Encode a floating point value.

        @param val: The floating point value to encode.
        @keyword length: An explicit length for the encoded data. Must be
            `None`, 0, 4, or 8; otherwise, a `ValueError` will be raised.
    """
    if length is None:
        if val is None or val == 0.0:
            return ''
        else:
            length = DEFAULT_FLOAT_SIZE

    if length == 0:
        return ''
    if length == 4:
        return _struct_float32.pack(val)
    elif length == 8:
        return _struct_float64.pack(val)
    else:
        raise ValueError("Cannot encode float of length %d; only 0, 4, or 8" % length)


def encodeString(val, length=None):
    """ Encode an ASCII string.

        @param val: The string (or bytearray) to encode.
        @keyword length: An explicit length for the encoded data. The result
            will be truncated if the length is less than that of the original.
    """
    if val is None:
        val = ''
        vlen = 0
    else:
        vlen = len(val)

    if length is None:
        return val
    elif vlen < length:
        return val.ljust(length, '\x00')
    else:
        return val[:length]


def encodeUnicode(val, length=None):
    """ Encode a Unicode string.

        @param val: The Unicode string to encode.
        @keyword length: An explicit length for the encoded data. The result
            will be truncated if the length is less than that of the original.
    """
    return encodeString(val.encode('utf_8'), length)


def encodeDate(val, length=None):
    """ Encode a `datetime` object as an EBML date (i.e. nanoseconds since
        2001-01-01T00:00:00).

        @param val: The `datetime.datetime` object value to encode.
        @keyword length: An explicit length for the encoded data. Must be
            `None` or 8; otherwise, a `ValueError` will be raised.
    """
    if length is None:
        length = 8
    elif length != 8:
        raise ValueError("Dates must be of length 8")

    if val is None:
        val = datetime.datetime.utcnow()

    delta = val - datetime.datetime(2001, 1, 1, tzinfo=None)
    nanoseconds = (delta.microseconds +
                   ((delta.seconds + (delta.days * 86400)) * 1000000)) * 1000
    return encodeInt(nanoseconds, length)


LENGTH_PREFIXES = [0,
                   0x80,
                   0x4000,
                   0x200000,
                   0x10000000,
                   0x0800000000,
                   0x040000000000,
                   0x02000000000000,
                   0x0100000000000000
                   ]

def getLength(val):
    """ Calculate the encoded length of a value.
    """
    if val <= 126:
        return 1
    elif val <= 16382:
        return 2
    elif val <= 2097150:
        return 3
    elif val <= 268435454:
        return 4
    elif val <= 34359738366L:
        return 5
    elif val <= 4398046511102L:
        return 6
    elif val <= 562949953421310L:
        return 7
    else:
        return 8


def encodeSize(val, length=None):
    """ Encode an element size.
    """
    length = getLength(val) if length is None else length
    try:
        prefix = LENGTH_PREFIXES[length]
        return encodeUInt(val|prefix, length)
    except IndexError:
        raise ValueError("Cannot encode element size %d" % length)
