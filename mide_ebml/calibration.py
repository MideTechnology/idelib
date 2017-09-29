'''
Calibration and Transform classes. These are callable objects that modify
data. Functionally, calibration is the same as a Transform, the difference
being in how they are used.

Created on Nov 27, 2013

@author: dstokes

@todo: Use regex to optimize built univariate and bivariate functions

@todo: Completely remove the 'optimization' that ends up converting floats to
    ints. It makes things worse. Do the opposite where possible.

@todo: Simplify, simplify. For example, allowing arbitrary variable names is a 
    needless complexity.
    
@todo: Completely remove ``AccelTransform``. Obsolete.
'''

# __all__ = ['Transform', 'AccelTransform', 'AccelTransform10G', 
#            'Univariate', 'Bivariate']

from collections import OrderedDict
import math
from time import sleep

import logging
logger = logging.getLogger('mide_ebml')

#===============================================================================
# 
#===============================================================================

class Transform(object):
    """ Base class for all data-manipulating objects (e.g. calibration
        polynomials). Instantiates as a function-like object representing any 
        processing that an event requires, including basic calibration at the 
        low level and adjustments for display at the high level.
    """
    modifiesTime = False
    modifiesValue = False
    units = None
    
    def __init__(self, *args, **kwargs):
        self.id = None
        self._str = "x"
        self._source = "lambda x: x"
        self._function = eval(self._source, {'math': math})
        self._lastSession = None
        self._timeOffset = 0
        
        # Custom attributes, e.g. Attribute elements in the EBML.
        self.attributes = kwargs.pop('attributes', None)
    
    
    def copy(self):
        """ Create a duplicate of this Transform.
        """
        t = self.__class__()
        for attr in ('id', '_str', '_source', '_function', '_lastSession', 
                     '_timeOffset'):
            setattr(t, attr, getattr(self, attr, None))
        return t
    
    
    def __str__(self):
        return self._str
    
    
    def __repr__(self):
        cname = self.__class__.__name__
        if self.id is None:
            return "<%s: (%s)>" % (cname, self._str)
        return "<%s (ID %d): (%s)>" % (cname, self.id, self._str)


    def __hash__(self):
        return hash(self._str)


    def __eq__(self, other):
        try:
            return self._str == other._str
        except AttributeError:
            return False
    
    
    def __ne__(self, other):
        return not self.__eq__(other)


    @property
    def function(self):
        """ The generated polynomial function itself. """
        return self._function


    @property
    def source(self):
        """ The optimized source code of the polynomial. """
        return self._source
    
    
    def __call__(self, event, session=None, noBivariates=False):
        if session != self._lastSession:
            self._timeOffset = 0 if session.startTime is None else session.startTime
            self._session = session
        return event[-2] + self._timeOffset, self._function(event[-1])

    
    #===========================================================================
    # 
    #===========================================================================
    
    @classmethod
    def null(cls, *args, **kwargs):
        return args[0]
    


#===============================================================================
# Simple Transforms. These could be represented by Univariate polynomials,
# but are hard-coded for efficiency's sake.
#===============================================================================

class AccelTransform(Transform):
    """ A simple transform to convert accelerometer values (parsed as
        int16) to floats in the range -100 to 100 G.
         
        This assumes that the data was parsed by `AccelerometerParser`, which
        puts the raw values in the range -32768 to 32767.
    """
    modifiesValue = True
     
    def __init__(self, amin=-100, amax=100, calId=0, dataset=None):
        self.id = calId
        self.range = (amin, amax)
        self._str = "(x / 32767.0) * %.3f" % amax
        self._source = "lambda x: x * %f" % (amax / 32767.0)
        self._function = eval(self._source, {'math': math})
        self._lastSession = None
        self._timeOffset = 0
        
        self.references = (0,)
        self.coefficients = ((amax / 32767.0), amax)


    def copy(self):
        """ Create a duplicate of this Transform.
        """
        t = self.__class__(self.range[0], self.range[1], self.id, self.dataset)
        return t
    
     


#===============================================================================
# Polynomial Generators
#===============================================================================

class Univariate(Transform):
    """ A simple calibration polynomial in the general form:
        `y=(coeffs[0]*(x**n))+(coeffs[1]*(x**n-1))+...+(coeffs[n]+(x**0))`.
        
        Instances are function-like objects that take one argument: a sensor
        reading.
    """
    modifiesValue = True
    
    @classmethod
    def _floatOrInt(self, v):
        " Helper method to convert floats with no decimal component to ints. "
