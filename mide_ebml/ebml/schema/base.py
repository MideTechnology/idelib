import abc, os
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO #@UnusedImport (PyLint doesn't like this)
from ..core import read_element_id, read_element_size
from ..core import read_signed_integer, read_unsigned_integer, read_float, read_string, read_unicode_string, read_date



__all__ = ('UnknownElement', 'Element', 'Document', 'INT', 'UINT', 'FLOAT',
           'STRING', 'UNICODE', 'DATE', 'BINARY', 'CONTAINER')


INT, UINT, FLOAT, STRING, UNICODE, DATE, BINARY, CONTAINER = range(0, 8)

READERS = {
    INT: read_signed_integer,
    UINT: read_unsigned_integer,
    FLOAT: read_float,
    STRING: read_string,
    UNICODE: read_unicode_string,
    DATE: read_date,
    BINARY: lambda stream, size: bytearray(stream.read(size))
}


class Stream(object):

    class Substream(object):
        def __init__(self, stream, offset, size):
            self.stream = stream
            self.offset = offset
            self.size = size

        def read(self, size):
            current_offset = self.tell()
            if current_offset == 0:
                self.stream.seek(self.offset)
                if size > self.size:
                    return self.stream.read(self.size)
                else:
                    return self.stream.read(size)
            else:
                if current_offset > self.size:
                    return b''
                else:
                    max_size = (self.size - current_offset)
                    if size <= max_size:
                        return self.stream.read(size)
                    else:
                        return self.stream.read(max_size)

        def seek(self, offset, whence=os.SEEK_SET):
            if whence == os.SEEK_SET:
                desired_offset = self.offset + offset
            elif whence == os.SEEK_CUR:
                desired_offset = self.stream.tell() + offset
            elif whence == os.SEEK_END:
                desired_offset = self.offset + self.size + offset

            if not self.offset <= desired_offset:
                raise IOError("Bad offset for seek()")

            self.stream.seek(desired_offset, os.SEEK_SET)

        def tell(self):
            stream_offset = self.stream.tell()
            if stream_offset <= self.offset:
                return 0
            else:
                return stream_offset - self.offset

        def substream(self, offset, size):
            if offset + size <= self.size:
                return self.stream.substream(self.offset + offset, size)
            else:
                raise IOError("Bad offset/size for substream")

        def __getitem__(self, key):
            if isinstance(key, (int, long)):
                self.seek(key)
                return self.read(1)
            elif isinstance(key, slice):
                if key.step is not None:
                    raise IndexError("Slices with steps not permitted")
                try:
                    return self.substream(key.start, (key.stop - key.start))
                except TypeError:
                    # key.start or key.stop is probably None
                    raise IndexError("Slice had no start and/or stop")
            else:
                raise TypeError("Bad type for index/key: %r" % key)

    def __init__(self, file_like):
        self.file = file_like
        self.file.seek(0, os.SEEK_END)
        self.size = self.file.tell()
        self.file.seek(0, os.SEEK_SET)
        self.substreams = {}

    def read(self, size):
        return self.file.read(size)

    def seek(self, offset, whence=os.SEEK_SET):
        return self.file.seek(offset, whence)

    def tell(self):
        return self.file.tell()

    def substream(self, offset, size):
        if offset + size <= self.size:
            # XXX: TEST: Caching disabled; it doesn't seem to do much good.
#             k = (offset, size)
#             if k not in self.substreams:
#                 self.substreams[k] = self.Substream(self, offset, size)
#             return self.substreams[k]
            return self.Substream(self, offset, size)
        else:
            raise IOError("Bad offset/size for substream")

    def __getitem__(self, key):
        if isinstance(key, (int, long)):
            self.seek(key)
            return self.read(1)
        elif isinstance(key, slice):
            if key.step is not None:
                raise IndexError("Slices with steps not permitted")
            try:
                return self.substream(key.start, (key.stop - key.start))
            except TypeError:
                # key.start or key.stop is probably None
                raise IndexError("Slice had no start and/or stop")
        else:
            raise TypeError("Bad type for index/key: %r" % key)


