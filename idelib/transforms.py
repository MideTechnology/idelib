"""
Calibration and Transform classes. These are callable objects that modify
data. Functionally, calibration is the same as a Transform, the difference
being in how they are used.

:author: dstokes
"""

__all__ = ['Transform', 'Univariate', 'Bivariate', 'CombinedPoly', 'PolyPoly',
           'AccelTransform']

import weakref
from collections import OrderedDict
import math
from time import sleep
import warnings

import logging

import numpy as np

logger = logging.getLogger('idelib')
logging.basicConfig(format="%(asctime)s %(levelname)s: %(message)s")

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
        self._variables = ("x",)
        self._lastSession = None
        self._timeOffset = 0
        self._watchers = weakref.WeakSet()
        
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
    
    
    def __call__(self, timestamp, value, session=None, noBivariates=False):
        if session != self._lastSession:
            self._timeOffset = 0 if session.startTime is None else session.startTime
            self._session = session
        return timestamp + self._timeOffset, self._function(value)


    def isValid(self, session=None, noBivariates=False):
        """ Check the validity of the Transform.
        """
        # TODO: More base validity tests for all Transform subclasses?
        try:
            return (self.function is not None)
        except AttributeError:
            return False


    def inplace(self, values, y=None, timestamp=None, session=None, noBivariates=False, out=None):
        """ In-place Transform call for the Transform base class.
            All subclasses are required to implement this method, so it will
            raise an error if called.
        """
        raise NotImplementedError()


    @property
    def useMean(self):
        """ Property to determine if a transform will use the mean of the
            secondary channel.  The base class and all univariate polynomials
            do not have a secondary channel, so they will always return the
            default `True` and generate a warning.
        """
        warnings.warn(UserWarning('{} does not support useMean'.format(type(self))))
        return True


    @useMean.setter
    def useMean(self, value):
        warnings.warn(UserWarning('{} does not support useMean'.format(type(self))))


    def addWatcher(self, watcher):
        """ Adds `watcher` to the list (a `WeakSet`) of watchers.  The watchers
            are other polynomials, such as a `CombinedPoly`, which reference
            this polynomial.  This is used to propogate changes to all
            polynomials which reference this one.
        """
        self._watchers.add(watcher)

    
    #===========================================================================
    # 
    #===========================================================================

    @classmethod
    def null(cls, *args, **kwargs):
        return args[0]


