"""
The basis of a simple plug-in architecture. Plug-ins can be imported modules, 
directories, or zip files with a different extension. Directories and zips
are imported by path (e.g. the name of the zip file) and must contain at least 
two items:

  * info.json:  A JSON file containing vital information about the plugin.
                At minimum, it must contain a `"module"` and a`"type"`. 
                The "module" should be the name of the file defining the
                plugin, typically the same as the directory or compressed
                file. It must be unique. The "type" is an arbitrary string,
                to be used by the host application.
                  
  * <name>.py:  The module containing the actual plugin. It must define an
                `init()` function which returns a function-like object;
                this object is what gets called when the plugin is used.
                The name should match that of the directory or compressed
                file.

Plug-ins as imported modules are explicitly imported in Python and then wrapped
in a `Plugin` object. They are the same as the Python in a file/directory-based
plug-in, but the metadata is stored in a `PLUGIN_INFO` attribute (a dictionary,
the same content as a parsed `info.json` file).

Plug-ins embedded in a packaged Python app (PyInstaller, Py2Exe) are most 
easily handled as modules.
"""

__author__ = "D. R. Stokes"
__email__ = "dstokes@mide.com"

from collections import defaultdict, Sequence
from fnmatch import fnmatch
from functools import partial
from glob import glob
import imp
import json
import os
import types
import zipimport

#===============================================================================
# 
#===============================================================================

class PluginImportError(ImportError):
    """ General exception raised when a plug-in fails to load. Base class for
        other plugin error exceptions; catch last.
        
        @ivar message: Description of the error.
        @ivar path: The path to the plug-in, if applicable.
        @ivar exception: The exception that caused this exception to be 
            raised, if applicable. 
    """
    def __init__(self, message='', path='', exception=None):
        if not message:
            message = path
        elif path:
            message = "%s %r" % (message, path)
        super(PluginImportError, self).__init__(message)
        self.path = path
        self.exception = exception


class PluginValidationError(PluginImportError):
    """ Raised when a plug-in fails validation.
    """


class PluginDupeError(PluginValidationError):
    """ Raised when a plug-in conflicts with an existing plug-in or module.
    """


#===============================================================================
# 
#===============================================================================