#         iv = int(v)
#         return iv if iv == v else v
        # Not a good optimization. Only convert 0 to integer.
        return 0 if v == 0 else float(v)
    
    
    @classmethod
    def _stremove(self, s, old):
        " Helper method to remove a set of substrings from a string. "
        result = str(s)
        for o in old:
            result = result.replace(o,'')
        return result
    
    
    @classmethod
    def _streplace(cls, s, *args):
        " Helper method to replace multiple substrings. "
        for old,new in args:
            s = s.replace(old, new)
        return s
    
    
    @classmethod
    def _fixSums(self, s):
        " Helper method to replace consecutive addition/subtraction combos. "
        result = str(s)
        for old, new in (("--", "+"), ("-+", "-"), ("+-", "-"), ("++", "+")):
            result = result.replace(old, new)
        return result.lstrip('+')
    
    
    # XXX: kwargs added to __init__() as work-around for bad SSS templates! 
    def __init__(self, coeffs, calId=None, dataset=None, reference=0, 
                 varName="x", attributes=None, **kwargs):
        """ Construct a simple polynomial function from a set of coefficients.
            
            @param coeffs: A list of coefficients
            @keyword calId: The polynomial's calibration ID (if any).
            @keyword dataset: The parent `dataset.Dataset`.
            @keyword reference: A reference value to be subtracted from the
                variable.
            @keyword varName: The name of the variable to be used in the
                string version of the polynomial. For display purposes.
            @keyword attributes: A dictionary of generic attributes, e.g.
                ones parsed from `Attribute` EBML elements, or `None`.
        """
        self.id = calId
        self.dataset = dataset
        self._coeffs = tuple(coeffs)
        self._variables = (varName,)
        self._references = (reference,)
        self._session = None
        self._lastSession = None
        self._timeOffset = 0
        
        self.attributes = attributes
        
        self._build()
        

    def __eq__(self, other):
        try:
            return self._coeffs == other._coeffs and self._references == other._references
        except AttributeError:
            return False


    def copy(self):
        """ Create a duplicate of this Transform.
        """
        return self.__class__(self._coeffs, calId=self.id, dataset=self.dataset,
                              reference=self._references[0], 
                              varName=self._variables[0])

    
    def _build(self):
        """ Internal method that (re-)constructs the polynomial function.
        """
        varName = str(self._variables[0])
        srcVarName = "x"
        reference = self._references[0]
        coeffs = self._coeffs
        
        if reference != 0:
            varName = "(%s-%s)" % (varName, reference)
            srcVarName = "(%s-%s)" % (srcVarName, reference)
        
        # f is used to build the lambda
        # strF is used to build the string version
        coeffs = list(reversed(coeffs))
        f = [coeffs[0]] if coeffs[0] != 0 else []
        strF = f[:]
        coeffs = map(self._floatOrInt, coeffs)
        for p, v in enumerate(coeffs[1:],1):
            # optimization: x*0 == 0
            if v == 0:
                continue
    
            # optimization: pow() is more expensive than lots of multiplication
            x = "*".join([srcVarName]*p)
            strX = "pow(%s,%s)" % (varName, p) if p > 1 else varName
    
            # optimization: remove multiplication by 1
            q = "%s*" % v if v != 1 else ""
    
            f.append("(%s%s)" % (q,x))
            strF.append("(%s%s)" % (q, strX))
    
        self._str = "+".join(map(str,reversed(strF)))
        self._str = self._fixSums(self._str)
        
        self._source = "lambda x: %s" % ("+".join(map(str,reversed(f))))
        self._source = self._fixSums(self._source)
        self._function = eval(self._source, {'math': math})
    
    
    @property
    def coefficients(self):
        """ The polynomial's coefficients. """
        return self._coeffs
    
    
    @coefficients.setter
    def coefficients(self, val):
        self._coeffs = val
        self._build()
        
        
    @property
    def variables(self):
        """ The name(s) of the variable(s) used in the polynomial. """
        return self._variables
    
    
    @variables.setter
    def variables(self, val):
        self._variables = val
        self._build()
    
    
    @property
    def references(self):
        """ The constant offset(s). """
        return self._references
    
    
    @references.setter
    def references(self, val):
        self._references = val
        self._build()
    
    
    def asDict(self):
        """ Dump the polynomial as a dictionary. Intended for use when
            generating EBML.
        """
        return OrderedDict((('CalID', self.id),
                            ('CalReferenceValue', self._references[0]),
                            ('PolynomialCoef', self._coeffs)))


