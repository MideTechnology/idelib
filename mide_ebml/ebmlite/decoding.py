"""
"""

import datetime
import struct

_struct_uint32 = struct.Struct(">I")
_struct_uint64 = struct.Struct(">Q")
_struct_int64 = struct.Struct(">q")
_struct_float32 = struct.Struct(">f")
_struct_float64 = struct.Struct(">d")


def decode_vint_length(byte):
    """ Extract the encoded size from an initial byte.

        @return: The size, and the byte with the size removed.
    """
    # The brute force version. 370% faster on average.
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


def decode_id_length(byte):
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

    length, _ = decode_vint_length(byte)
    raise IOError('Invalid length for ID: %d' % length)


def read_element_id(stream):
    """ Read an element ID from a file (or file-like) stream.

        @param stream: The source file-like object.
        @return: The decoded element ID and its length in bytes.
    """
    ch = stream.read(1)
    byte = ord(ch)
    length, id_ = decode_id_length(byte)
    if length > 4:
        raise IOError('Cannot decode element ID with length > 4.')
    if length > 1:
        id_ = _struct_uint32.unpack((ch + stream.read(length-1)).rjust(4,'\x00'))[0]
    return id_, length


def read_element_size(stream):
    """ Read an element size from a file (or file-like) stream.

        @param stream: The source file-like object.
        @return: The decoded size (or `None`) and the length of the
            descriptor in bytes.
    """
    ch = stream.read(1)
    byte = ord(ch)
    length, size = decode_vint_length(byte)

    if length > 1:
        size = _struct_uint64.unpack((chr(size) + stream.read(length-1)).rjust(8,'\x00'))[0]

    if size == (2**(7*length)) - 1:
        size = None

    return size, length


def read_unsigned_integer(stream, size):
    """

    Reads an encoded unsigned integer value from a file-like object.

    :arg stream: the file-like object
    :arg size: the number of bytes to read and decode
    :type size: int
    :returns: the decoded unsigned integer value
    :rtype: int

    """

    if size == 0:
        return 0
    data = stream.read(size)
    return _struct_uint64.unpack_from(data.rjust(_struct_uint64.size,'\x00'))[0]


def read_signed_integer(stream, size):
    """

    Reads an encoded signed integer value from a file-like object.

    :arg stream: the file-like object
    :arg size: the number of bytes to read and decode
    :type size: int
    :returns: the decoded signed integer value
    :rtype: int

    """

    if size == 0:
        return 0
    data = stream.read(size)
    if ord(data[0]) & 0b10000000:
        pad = '\xff'
    else:
        pad = '\x00'
    return _struct_int64.unpack_from(data.rjust(_struct_int64.size,pad))[0]



def read_float(stream, size):
    """

    Reads an encoded floating point value from a file-like object.

    :arg stream: the file-like object
    :arg size: the number of bytes to read and decode (must be 0, 4, or 8)
    :type size: int
    :returns: the decoded floating point value
    :rtype: float

    """

    if size == 4:
        return _struct_float32.unpack(stream.read(size))[0]
    if size == 8:
        return _struct_float64.unpack(stream.read(size))[0]
    if size == 0:
        return 0.0

    raise IOError('Cannot read floating point values with lengths other than 0, 4, or 8 bytes.')



def read_string(stream, size):
    """

    Reads an encoded ASCII string value from a file-like object.

    :arg stream: the file-like object
    :arg size: the number of bytes to read and decode
    :type size: int
    :returns: the decoded ASCII string value
    :rtype: str

    """

    if size == 0:
        return ''

    value = stream.read(size)
    value = value.partition('\x00')[0]
    return value


def read_unicode_string(stream, size):
    """

    Reads an encoded unicode string value from a file-like object.

    :arg stream: the file-like object
    :arg size: the number of bytes to read and decode
    :type size: int
    :returns: the decoded unicode string value
    :rtype: unicode

    """

    if size == 0:
        return u''

    data = stream.read(size)
    data = data.partition('\x00')[0]
    return unicode(data, 'utf_8')


def read_date(stream, size):
    """

    Reads an encoded date (and time) value from a file-like object.

    :arg stream: the file-like object
    :arg size: the number of bytes to read and decode (must be 8)
    :type size: int
    :returns: the decoded date (and time) value
    :rtype: datetime

    """

    if size != 8:
        raise IOError('Cannot read date values with lengths other than 8 bytes.')
    data = stream.read(size)
    nanoseconds = _struct_int64.unpack(data)[0]
    delta = datetime.timedelta(microseconds=(nanoseconds // 1000))
    return datetime.datetime(2001, 1, 1, tzinfo=None) + delta



def encodeId(val):
    return _struct_uint32.pack(val).lstrip('\x00')


LENGTHS = [0,
           0x80,
           0x4000,
           0x200000,
           0x10000000,
           0x0800000000,
           0x040000000000,
           0x02000000000000,
           0x0100000000000000]

def getLength(val):
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

def encodeUInt(val, length=None)
    length = getLength(val) if length is None else length
    mask = LENGTHS[length]
    return _struct_uint64.pack(val | mask)[-length:]

def encodeInt(val, length=None):
    length = getLength(abs(val)) if length is None else length
    mask = LENGTHS[length]
    v = _struct_uint64.unpack(_struct_int64.pack(val)) | mask
    return _struct_uint64.pack(v)[-length:]
