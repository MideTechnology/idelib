'''
Created on Nov 8, 2013

@author: dstokes
'''

import threading

class ThreadAwareFile(object):
    """ A 'replacement' for the standard file stream that supports reading
        by multiple threads. Each thread actually gets its own stream. This
        functionality is transparent.
    """
    
    def __init__(self, *args, **kwargs):
        ident = threading.currentThread().ident
        self.initArgs = args[:]
        self.initKwargs = kwargs.copy()
        self.threads = {ident: file(*args, **kwargs)}
        self.forceIdent = None
        
       
    def getIdent(self):
        if self.forceIdent is not None:
            return self.forceIdent
        return threading.currentThread().ident


    def getThreadStream(self):
        ident = self.getIdent()
        if ident not in self.threads:
            fp = file(*self.initArgs, **self.initKwargs)
            self.threads[ident] = fp
            return fp
        return self.threads[ident]

    def closeAll(self):
        for v in self.threads.itervalues():
            v.close()

#     def __enter__(self, *args, **kwargs):
#         return self.getThreadStream().__enter__(*args, **kwargs)
# 
#     def __exit__(self, *args, **kwargs):
#         return self.getThreadStream().__exit__(*args, **kwargs)

    def __format__(self, *args, **kwargs):
        return self.getThreadStream().__format__(*args, **kwargs)

    def __hash__(self, *args, **kwargs):
        return self.getThreadStream().__hash__(*args, **kwargs)

    def __iter__(self, *args, **kwargs):
        return self.getThreadStream().__iter__(*args, **kwargs)

    def __reduce__(self, *args, **kwargs):
        return self.getThreadStream().__reduce__(*args, **kwargs)

    def __reduce_ex__(self, *args, **kwargs):
        return self.getThreadStream().__reduce_ex__(*args, **kwargs)

    def __repr__(self, *args, **kwargs):
        return self.getThreadStream().__repr__(*args, **kwargs)

    def __sizeof__(self, *args, **kwargs):
        return self.getThreadStream().__sizeof__(*args, **kwargs)

    def __str__(self, *args, **kwargs):
        return self.getThreadStream().__str__(*args, **kwargs)

#     def __subclasshook__(self, *args, **kwargs):
#         return self.getThreadStream().__subclasshook__(*args, **kwargs)

    def close(self, *args, **kwargs):
        return self.getThreadStream().close(*args, **kwargs)

    def fileno(self, *args, **kwargs):
        return self.getThreadStream().fileno(*args, **kwargs)

    def flush(self, *args, **kwargs):
        return self.getThreadStream().flush(*args, **kwargs)

    def isatty(self, *args, **kwargs):
        return self.getThreadStream().isatty(*args, **kwargs)

    def next(self, *args, **kwargs):
        return self.getThreadStream().next(*args, **kwargs)

    def read(self, *args, **kwargs):
        return self.getThreadStream().read(*args, **kwargs)

    def readinto(self, *args, **kwargs):
        return self.getThreadStream().readinto(*args, **kwargs)

    def readline(self, *args, **kwargs):
        return self.getThreadStream().readline(*args, **kwargs)

    def readlines(self, *args, **kwargs):
        return self.getThreadStream().readlines(*args, **kwargs)

    def seek(self, *args, **kwargs):
        return self.getThreadStream().seek(*args, **kwargs)

    def tell(self, *args, **kwargs):
        return self.getThreadStream().tell(*args, **kwargs)

    def truncate(self, *args, **kwargs):
        raise IOError("Can't truncate(); ThreadAwareFile is read-only")
#         return self.getThreadStream().truncate(*args, **kwargs)

    def write(self, *args, **kwargs):
        raise IOError("Can't write(); ThreadAwareFile is read-only")
#         return self.getThreadStream().write(*args, **kwargs)

    def writelines(self, *args, **kwargs):
        raise IOError("Can't writelines(); ThreadAwareFile is read-only")
        return self.getThreadStream().writelines(*args, **kwargs)

    def xreadlines(self, *args, **kwargs):
        return self.getThreadStream().xreadlines(*args, **kwargs)

    @property
    def closed(self):
        return self.getThreadStream().closed

    @property
    def encoding(self):
        return self.getThreadStream().encoding

    @property
    def errors(self):
        return self.getThreadStream().errors

    @property
    def mode(self):
        return self.getThreadStream().mode

    @property
    def name(self):
        return self.getThreadStream().name

    @property
    def newlines(self):
        return self.getThreadStream().newlines

    @property
    def softspace(self):
        return self.getThreadStream().softspace

    @softspace.setter
    def softspace(self, val):
        self.getThreadStream().softspace = val