#===============================================================================
# 
#===============================================================================

class Bivariate(Univariate):
    """ A two-variable polynomial in the general form
        `v=(A*x*y)+(B*x)+(C*y)+D`.
        
        Instances are function-like objects that take one argument: a sensor
        reading time and value.
    """
    
    def __init__(self, coeffs, calId=None, dataset=None, reference=0, 
                 reference2=0, channelId=None, subchannelId=None, varNames="xy",
                 attributes=None):
        """ Construct the two-variable polynomial.
            
            @param coeffs: A list of coefficients. Must contain 4!
            @keyword reference: A reference value to be subtracted from the
                'x' variable.
            @keyword reference2: A reference value to be subtracted from the
                'y' variable.
            @keyword varNames: The names of the variables to be used in the
                string version of the polynomial. For display purposes; they
                can be any arbitrary (but hopefully meaningful) strings.
            @keyword calId: The polynomial's calibration ID (if any).
            @keyword dataset: The parent `dataset.Dataset`.
            @keyword varName: The name of the variable to be used in the
                string version of the polynomial. For display purposes.
            @keyword attributes: A dictionary of generic attributes, e.g.
                ones parsed from `Attribute` EBML elements, or `None`.
        """
        self.dataset = dataset
        self._eventlist = None
        self._sessionId = None
        self.channelId, self.subchannelId = channelId, subchannelId
        if channelId is None or subchannelId is None:
            raise ValueError("Bivariate polynomial requires channel and " \
                    "subchannel IDs; got %r, %d" % (channelId, subchannelId))
        
        if len(coeffs) != 4:
            raise ValueError("Bivariate polynomial must have exactly 4 "
                             "coefficients; %d were supplied" % len(coeffs))
        if len(varNames) != 2:
            raise ValueError("Bivariate polynomial must have two variable "
                             "names; %d were supplied" % len(varNames))
        
        self.id = calId
        
        self._references = (float(reference), float(reference2))
        self._coeffs = tuple(map(float,coeffs))
        self._variables = tuple(map(str, varNames))
        
        self._session = None
        self._timeOffset = 0
        
        self.attributes = attributes
        
        self._build()
        
        
    def __eq__(self, other):
        try:
            return self._str == other._str
        except AttributeError:
            return False
    
    
    def copy(self):
        """ Create a duplicate of this Transform.
        """
        # This could be optimized by circumventing the polynomial rebuild,
        # and instead using the already-generated source.
        return self.__class__(self._coeffs, dataset=self.dataset, 
               channelId=self.channelId, subchannelId=self.subchannelId, 
               reference=self._references[0], reference2=self._references[1], 
               varNames=self._variables, calId=self.id)

    
    @classmethod
    def _reduce(cls, src):
        """ Simple reduction for polynomial expressions, removing redundant
            parts (adding/subtracting 0, multiplying by 0 or 1, etc.).
        """
        old = None
        while old != src:
            old = src
            src = cls._streplace(src, 
                ('(0+', '('), ('(0.0+', '('), ('(0-', '(-'), ('(0.0-', '(-'),
                ('(0*x', '(0'), ('(0.0*x', '(0'), 
                ('(0*y', '(0'), ('(0.0*y', '(0'),
                ('(0*x*y)+', ''), ('(0*x)+', ''), ('(0*y)+', ''),
                ('*)', ')'), ('+)', ')'), 
                ('(0)', ''), ('(0.0)', ''), ('()', ''), 
                ('(1)','1.0'), ('(1.0)','1.0'),
                ("(1*", "("), ("(1.0*", "("), ("(x)", "x"), ("(y)", "y"),
                ("--", "+"), ("-+", "-"), ("+-", "-"), ("++", "+")
            )
            if src.endswith('+0') or src.endswith('+0.0'):
                src = src.rstrip('+0.')
        return src
    
    
    def _build(self):
        """ Internal method that (re-)constructs the polynomial function.
        """
        coeffs = self._coeffs
        reference, reference2 = self._references
        varNames = self._variables
        
        # Construct the polynomial expression string
        strF = "(%s*x*y)+(%s*x)+(%s*y)+%s"
        src = strF % tuple(map(self._floatOrInt, coeffs))

        # Build the display (i.e. unoptimized) version of the polynomial         
        self._str = strF % self._coeffs
        varNames = list(varNames)
        if reference != 0:
            varNames[0] = "(x-%s)" % reference
        if reference2 != 0:
            varNames[1] = "(y-%s)" % reference2
        self._str = self._fixSums(self._str)
        
        # Replace standard variable names with custom ones. Change one to 
        # a stand-in first, to prevent problems if one name contains the other.
        self._str = self._streplace(self._str, ("x","\x00"), 
                                    ("y", varNames[1]), ("\x00", varNames[0]))

        # Optimizations: Build a simplified expression for function.
        # 1. Remove multiples of 0 and 1, addition of 0 constants.
        src = self._reduce(src)    

        # 2. If there's a reference value, replace the variable with (v-ref)           
        references = map(self._floatOrInt, (reference, reference2))
        for i,v in enumerate("xy"):
            if references[i] != 0:
                src = src.replace(v, "(%s-%s)" % (v, references[i]))  
        
        # 3. Do the reduction again, now that the offsets are in.
        src = self._reduce(src)    
        if not src:
            logger.warning("Bad polynomial coefficients {}".format(self._coeffs))
            src = "x"
        
        self._source = 'lambda x,y: %s' % self._fixSums(src)
        self._function = eval(self._source, {'math': math})
        
        # Optimization: it is possible that the polynomial could exclude Y
        # completely. If that's the case, use a dummy value to speed things up.
        self._noY = (0,1) if 'y' not in src else False 


    def __call__(self, event, session=None, noBivariates=False):
        """ Apply the polynomial to an event. 
        
            @param event: The event to process (a time/value tuple).
            @keyword session: The session containing the event.
        """
        session = self.dataset.lastSession if session is None else session
        sessionId = None if session is None else session.sessionId
        
        try:
            if self._eventlist is None or self._sessionId != sessionId:
                channel = self.dataset.channels[self.channelId][self.subchannelId]
                self._eventlist = channel.getSession(session.sessionId)
                self._sessionId = session.sessionId
            if len(self._eventlist) == 0:
                return event
            
            x = event[-1]
            
            # Optimization: don't check the other channel if Y is unused
            if noBivariates:
                y = (0,1)
            else:
                y = self._noY or self._eventlist.getMeanNear(event[-2])
            return event[-2],self._function(x,y)
        
        except (IndexError, ZeroDivisionError) as err:
            # In multithreaded environments, there's a rare race condition
            # in which the main channel can be accessed before the calibration
            # channel has loaded. This should fix it.
            logger.warning("%s occurred in Bivariate polynomial %r" % \
                           err.__class__.__name__, self.id)
            return None


    def asDict(self):
        """ Dump the polynomial as a dictionary. Intended for use when
            generating EBML.
        """
        cal = super(Bivariate, self).asDict()
        cal['BivariateCalReferenceValue'] = self._references[1]
        cal['BivariateChannelIDRef'] = self.channelId
        cal['BivariateSubChannelIDRef'] = self.subchannelId
        return cal