class Element(object):
    __metaclass__ = abc.ABCMeta

    id = abc.abstractproperty()
    name = abc.abstractproperty()
    type = abc.abstractproperty()
    default = None
    children = ()
    mandatory = False
    multiple = False

    _childDict = {}

    def __init__(self, document, stream):
        self.document = document
        self.stream = stream

    @property
    def value(self):
        try:
            return self.cached_value
        except AttributeError:
            if self.type == CONTAINER:
                self.cached_value = read_elements(self.body_stream, self.document, self._childDict)
            else:
                try:
                    self.cached_value = READERS[self.type](self.body_stream, self.body_size)
                except KeyError:
                    self.cached_value = None
        return self.cached_value

    @property
    def id_size(self):
        try:
            return self.cached_id_size
        except AttributeError:
            self.stream.seek(0)
            _, self.cached_id_size = read_element_id(self.stream)
        return self.cached_id_size

    @property
    def size_size(self):
        try:
            return self.cached_size_size
        except AttributeError:
            self.stream.seek(self.id_size)
            _, self.cached_size_size = read_element_size(self.stream)
        return self.cached_size_size

    @property
    def head_size(self):
        return self.id_size + self.size_size

    @property
    def body_size(self):
        return self.size - self.head_size

    @property
    def body_stream(self):
        return self.stream.substream(self.head_size, self.body_size)

    @property
    def size(self):
        return self.stream.size


class UnknownElement(Element):
    id = None
    name = 'Unknown'
    type = BINARY

    def __init__(self, document, stream, id_):
        self.id = id_
        super(UnknownElement, self).__init__(document, stream)


def read_elements(stream, document, children):
    elements = []
    size = stream.size
    while size:
        element_offset = stream.size - size
        stream.seek(element_offset)
        element_id, element_id_size = read_element_id(stream)
        element_size, element_size_size = read_element_size(stream)
        element_stream_size = element_id_size + element_size_size + element_size
        element_stream = stream.substream(element_offset, element_stream_size)
        size -= element_stream_size

#         element_class = None
#         for child in (children + document.globals):
#             if child.id == element_id:
#                 element_class = child
#                 break

        element_class = children.get(element_id, None)

        if element_class is None:
            element = UnknownElement(document, element_stream, element_id)
        else:
            element = element_class(document, element_stream)

        elements.append(element)
    return elements


def iter_elements(stream, document, children):
    size = stream.size
    while size:
        element_offset = stream.size - size
        stream.seek(element_offset)
        element_id, element_id_size = read_element_id(stream)
        element_size, element_size_size = read_element_size(stream)
        element_stream_size = element_id_size + element_size_size + element_size
        element_stream = stream.substream(element_offset, element_stream_size)
        size -= element_stream_size

#         element_class = None
#         for child in (children + document.globals):
#             if child.id == element_id:
#                 element_class = child
#                 break

        element_class = children.get(element_id, None)

        if element_class is None:
            element = UnknownElement(document, element_stream, element_id)
        else:
            element = element_class(document, element_stream)

        yield(element)


class Document(object):
    __metaclass__ = abc.ABCMeta

    type = abc.abstractproperty()
    version = abc.abstractproperty()
    children = ()
    globals = ()

    def __init__(self, file_like):
        self.stream = Stream(file_like)
        self._roots = None

    @property
    def roots(self):
        if self._roots is None:
            self._roots = []
            # This won't totally fail if the file was damaged
            for r in iter_elements(self.stream, self, self._childDict):
                self._roots.append(r)
        return self._roots


    def iterroots(self):
        """ Iterate over the document's root elements. Allows use of a
            damaged file; just catch an `IOError` in the root-reading loop.
        """
        return iter_elements(self.stream, self, self._childDict)