class Plugin(object):
    """ A plug-in component, as represented in the host application. It handles
        loading the actual plug-in code, reading from either a compressed file
        or a directory (if permitted). 
        
        After initialization, the plug-in must still be loaded before use.
        The actual import of the plug-in module happens then.
        
    """
    PLUGIN_EXT = (".plg", ".zip")
    
    @classmethod
    def isPlugin(cls, p, useSource=True):
        """ Test a given path or module for plugin-ness.
        """
        if isinstance(p, types.ModuleType):
            return hasattr(p, "PLUGIN_INFO")
        if not isinstance(p, basestring):
            return False
        if os.path.isdir(p):
            if not useSource:
                return False
            return os.path.exists(os.path.join(p, 'info.json'))
        p = os.path.splitext(p)[0]
        return any(map(os.path.isfile, [p+x for x in cls.PLUGIN_EXT]))


    def __repr__(self):
        args = (self.__class__.__name__, self.moduleName, self.path)
        if self.loaded:
            r = u'<%s %s %s>' % args
        else:
            r = u'<%s (unloaded) %s %s>' % args
        return r.encode('ascii', 'replace')
    
    
    def __init__(self, path, useSource=True):
        """ Constructor. 
        
            @param path: The path to the plugin. Any file extension is
                ignored. May also be an imported module with the proper
                attributes.
            @keyword useSource: If `True`, an uncompressed version of the
                plugin will be loaded if available. 
        """
        self.loaded = False
        self.module = None
        self.main = None
        self.isModule = False
        
        # The plugin is an imported module. Just get the relevant data from it.
        # Module plugins are not otherwise validated, since they were imported
        # explicitly.
        if isinstance(path, types.ModuleType):
            self.isDir = False
            self.isModule =True
            try:
                self.info = path.PLUGIN_INFO.copy()
                self.name = self.info['name']
                self.type = self.info['type']
            except (KeyError, AttributeError) as err:
                raise PluginImportError('Could not find plugin info in', 
                                        path, err)
            self.module = path
            self.moduleName = path.__name__
            self.path = path.__file__
            return
        
        # The plugin could be a directory name, or the name of a compressed
        # file (with extension `PLUGIN_EXT`). For convenience, the extension
        # '.zip' is also valid; if both exist, the former is used.
        path = os.path.realpath(os.path.expanduser(path))
        try:
            dirPath = os.path.splitext(path)[0]
            zipPaths = filter(os.path.isfile, 
                              [dirPath + x for x in self.PLUGIN_EXT])
        except (AttributeError, TypeError) as err:
            raise PluginImportError("Bad path:", path, err)
        
        # Find the plugin's file or directory. If `useSource`, an
        # uncompressed directory takes precedence.
        if useSource and os.path.isdir(dirPath): 
            self.path = dirPath
            self.isDir = True
        elif len(zipPaths) > 0:
            self.path = zipPaths[0]
            self.isDir = False
        else:
            raise PluginImportError("Not a plugin:", path)

        # Get the plugin info, stored in a JSON file.
        try:
            if self.isDir:
                # Not archive.
                self.zip = None
                with open(os.path.join(self.path, u'info.json'), 'rb') as f:
                    self.info = json.load(f)
            else:
                # Is an archive.
                self.zip = zipimport.zipimporter(self.path)
                self.info = json.loads(self.zip.get_data(u'info.json'))
        except (IOError, ImportError) as err:
            raise PluginImportError('Could not find plugin info in', 
                                    self.path, err)
        except ValueError as err:
            raise PluginImportError('Could not read plugin info from', 
                                    self.path, err)

        # Validate the plugin, using information from the info file.
        # TODO: This. Maybe check signatures or something for security.
        # TODO: Possibly store list of dependencies, like `setup.py` scripts.
        try:
            self.type = self.info['type']
            self.moduleName = self.info['module']
        except KeyError as err:
            raise PluginValidationError("Could not validate plugin", 
                                        self.path, err)
        
        try:
            imp.find_module(self.moduleName)
            raise PluginDupeError("Plugin module name %r already in use" % \
                                  self.moduleName, self.path)
        except ImportError:
            # This is good: the module doesn't already exist.
            pass
        
        self.name = self.info.get('name', self.moduleName)
        

    def load(self, *args, **kwargs):
        """ Import the plugin's code. The module is loaded and its
            `init()` function is called, which should return a function-like
            object (the plugin itself). The actual plugin is not executed.
            
            Arguments and keyword arguments are passed directly to the
            plugin's `__init__()` method.
        """
        if self.module is None:
            try:
                if self.isDir:
                    # Load either the source or compiled version of the plugin.
                    # Source takes precedence.
                    src = os.path.join(self.path, self.moduleName+'.py')
                    com = os.path.join(self.path, self.moduleName+'.pyc')
                    if os.path.exists(src):
                        self.module = imp.load_source(self.moduleName, src)
                    else:
                        self.module = imp.load_compiled(self.moduleName, com)
                else:
                    # Import from the compressed file.
                    # The library handles loading source vs. compiled.
                    self.module = self.zip.load_module(self.moduleName)
            except (SyntaxError, ImportError, IOError) as err:
                raise PluginImportError("Could not import %r from" % \
                                        self.moduleName, self.path, err)
        
        if not hasattr(self.module, 'init'):
            raise PluginImportError("No 'init' function in plugin", 
                                    self.path)
        
        self.loaded = True
        self.main = self.module.init(*args, **kwargs)
        self.__call__.__func__.__doc__ = self.main.__doc__
        return self


    def __call__(self, *args, **kwargs):
        """ Execute the plug-in.
        """
        if not self.loaded:
            self.load()
        return self.main(*args, **kwargs)


#===============================================================================
# 
#===============================================================================