#===============================================================================
# 
#===============================================================================

class CombinedPoly(Bivariate):
    """ Calibration transform that combines multiple polynomials into a single
        function. Used for combining Channel and Subchannel transforms to make
        them more efficient.
    """
    
    def copy(self):
        """ Create a duplicate of this Transform.
        """
        return self.__class__(self.poly, subchannel=self._subchannel, 
                              calId=self.id, dataset=self.dataset, 
                              **self.kwargs)
    
    def __init__(self, poly, subchannel=None, calId=None, dataset=None, 
                 **kwargs):
        self.id = calId
        self.poly = poly
        self.subpolys = kwargs
        
        if subchannel is not None:
            self.poly = self.poly[subchannel]

        self.kwargs = kwargs
        p = kwargs.values()[0]
        for attr in ('dataset','_eventlist','_sessionId','channelId',
                     'subchannelId', '_references', '_coeffs','_variables'):
            setattr(self, attr, getattr(poly, attr, getattr(p, attr, None)))
                    
        self.dataset = self.dataset or dataset
        self._subchannel = subchannel
        self._build()
    
    
    def _build(self):
        if self.poly is None:
            if len(self.subpolys) == 1:
                p = self.subpolys.values()[0]
                if p is not None:
                    for attr in ('_str', '_source', '_function', '_noY'):
                        setattr(self, attr, getattr(p, attr, None))
                    return
            phead, src= "lambda x", "x"
        else:
            phead,src = self.poly.source.split(": ")
            
        for k,v in self.subpolys.items():
            if v is None:
                ssrc = "lambda x: x"
            else:
                ssrc = v.source 
            s = "(%s)" % ssrc.split(": ")[-1]
            src = self._reduce(src.replace(k, s))

        if self._subchannel is not None:
            src = src.replace('x','x[%d]' % self._subchannel)
        
        # Merge in all function globals, in case components use additional
        # libraries (e.g. math). 
        evalGlobals = {'math': math}
        if self.poly is not None: 
            evalGlobals.update(self.poly._function.func_globals)
        for p in self.subpolys.itervalues():
            if p is not None:
                evalGlobals.update(p._function.func_globals)
        
        self._str = src
        self._source = "%s: %s" % (phead, src)
        self._function = eval(self._source, evalGlobals)
        self._noY = (0,1) if 'y' not in src else False
        
        
    def asDict(self):
        """ Dump the polynomial as a dictionary. Intended for use when
            generating EBML.
        """
        raise TypeError("Can't generate dictionary for %s" % \
                        self.__class.__.__name)