class ComplexTransform(Transform):
    """ An mixin class for arbitrarily complex functions that don't follow a set form.

        Instances are function-like objects that take one argument: a sensor
        reading.
    """

    def inplace(self, values, y=None, timestamp=None, session=None, noBivariates=False, out=None):
        """ In-place transform for the `ComplexTransform` transform.  These functions
            can't be easily reduced and combined like polynomials, so this instead
            wraps the `function` method.
        """

        scalar = np.isscalar(values)

        if scalar:
            values = float(values)
        elif out is None:
            out = np.zeros_like(values, dtype=np.float64)

        if len(self._variables) == 1:

            if scalar:
                out = self.function(values)
            else:
                out[:] = self.function(values)
        else:

            session = self.dataset.lastSession if session is None else session
            sessionId = None if session is None else session.sessionId

            try:
                if self._eventlist is None or self._sessionId != sessionId:
                    channel = self.dataset.channels[self.channelId][self.subchannelId]
                    self._eventlist = channel.getSession(session.sessionId)
                    self._sessionId = session.sessionId

            except IndexError as err:
                # In multithreaded environments, there's a rare race condition
                # in which the main channel can be accessed before the calibration
                # channel has loaded. This should fix it.
                logger.warning("%s occurred in Bivariate polynomial %r" %
                               err.__class__.__name__, self.id)
                return None

            if noBivariates:
                y = 0
            elif self.useMean:
                y = self._eventlist.getMean()
            elif y is None and timestamp is None:
                y = self._eventlist.getMean()
            elif y is None and timestamp is not None:
                y = np.fromiter((self._eventlist[self._eventlist.getEventIndexNear(t)][0] for t in
                                 timestamp), dtype=np.float64)

            if scalar:
                out = self.function(values, y)
            else:
                out[:] = self.function(values, y)

        return out



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

        self.dataset = None
        self._watchers = weakref.WeakSet()


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

        TODO: in-place changes force this to be in the form of either
              `f(x) = coeffs[0]*x + coeffs[1]`
              or
              `f(x) = coeffs[0]`
              This behavior will need to be updated later.
    """
    modifiesValue = True
    
    @classmethod
    def _floatOrInt(cls, v):
        """ Helper method to convert floats with no decimal component to ints. """
#         iv = int(v)
#         return iv if iv == v else v
        # Not a good optimization. Only convert 0 to integer.
        return 0 if v == 0 else float(v)
    
    
    @classmethod
    def _stremove(cls, s, old):
        """ Helper method to remove a set of substrings from a string. """
        result = str(s)
        for o in old:
            result = result.replace(o, '')
        return result
    
    
    @classmethod
    def _streplace(cls, s, *args):
        """ Helper method to replace multiple substrings. """
        for old, new in args:
            s = s.replace(old, new)
        return s
    
    
    @classmethod
    def _fixSums(cls, s):
        """ Helper method to replace consecutive addition/subtraction combos. """
        result = str(s)
        for old, new in (("--", "+"), ("-+", "-"), ("+-", "-"), ("++", "+")):
            result = result.replace(old, new)
        return result.lstrip('+')
    
    
    # XXX: kwargs added to __init__() as work-around for bad SSS templates! 
    def __init__(self, coeffs, calId=None, dataset=None, reference=0, 
                 varName="x", attributes=None, **kwargs):
        """ Construct a simple polynomial function from a set of coefficients.
            
            :param coeffs: A list of coefficients
            :keyword calId: The polynomial's calibration ID (if any).
            :keyword dataset: The parent `dataset.Dataset`.
            :keyword reference: A reference value to be subtracted from the
                variable.
            :keyword varName: The name of the variable to be used in the
                string version of the polynomial. For display purposes.
            :keyword attributes: A dictionary of generic attributes, e.g.
                ones parsed from `Attribute` EBML elements, or `None`.
        """
        if len(coeffs) > 2 or len(coeffs) == 0:
            raise ValueError('Coefficients of length {} are not supported.  '
                             'Coefficients must be length 1 (constant) or 2 '
                             '(linear).'.format(len(coeffs)))
        coeffs = tuple(float(x) for x in coeffs)
        self.id = calId
        self.dataset = dataset
        self._coeffs = tuple(coeffs)
        self._fastCoeffs = tuple(coeffs)
        self._variables = (varName,)
        self._references = (reference,)
        self._session = None
        self._lastSession = None
        self._timeOffset = 0
        self._watchers = weakref.WeakSet()
        
        self.attributes = attributes
        
        self._build()


    def __hash__(self):
        return hash((self._coeffs, self._references, self.id))
        

    def __eq__(self, other):
        try:
            return self._coeffs == other._coeffs and \
                   self._references == other._references and \
                   self.id == other.id
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

        if len(coeffs) == 1:
            self._fastCoeffs = tuple(self._coeffs)
            self._str = str(self._fastCoeffs[0])
        elif len(coeffs) == 2:
            # a0*(x - ref) + a1 = a0*x + (a1 - a0*ref)
            self._fastCoeffs = (self._coeffs[0], self._coeffs[1] - self._coeffs[0]*reference)
        else:
            raise ValueError('Invalid list of coefficients.')


        # f is used to build the lambda
        # strF is used to build the string version
        coeffs = list(reversed(coeffs))
        f = [coeffs[0]] if coeffs[0] != 0 else []
        strF = f[:]
        coeffs = [self._floatOrInt(c) for c in coeffs]
        for p, v in enumerate(coeffs[1:], 1):
            # optimization: x*0 == 0
            if v == 0:
                continue
    
            # optimization: pow() is more expensive than lots of multiplication
            x = "*".join([srcVarName]*p)
            strX = "pow(%s,%s)" % (varName, p) if p > 1 else varName
    
            # optimization: remove multiplication by 1
            q = "%s*" % v if v != 1 else ""
    
            f.append("(%s%s)" % (q, x))
            strF.append("(%s%s)" % (q, strX))

        if tuple(coeffs) == (0,):
            f = [0]
            strF = [0]
    
        self._str = "+".join(map(str, reversed(strF)))
        self._str = self._fixSums(self._str)
        
        self._source = "lambda x: %s" % ("+".join(map(str, reversed(f))))
        self._source = self._fixSums(self._source)
        self._function = eval(self._source, {'math': math})


    def inplace(self, values, y=None, timestamp=None, session=None, noBivariates=False, out=None):
        """ In-place transform for the `Univariate` transform.  It reduces the
            number of array allocations/operations compared to the normal
            `__call__` method.  The user can supply an `out` argument to save
            the results to that array, or leave `out` equal to `None`.  If `out`
            is `None`, then this method will allocate an array in the shape of
            `values`.

            The method uses the following algebra, calculated in the `_build`
            method, to reduce the equation to fewer operations.  For brevity:
                `x` = `values`
                `an` = `coeffs[n]`
                `bn` = `_fastCoeffs[n]`

            `f(x) = a0*(x - ref) + a1`
             =>
            `f(x) = x*(a0) + (a1 - a0*ref)`
             =>
            `f(x) = b0*x + b1`

        """

        scalar = np.isscalar(values)

        if scalar:
            values = float(values)
        elif out is None:
            out = np.zeros_like(values, dtype=np.float64)

        if len(self._fastCoeffs) == 1:
            if scalar:
                out = self._fastCoeffs[0]
            else:
                out[:] = self._fastCoeffs[0]
        elif len(self._fastCoeffs) == 2:
            if scalar:
                out = values
            else:
                out[:] = values
            out *= self._fastCoeffs[0]
            out += self._fastCoeffs[1]
        else:
            raise

        return out
    
    
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
            
            :param coeffs: A list of coefficients. Must contain 4!
            :keyword reference: A reference value to be subtracted from the
                'x' variable.
            :keyword reference2: A reference value to be subtracted from the
                'y' variable.
            :keyword varNames: The names of the variables to be used in the
                string version of the polynomial. For display purposes; they
                can be any arbitrary (but hopefully meaningful) strings.
            :keyword calId: The polynomial's calibration ID (if any).
            :keyword dataset: The parent `dataset.Dataset`.
            :keyword attributes: A dictionary of generic attributes, e.g.
                ones parsed from `Attribute` EBML elements, or `None`.
        """
        if len(coeffs) not in [1, 4]:
            raise ValueError('Coefficients of length {} are not supported.  '
                             'Coefficients must be length 1 (constant) or 4 '
                             '(linear).'.format(len(coeffs)))
        coeffs = tuple(float(x) for x in coeffs)
        self.dataset = dataset
        self._eventlist = None
        self._sessionId = None
        self.channelId, self.subchannelId = channelId, subchannelId
        if channelId is None or subchannelId is None:
            raise ValueError("Bivariate polynomial requires channel and "
                    "subchannel IDs; got %r, %d" % (channelId, subchannelId))
        
        self.id = calId
        
        self._references = (float(reference), float(reference2))
        self._coeffs = tuple(map(float, coeffs))
        self._fastCoeffs = tuple(self._coeffs)
        self._variables = tuple(map(str, varNames))
        
        self._session = None
        self._timeOffset = 0
        
        self.attributes = attributes

        self._useMean = True
        self._watchers = weakref.WeakSet()
        
        self._build()


    def __hash__(self):
        return hash(self._str)
        
        
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
                ('(1)', '1.0'), ('(1.0)', '1.0'),
                ("(1*", "("), ("(1.0*", "("),  # ("(x)", "x"), ("(y)", "y"),
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

        if len(coeffs) not in [1, 4]:
            raise ValueError('Coefficients of length {} are not supported.  '
                             'Coefficients must be length 1 (constant) or 4 '
                             '(linear).'.format(len(coeffs)))

        if len(coeffs) == 1:
            self._fastCoeffs = tuple(self._coeffs)
        if len(coeffs) == 4:
            # a0*(x - refx)*(y - refy) + a1*(x - refx) + a2*(y - refy) + a3 =
            # = a0*x*y + x*(a1 - a0*refy) + y*(a2 - a0*refx) +
            #   + (a0*refx*refy + a3 - a1*refx - a2*refy)
            self._fastCoeffs = (
                self._coeffs[0],
                self._coeffs[1] - self._coeffs[0]*reference2,
                self._coeffs[2] - self._coeffs[0]*reference,
                self._coeffs[3] + self._coeffs[0]*reference*reference2 -
                self._coeffs[1]*reference - self._coeffs[2]*reference2,
                )

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
        self._str = self._streplace(self._str, ("x", "\x00"), 
                                    ("y", varNames[1]), ("\x00", varNames[0]))

        # Optimizations: Build a simplified expression for function.
        # 1. Remove multiples of 0 and 1, addition of 0 constants.
        src = self._reduce(src)    

        # 2. If there's a reference value, replace the variable with (v-ref)
        references = [self._floatOrInt(x) for x in (reference, reference2)]
        for i, v in enumerate("xy"):
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
        self._noY = (0, 1) if 'y' not in src else False


    def inplace(self, values, y=None, timestamp=None, session=None, noBivariates=False, out=None):
        """ In-place transform for the `Bivariate` transform.  It reduces the
            number of array allocations/operations compared to the normal
            `__call__` method.  The user can supply an `out` argument to save
            the results to that array, or leave `out` equal to `None`.  If `out`
            is `None`, then this method will allocate an array in the shape of
            `values`.

            When calculating the `y` value, several things need to be taken into
            account in the following priority:
            1. If `noBivariates` is `True`, then `y` must be equal to `0`.
            2. If `self.useMean` is `True`, then `y` is equal to the mean of the
               full length of the secondary channel.
            3. If `y` is provided, then use the provided value.
            4. If `timestamp` is provided, then get the values for the given `timestamp`.
            5. Otherwise, default to the mean of the secondary channel.

            Depending on if `y` is scalar, one of two methods will be used, detailed below.

            The method uses the following algebra, calculated in the `_build`
            method, to reduce the equation to fewer operations.  For brevity:
                `x` = `values`
                `xref`, `yref` = `references`
                `an` = `coeffs[n]`
                `bn` = `_fastCoeffs[n]`

            `y` is not scalar:

              `f(x) = a0*(x - xref)*(y - yref) + a1*(x - xref) + a2*(y - yref) + a3`
               =>
              `f(x) = x*y*(a0) + x*(a1 - a0*yref) + y*(a2 - a0*xref) + (a3 + a0*xref*yref - a1*xref - a2*yref)`
               =>
              `f(x) = b0*x*y + b1*x + b2*y + b3`

            `y` is scalar:

              `f(x) = b0*x*y + b1*x + b2*y + b3`
               =>
              `f(x) = x*(b0*y + b1) + (b2*y + b3)`
        """

        scalar = np.isscalar(values)

        if scalar:
            values = float(values)
        elif out is None:
            out = np.zeros_like(values, dtype=np.float64)

        session = self.dataset.lastSession if session is None else session
        sessionId = None if session is None else session.sessionId

        try:
            if self._eventlist is None or self._sessionId != sessionId:
                channel = self.dataset.channels[self.channelId][self.subchannelId]
                self._eventlist = channel.getSession(session.sessionId)
                self._sessionId = session.sessionId

        except IndexError as err:
            # In multithreaded environments, there's a rare race condition
            # in which the main channel can be accessed before the calibration
            # channel has loaded. This should fix it.
            logger.warning("%s occurred in Bivariate polynomial %r" %
                           err.__class__.__name__, self.id)
            return None

        if noBivariates:
            y = 0
        elif self.useMean:
            y = self._eventlist.getMean()
        elif y is None and timestamp is None:
            y = self._eventlist.getMean()
        elif y is None and timestamp is not None:
            y = np.fromiter((self._eventlist[self._eventlist.getEventIndexNear(t)][0] for t in timestamp), dtype=np.float64)

        if len(self._fastCoeffs) == 1:
            if scalar:
                out = self._fastCoeffs[0]
            else:
                out[:] = self._fastCoeffs[0]
        elif len(self._fastCoeffs) == 4:
            if np.isscalar(y):
                # a0*x*y + a1*x + a2*y + a3 =
                # x*(a0*y + a1) + (a2*y + a3)
                if scalar:
                    out = values
                else:
                    out[:] = values
                out *= self._fastCoeffs[0]*y + self._fastCoeffs[1]
                out += self._fastCoeffs[2]*y + self._fastCoeffs[3]
            else:
                out += values*y*self._fastCoeffs[0]
                out += values*self._fastCoeffs[1]
                out += y*self._fastCoeffs[2]
                out += self._fastCoeffs[3]

        else:
            raise

        return out


    def __call__(self, timestamp, value, session=None, noBivariates=False):
        """ Apply the polynomial to an event. 
        
            :param timestamp: The time of the event to process.
            :param value: The value of the event to process.
            :keyword session: The session containing the event.
            :keyword noBivariates: If `True`, the reference channel will not
                be used.
        """
        session = self.dataset.lastSession if session is None else session
        sessionId = None if session is None else session.sessionId
        
        try:
            if self._eventlist is None or self._sessionId != sessionId:
                channel = self.dataset.channels[self.channelId][self.subchannelId]
                self._eventlist = channel.getSession(session.sessionId)
                self._sessionId = session.sessionId
            if len(self._eventlist) == 0:
                return timestamp, value
            
            # Optimization: don't check the other channel if Y is unused
            if noBivariates:
                y = (0, 1)
            else:
                y = self._noY or self._eventlist.getMean()
            return timestamp, self._function(value, y)
        
        except (IndexError, ZeroDivisionError) as err:
            # In multithreaded environments, there's a rare race condition
            # in which the main channel can be accessed before the calibration
            # channel has loaded. This should fix it.
            logger.warning("%s occurred in Bivariate polynomial %r" %
                           err.__class__.__name__, self.id)
            return None

        except (IndexError, ZeroDivisionError) as err:
            # In multithreaded environments, there's a rare race condition
            # in which the main channel can be accessed before the calibration
            # channel has loaded. This should fix it.
            logger.warning("%s occurred in Bivariate polynomial %r" %
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


    def isValid(self, session=None, noBivariates=False, _retries=3):
        """ Check the validity of the Transform.
        
            :keyword session: The session to check (could be valid in one and
                invalid in another, e.g. one session has no temperature data).
            :keyword noBivariates: If `True`, the reference channel will not
                be used.
        """
        valid = super(Bivariate, self).isValid(session, noBivariates)
        if noBivariates or not valid:
            return valid
        
        session = self.dataset.lastSession if session is None else session
        sessionId = None if session is None else session.sessionId
        
        try:
            if self._eventlist is None or self._sessionId != sessionId:
                channel = self.dataset.channels[self.channelId][self.subchannelId]
                self._eventlist = channel.getSession(session.sessionId)
                self._sessionId = session.sessionId
            if len(self._eventlist) == 0:
                return False
            
        except:
            # HACK: In multithreaded environments, there's a rare race 
            # condition in which the main channel can be accessed before the
            # calibration channel has loaded. Retry isValid() a few times.
            if _retries == 0:
                return False
            
            return self.isValid(session, noBivariates, _retries-1)


    @property
    def useMean(self):
        return self._useMean


    @useMean.setter
    def useMean(self, value):
        self._useMean = value
        for w in self._watchers:
            w.useMean = self.useMean


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
        self._fastCoeffs = None
        
        if subchannel is not None:
            self.poly = self.poly[subchannel]

        self.kwargs = kwargs
        p = list(kwargs.values())[0]
        for attr in ('dataset', '_eventlist', '_sessionId', 'channelId',
                     'subchannelId', '_references', '_coeffs', '_variables'):
            setattr(self, attr, getattr(poly, attr, getattr(p, attr, None)))
                    
        self.dataset = self.dataset or dataset
        self._subchannel = subchannel
        self._watchers = weakref.WeakSet()
        self._build()

        self._useMean = True
    
    
    def _build(self):
        if self.poly is None:
            self.poly = Univariate((1, 0))
            if len(self.subpolys) == 1:
                p = list(self.subpolys.values())[0]
                if p is not None:
                    for attr in ('_str', '_source', '_function', '_noY'):
                        setattr(self, attr, getattr(p, attr, None))
        phead, _, src = self.poly.source.partition(": ")

        for k, v in self.subpolys.items():
            if v is None:
                ssrc = "lambda x: x"
            else:
                ssrc = v.source
            start, _, end = ssrc.rpartition(": ")
            s = "(%s)" % (end or start)
            src = self._reduce(src.replace(k, s))

        if self._subchannel is not None:
            src = src.replace('x', 'x[%d]' % self._subchannel)
        
        # Merge in all function globals, in case components use additional
        # libraries (e.g. math). 
        evalGlobals = {'math': math}
        if self.poly is not None: 
            evalGlobals.update(self.poly._function.__globals__)
        for p in self.subpolys.values():
            if p is not None:
                evalGlobals.update(p._function.__globals__)

        if isinstance(self.poly, Bivariate):
            # a0*(b0*x + b1)*(c0*y + c1) + a1*(b0*x + b1) + a2*(c0*y + c1) + a3 =
            # x*y*(a0*b0*c0) + x*(a0*b0*c1 + a1*b0) + y*(a0*b1*c0 + a2*c0) + (a0*b1*c1 + a1*b1 + a2*c1 + a3)
            a = self.poly._fastCoeffs
            if self.poly.variables[0] in self.subpolys:
                if self.subpolys[self.variables[0]] is not None and \
                        not isinstance(self.subpolys[self.variables[0]], ComplexTransform):
                    b = self.subpolys[self.variables[0]]._fastCoeffs
                else:
                    b = (1, 0)
            else:
                b = (1, 0)
            if self.poly.variables[1] in self.subpolys:
                if self.subpolys[self.variables[1]] is not None and \
                        not isinstance(self.subpolys[self.variables[1]], ComplexTransform):
                    c = self.subpolys[self.variables[1]]._fastCoeffs
                else:
                    c = (1, 0)
            else:
                c = (1, 0)
            self._fastCoeffs = (
                a[0]*b[0]*c[0],
                a[0]*b[0]*c[1] + a[1]*b[0],
                a[0]*b[1]*c[0] + a[2]*c[0],
                a[0]*b[1]*c[1] + a[1]*b[1] + a[2]*c[1] + a[3],
                )
        elif isinstance(self.poly, Univariate):
            # a0*(b0*x + b1) + a1 = a0*b0*x + (a1 + a0*b1)
            a = self.poly._fastCoeffs
            b = self.subpolys[self.poly.variables[0]]
            if b is None:
                b = (1., 0.)
            else:
                b = b._fastCoeffs
            self._fastCoeffs = (a[0]*b[0], a[1] + a[0]*b[1])
        
        self._str = src
        self._source = "%s: %s" % (phead, src)
        self._function = eval(self._source, evalGlobals)
        self._noY = (0, 1) if 'y' not in src else False

        for x in [self.poly] + list(self.subpolys.values()):
            if x is not None:
                x.addWatcher(self)

    def inplace(self, values, y=None, timestamp=None, session=None, noBivariates=False, out=None):
        """ In-place transform for the `CombinedPoly` transform.  It reduces the
            number of array allocations/operations compared to the normal
            `__call__` method.  The user can supply an `out` argument to save
            the results to that array, or leave `out` equal to `None`.  If `out`
            is `None`, then this method will allocate an array in the shape of
            `values`.

            If any component polynomials are a `ComplexTransform`, those will be
            calculated first.

            If the main polynomial is a `Complex Transform`, then all values
            will be calculated separately.

            If the component polynomials of this `CombinedPoly` are all
            `Univariate`, then the following equation will be used.  Otherwise,
            the rest of the documentation will detail how a `CombinedPoly` based
            on a `Bivariate` behaves.

            The method uses the following algebra, calculated in the `_build`
            method, to reduce the equation to fewer operations.  For brevity:
                `x` = `values`
                `xref`, `yref` = `references`
                `an` = `poly.coeffs[n]`
                `bn` = `subpoly['x']._fastCoeffs[n]`
                `cn` = `_fastCoeffs[n]`

            `f(x) = a0*(b0*x + b1 - xref) + a1`
             =>
            `f(x) = x*(a0*b0) + (a0*(b1 - xref) + a1)`
             =>
            `f(x) = c0*x + c1`

            When calculating the `y` value, several things need to be taken into
            account in the following priority:
            1. If `noBivariates` is `True`, then `y` must be equal to `0`.
            2. If `self.useMean` is `True`, then `y` is equal to the mean of the
               full length of the secondary channel.
            3. If `y` is provided, then use the provided value.
            4. If `timestamp` is provided, then get the values for the given `timestamp`.
            5. Otherwise, default to the mean of the secondary channel.

            Depending on if `y` is scalar, one of two methods will be used, detailed below.

            The method uses the following algebra, calculated in the `_build`
            method, to reduce the equation to fewer operations.  For brevity:
                `x` = `values`
                `xref`, `yref` = `references`
                `an` = `poly.coeffs[n]`
                `bn` = `subpoly['x']._fastCoeffs[n]`
                `cn` = `subpoly['y']._fastCoeffs[n]`
                `dn` = `_fastCoeffs[n]`

            `y` is not scalar:

              `f(x) = a0*(b0*x + b1 - xref)*(c0*y + c1 - yref) + a1*(b0*x + b1 - xref) +
                    + a2*(c0*y + c1 - yref) + a3`
               =>
              `f(x) = x*y*(a0*b0*c0) + x*(a0*b0*(c1 - yref) + a1*b0) +
                    + y*(a0*(b1 - xref)*c0 + a2*c0) +
                    + (a0*(b1 - xref)*(c1 - yref) + a1*(b1 - xref) + a2*(c1 - yref) + a3)`
               =>
              `f(x) = d0*x*y + d1*x + d2*y + d3`

            `y` is scalar:

              `f(x) = d0*x*y + d1*x + d2*y + d3`
               =>
              `f(x) = x*(d0*y + d1) + (d2*y + d3)`
        """

        scalar = np.isscalar(values)

        # Catches the case where the first subpoly is a `ComplexTransform`
        if self.variables and \
                self.variables[0] in self.subpolys and \
                isinstance(self.subpolys[self.variables[0]], ComplexTransform):
            values = self.subpolys[self.variables[0]].inplace(
                    values,
                    timestamp=timestamp,
                    session=session,
                    noBivariates=noBivariates,
                    )

        if scalar:
            values = float(values)
        elif out is None:
            out = np.zeros_like(values, dtype=np.float64)

        if self.variables is None:
            if scalar:
                return values
            out[:] = values
            return out

        try:
            if len(self.variables) == 1:
                if isinstance(self.poly, ComplexTransform):

                    if self.variables[0] in self.subpolys and not isinstance(self.subpolys[self.variables[0]], ComplexTransform):
                        values = self.subpolys[self.variables[0]].inplace(
                                values,
                                timestamp=timestamp,
                                session=session,
                                noBivariates=noBivariates,
                                )

                    if scalar:
                        out = self.poly.function(values)
                    else:
                        out[:] = self.poly.function(values)
                else:
                    if scalar:
                        out = values
                    else:
                        out[:] = values

                    out *= self._fastCoeffs[0]
                    out += self._fastCoeffs[1]
            else:

                session = self.dataset.lastSession if session is None else session
                sessionId = None if session is None else session.sessionId

                if self._eventlist is None or self._sessionId != sessionId:
                    channel = self.dataset.channels[self.channelId][self.subchannelId]
                    self._eventlist = channel.getSession(session.sessionId)
                    self._sessionId = session.sessionId

                if noBivariates:
                    y = 0
                elif self.useMean:
                    y = self._eventlist.getMean()
                elif y is None and timestamp is None:
                    y = self._eventlist.getMean()
                elif y is None and timestamp is not None:
                    y = np.fromiter(
                            (self._eventlist[self._eventlist.getEventIndexNear(t)][0] for t in
                             timestamp), dtype=np.float64)

                # Catches the case where the secondary subpoly is a `ComplexTransform`
                if self.variables[1] in self.subpolys and isinstance(self.subpolys[self.variables[1]], ComplexTransform):
                    y = self.subpolys[self.variables[1]].inplace(
                            y,
                            timestamp=timestamp,
                            session=session,
                            noBivariates=noBivariates,
                            )

                # in this instance, basically give up on efficiency
                if isinstance(self.poly, ComplexTransform):

                    if self.variables[0] in self.subpolys and not isinstance(self.subpolys[self.variables[0]], ComplexTransform):
                        values = self.subpolys[self.variables[0]].inplace(
                                values,
                                timestamp=timestamp,
                                session=session,
                                noBivariates=noBivariates,
                                )

                    if self.variables[1] in self.subpolys and not isinstance(self.subpolys[self.variables[1]], ComplexTransform):
                        y = self.subpolys[self.variables[1]].inplace(
                                y,
                                timestamp=timestamp,
                                session=session,
                                noBivariates=noBivariates,
                                )

                    if scalar:
                        out = self.poly.inplace(
                                values,
                                y=y,
                                timestamp=timestamp,
                                session=session,
                                noBivariates=noBivariates,
                                )
                    else:

                        out[:] = self.poly.inplace(
                                values,
                                y=y,
                                timestamp=timestamp,
                                session=session,
                                noBivariates=noBivariates,
                                )

                else:

                    if np.isscalar(y):
                        # a2*x*y + b2*x + c2*y + d2 =
                        # x*(a2*y + b) + (c2*y + d2) =
                        # x*a3 + b3
                        if scalar:
                            out = values
                        else:
                            out[:] = values
                        a3 = self._fastCoeffs[0]*y + self._fastCoeffs[1]
                        b3 = self._fastCoeffs[2]*y + self._fastCoeffs[3]
                        out *= a3
                        out += b3
                    else:
                        if np.scalar:
                            out = values*y*self._fastCoeffs[0]
                        else:
                            out[:] = values*y*self._fastCoeffs[0]
                        out += values*self._fastCoeffs[1]
                        out += y*self._fastCoeffs[2]
                        out += self._fastCoeffs[3]

            return out

        except (IndexError, ZeroDivisionError) as err:
            # In multithreaded environments, there's a rare race condition
            # in which the main channel can be accessed before the calibration
            # channel has loaded. This should fix it.
            logger.warning("%s occurred in Bivariate polynomial %r" %
                           err.__class__.__name__, self.id)
            return None
        
        
    def asDict(self):
        """ Dump the polynomial as a dictionary. Intended for use when
            generating EBML.
        """
        raise TypeError("Can't generate dictionary for %s" %
                        self.__class__.__name__)

    
    def isValid(self, session=None, noBivariates=False):
        """ Check the validity of the Transform.
        """
        if not Transform.isValid(self, session, noBivariates):
            return False
        return all(p.isValid(session, noBivariates) for p in self.subpolys.values())
        

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
        for attr in ('dataset', '_eventlist', '_sessionId', 'channelId', 'subchannelId'):
            setattr(self, attr, getattr(poly, attr, None))
        
        self.dataset = self.dataset or dataset
        self._eventlist = None
        self._watchers = weakref.WeakSet()
        self._build()

        self._useMean = True


    def _build(self):
        params = []
        body = []
        for n, p in enumerate(self.polys):
            params.append('x%d' % n)
            if p is None:
                body.append('x%d' % n)
            else:
                start, _, end = p.source.rpartition(':')
                body.append((end or start).replace('x', 'x%d' % n))
        
        # ends with a comma to ensure a tuple is returned
        src = "(%s,)" % (', '.join(body))
        self._str = src

        if 'y' in src:
            params.insert(0, 'y')
            self._noY = False
        else:
            self._noY = (0, 1)
        
        # Merge in all function globals, in case components use additional
        # libraries (e.g. math). 
        evalGlobals = {'math': math}
        for p in self.polys:
            if p is not None:
                evalGlobals.update(p._function.__globals__)
                p.addWatcher(self)
        
        self._source = "lambda %s: %s" % (','.join(params), src)
        self._function = eval(self._source, evalGlobals)
        self._variables = params


    def __call__(self, timestamp, values, session=None, noBivariates=False):
        """ Apply the polynomial to an event. 
        
            :param timestamp: The time of the event to process.
            :param values: The values of the event to process.
            :keyword session: The session containing the event.
        """
        try:
            # Optimization: don't check the other channel if Y is unused
            if self._noY is False:
                if noBivariates:
                    return timestamp, self._function(0, *values)
                    
                session = self.dataset.lastSession if session is None else session
                sessionId = None if session is None else session.sessionId
                
                if self._eventlist is None or self._sessionId != sessionId:
                    channel = self.dataset.channels[self.channelId][self.subchannelId]
                    self._eventlist = channel.getSession(session.sessionId)
                    self._sessionId = session.sessionId
                
                # XXX: Hack! EventList length can be 0 if a thread is running.
                # This almost immediately gets fixed. Find real cause.
                try:    
                    y = self._eventlist.getMean()
                except IndexError:
                    sleep(0.001)
                    if len(self._eventlist) == 0:
                        return None
                    y = self._eventlist.getMean()
                    
                return timestamp, self._function(y, *values)
            
            else:
                return timestamp, self._function(*values)
            
        except (TypeError, IndexError, ZeroDivisionError) as err:
            # In multithreaded environments, there's a rare race condition
            # in which the main channel can be accessed before the calibration
            # channel has loaded. This should fix it.
            if getattr(self.dataset, 'loading', False):
                logger.warning("%s occurred in combined polynomial %r" %
                               (err.__class__.__name__, self))
                return None
            raise


    def inplace(self, values, y=None, timestamp=None, session=None, noBivariates=False, out=None):
        """ In-place transform for the `PolyPoly` transform.  It reduces the
            number of array allocations/operations compared to the normal
            `__call__` method.  The user can supply an `out` argument to save
            the results to that array, or leave `out` equal to `None`.  If `out`
            is `None`, then this method will allocate an array in the shape of
            `values`.

            This method does not do any calculations, and instead leaves that to
            its member polynomials.
        """
        if out is None:
            out = np.zeros_like(values, dtype=np.float64)

        try:
            # Optimization: don't check the other channel if Y is unused
            if self._noY is False:
                if noBivariates:
                    for i, poly in enumerate(self.polys):
                        if np.isscalar(out[i]):
                            out[i] = poly.inplace(values[i], y=0)
                        else:
                            poly.inplace(values[i], y=0, out=out[i])
                    return out

                session = self.dataset.lastSession if session is None else session
                sessionId = None if session is None else session.sessionId

                if self._eventlist is None or self._sessionId != sessionId:
                    channel = self.dataset.channels[self.channelId][self.subchannelId]
                    self._eventlist = channel.getSession(session.sessionId)
                    self._sessionId = session.sessionId

                # XXX: Hack! EventList length can be 0 if a thread is running.
                # This almost immediately gets fixed. Find real cause.
                try:
                    y = self._eventlist.getMean()
                except IndexError:
                    sleep(0.001)
                    if len(self._eventlist) == 0:
                        return None
                    y = self._eventlist.getMean()

                for i, poly in enumerate(self.polys):
                    if np.isscalar(out[i]):
                        out[i] = poly.inplace(values[i], y=y)
                    else:
                        poly.inplace(values[i], y=y, out=out[i])
                return out

            else:
                for i, poly in enumerate(self.polys):
                    if np.isscalar(out[i]):
                        out[i] = poly.inplace(values[i])
                    else:
                        poly.inplace(values[i], out=out[i])
                return out

        except (TypeError, IndexError, ZeroDivisionError) as err:
            # In multithreaded environments, there's a rare race condition
            # in which the main channel can be accessed before the calibration
            # channel has loaded. This should fix it.
            if getattr(self.dataset, 'loading', False):
                logger.warning("%s occurred in combined polynomial %r"%
                               (err.__class__.__name__, self))
                return None
            raise


    def isValid(self, session=None, noBivariates=False):
        """ Check the validity of the Transform.
        """
        if not Transform.isValid(self, session, noBivariates):
            return False
        return all(p.isValid(session, noBivariates) for p in self.polys)