class PluginSet(object):
    """ A container for `Plugin` objects. Handles loading accessing them.
    """
    
    @staticmethod
    def _isWildcard(s):
        if not isinstance(s, basestring):
            return False
        try:
            return any([c in s for c in '*?[]'])
        except TypeError:
            return False


    def __init__(self, paths=None, useSource=True, quiet=False):
        """ Constructor. 
        
            @keyword paths: The path to a plugin file or directory, an imported
                module containing a plugin, or a collection of the two. Paths
                may contain glob-style wildcards.
            @keyword useSource: If `True`, unpackaged plugin directories will
                be imported in favor of the packaged versions. 
            @keyword quiet: If `True`, plugin import errors will be suppressed.
                Bad imports will be added to the object's `bad` and `dupes` 
                lists.
        """
        self.plugins = {}
        self.pluginTypes = defaultdict(list)
        self.bad = []
        self.dupes = []

        if paths is None:
            return        
        self.add(paths, useSource=useSource, quiet=quiet)
        

    def add(self, paths, useSource=True, quiet=False):
        """ Add one or more plugins. The plugin will be imported but not
            loaded (i.e. its `load()` method will not be called).
            
            @param paths: The path to a plugin file or directory, an imported
                module containing a plugin, or a collection of the two. Paths
                may contain glob-style wildcards.
            @keyword useSource: If `True`, unpackaged plugin directories will
                be imported in favor of the packaged versions. 
            @keyword quiet: If `True`, plugin import errors will be suppressed.
                Bad imports will be added to the object's `bad` and `dupes` 
                lists, regardless.
        """
        if isinstance(paths, basestring) or not isinstance(paths, Sequence):
            paths = [paths]
        
        map(paths.extend, map(glob, [p for p in paths if self._isWildcard(p)]))
        
        err = None
        for path in paths:
            if not Plugin.isPlugin(path):
                continue
            try:
                p = Plugin(path, useSource=useSource)
                if p.moduleName in self.plugins:
                    self.dupes.append(path)
                else:
                    self.plugins[p.moduleName] = p
                    self.pluginTypes[p.type].append(p)
            except PluginDupeError as err:
                self.dupes.append(path)
            except PluginImportError as err:
                self.bad.append((path, err))
        
        if not quiet and err is not None:
            raise err


    def __len__(self):
        return len(self.plugins)
   
   
    def __getitem__(self, k):
        return self.plugins[k]

    def get(self, *args, **kwargs):
        return self.plugins.get(*args, **kwargs)
    
    def items(self):
        return self.plugins.items()

    def keys(self):
        return self.plugins.keys()

    def values(self):
        return self.plugins.values()
    
    def __iter__(self, *args, **kwargs):
        return self.plugins.__iter__(*args, **kwargs)
    
    def __contains__(self, k):
        return self.plugins.__contains__(k)
    
    @property
    def types(self):
        """ Return a list of all plugin types.
        """
        return self.pluginTypes.keys()
    
    
    def find(self, **kwargs):
        """ Find all plugins with the specified values in their `info`. Plugins
            matching all of the specified criteria are returned.
 
            Parameters to match are provided as keyword arguments. Glob-style 
            wildcards accepted as values. Examples:
                plugins.find(name="Specific Tool") # Gets one plug-in
                plugins.find(type="exporter") # Gets all of the specific type
                plugins.find(name="Meters2*") # Gets all plugins starting with "Meters2"
        """
        result = []
        for p in self.plugins.itervalues():
            good = True
            for k,v in kwargs.iteritems():
                # Get data from either the 'info' dict or an attribute
                val = p.info[k] if k in p.info else getattr(p, k, None)
                try:
                    if val == v:
                        good = good and True
                    elif not isinstance(v, basestring) or not fnmatch(val, v):
                        good = False
                except AttributeError:
                    good = False
                if not good:
                    break
            if good:
                result.append(p)
        return result


    def findAny(self, **kwargs):
        """ Find all plugins with the specified values in their `info`. Plugins
            matching any of the specified criteria are returned.
 
            Parameters to match are provided as keyword arguments. Glob-style 
            wildcards accepted as values. Examples:
                plugins.find(name="Specific Tool") # Gets one plug-in
                plugins.find(type="exporter") # Gets all of the specific type
                plugins.find(name="Meters2*") # Gets all plugins starting with "Meters2"
        """
        result = []
        for p in self.plugins.itervalues():
            for k,v in kwargs.iteritems():
                # Get data from either the 'info' dict or an attribute
                val = p.info[k] if k in p.info else getattr(p, k, None)
                try:
                    if val == v:
                        result.append(p)
                    elif isinstance(v, basestring) and fnmatch(val, v):
                        result.append(p)
                except AttributeError:
                    continue
        return result
    
    
    def load(self, plug, args=[], kwargs={}, quiet=False):
        """ Load a plugin. Wraps the plugin's `load()` method. Can be called
            with the name of a plugin, a `Plugin` object, or a list of
            either.
            
            @param plug: The plugin(s) to load. Can be a `Plugin` object,
                the name of a plugin, or a list of objects and/or names.
            @keyword args: A list of arguments to be passed to the plugin's
                `load()` method.
            @keyword kwargs: A dictionary of keyword arguments to be passed
                to the plugin's `load()` method.
            @keyword quiet: If `True`, plugins that fail to load will do so
                without raising an exception.
            @return: The loaded plugin, or a list of loaded plugins if 
                `plug` was a list.
        """
        err = None
        try:
            if isinstance(plug, basestring):
                return self.plugins[plug].load(*args, **kwargs)
            elif isinstance(plug, Sequence):
                load = partial(self.load, args=args, kwargs=kwargs, quiet=quiet)
                return filter(None, map(load, plug))
            else:
                return plug.load(*args, **kwargs)
        except (KeyError, PluginImportError) as err:
            self.bad.append((plug, err))
        
        if err is not None and not quiet:
            raise err


#===============================================================================
# 
#===============================================================================

def makeInfo(mod):
    """ Utility function to generate the data for an plugin's `info.json` file.
    """
    ignore = ('__name__',)
    items = {}
    if isinstance(mod, basestring):
        if os.path.exists(mod):
            # A module name or a path
            modName = os.path.splitext(os.path.basename(mod.strip('\\/')))[0]
            if os.path.isdir(mod):
                infoFile = os.path.join(mod, 'info.json')
                if os.path.isfile(infoFile):
                    with open(infoFile, "rb") as f:
                        print "reading JSON"
                        items = json.load(f)
                modName = items.get('moduleName', modName)
                mod = os.path.join(mod, modName+".py")
            
            mod = imp.load_source(modName, mod)
        else:
            import importlib
            mod = importlib.import_module(mod)
    headerInfo = [x for x in dir(mod) if x.startswith('__') and x not in ignore]
    items.update({x.strip('_'): getattr(mod, x) for x in headerInfo if isinstance(getattr(mod, x), basestring)})
    items['moduleName'] = mod.__name__
    if hasattr(mod, "PLUGIN_INFO"):
        items.update(mod.PLUGIN_INFO)
    return items