#------------------------------------------------------------------------------ 

class PolyPoly(CombinedPoly):
    """ Calibration transform that combines multiple subchannel polynomials 
        into one single function.
    """
    
    def copy(self):
        """ Create a duplicate of this Transform.
        """
        return self.__class__(self.polys, calId=self.id, dataset=self.dataset)
    
    
    def __init__(self, polys, calId=None, dataset=None):
        self.id = calId
        self.polys = polys
        poly = polys[0]
        for attr in ('dataset','_eventlist','_sessionId','channelId','subchannelId'):
            setattr(self, attr, getattr(poly, attr, None))
        
        self.dataset = self.dataset or dataset
        self._eventlist = None
        self._build()


    def _build(self):
        params = []
        body = []
        for n,p in enumerate(self.polys):
            params.append('x%d' % n)
            if p is None:
                body.append('x%d' % n)
            else:
                body.append(p.source.split(':')[-1].replace('x', 'x%d' % n))
        
        # ends with a comma to ensure a tuple is returned
        src = "(%s,)" % (', '.join(body))
        self._str = src

        if 'y' in src:
            params.insert(0,'y')
            self._noY = False
        else:
            self._noY = (0,1)
        
        # Merge in all function globals, in case components use additional
        # libraries (e.g. math). 
        evalGlobals = {'math': math}
        for p in self.polys:
            if p is not None:
                evalGlobals.update(p._function.func_globals)
        
        self._source = "lambda %s: %s" % (','.join(params), src)
        self._function = eval(self._source, evalGlobals)
        self._variables = params


    def __call__(self, event, session=None, noBivariates=False):
        """ Apply the polynomial to an event. 
        
            @param event: The event to process (a time/value tuple or a
                `Dataset.Event` named tuple).
            @keyword session: The session containing the event.
        """
        try:
            x = event[-1]
            # Optimization: don't check the other channel if Y is unused
            if self._noY is False:
                if noBivariates:
                    return event[-2], self._function(0, *x)
                    
                session = self.dataset.lastSession if session is None else session
                sessionId = None if session is None else session.sessionId
                
                if self._eventlist is None or self._sessionId != sessionId:
                    channel = self.dataset.channels[self.channelId][self.subchannelId]
                    self._eventlist = channel.getSession(session.sessionId)
                    self._sessionId = session.sessionId
                
                # XXX: Hack! EventList length can be 0 if a thread is running.
                # This almost immediately gets fixed. Find real cause.
                try:    
                    y = self._eventlist.getMeanNear(event[-2], outOfRange=True)
                except IndexError:
                    sleep(0.001)
                    if len(self._eventlist) == 0:
                        return None
                    y = self._eventlist.getMeanNear(event[-2], outOfRange=True)
                    
                return event[-2],self._function(y, *x)
            
            else:
                return event[-2],self._function(*x)
            
        except (TypeError, IndexError, ZeroDivisionError) as err:
            # In multithreaded environments, there's a rare race condition
            # in which the main channel can be accessed before the calibration
            # channel has loaded. This should fix it.
            if getattr(self.dataset, 'loading', False):
                logger.warning("%s occurred in combined polynomial %r" % \
                               (err.__class__.__name__, self))
                return None
            raise

