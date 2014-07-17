'''
Calibration and Transform classes. These are callable objects that modify
data. Functionally, calibration is the same as a Transform, the difference
being in how they are used.

Created on Nov 27, 2013

@author: dstokes

@todo: Use regex to optimize built univariate and bivariate functions
'''

# __all__ = ['Transform', 'AccelTransform', 'AccelTransform10G', 
#            'Univariate', 'Bivariate']


#===============================================================================
# 
#===============================================================================

class Transform(object):
    """ A function-like object representing any processing that an event
        requires, including basic calibration at the low level and 
        adjustments for display at the high level.
    """
    modifiesTime = False
    modifiesValue = False
    
    def __init__(self, *args, **kwargs):
        pass
    
    def __call__(self,  event, session=None):
        if session is None:
            return event
        return event[0] + session.startTime, event[1]

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
     
    def __init__(self, amin=-100, amax=100):
        self.range = (amin, amax)
        self._fun = lambda x: (x / 32767.0) * amax
     
    def __repr__(self):
        return "<%s%r at 0x%08x>" % (self.__class__.__name__, self.range, 
                                     id(self))
     
    def __call__(self, event, session=None):
        return event[:-1] + (self._fun(event[-1]),)
     
     
    
class AccelTransform100(Transform):
    """ A simple transform to convert accelerometer values (parsed as
        int16) to floats in the range -100 to 100 G.
        
        This assumes that the data was parsed by `AccelerometerParser`, which
        puts the raw values in the range -32768 to 32767.
    """
    modifiesValue = True
    
    def __call__(self, event, session=None):
#         return event[:-1] + ((event[-1] * 200.0) / 65535 - 100,)
        return event[:-1] + ((event[-1] / 32767.0) * 100.0,)


class AccelTransform25G(Transform):
    """ A simple transform to convert accelerometer values (parsed as
        int16) to floats in the range -25 to 25 G.
        
        This assumes that the data was parsed by `AccelerometerParser`, which
        puts the raw values in the range -32768 to 32767.
    """
    modifiesValue = True
    def __call__(self, event, session=None):
#         return event[:-1] + ((event[-1] * 50.0) / 65535 - 25,)
        return event[:-1] + ((event[-1] / 32767) * 25.0,)


class AccelTransform200G(Transform):
    """ A simple transform to convert accelerometer values (parsed as
        int16) to floats in the range -25 to 25 G.
        
        This assumes that the data was parsed by `AccelerometerParser`, which
        puts the raw values in the range -32768 to 32767.
    """
    modifiesValue = True
    def __call__(self, event, session=None):
#         return event[:-1] + ((event[-1] * 50.0) / 65535 - 25,)
        return event[:-1] + ((event[-1] / 32767) * 25.0,)



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

    def _floatOrInt(self, v):
        " Helper method to convert floats with no decimal component to ints. "
        iv = int(v)
        return iv if iv == v else v
    
    def _stremove(self, s, old):
        " Helper method to remove a set of substrings from a string. "
        result = str(s)
        for o in old:
            result = result.replace(o,'')
        return result
    
    def _fixSums(self, s):
        " Helper method to replace consecutive addition/subtraction combos. "
        result = str(s)
        for old, new in (("--", "+"), ("-+", "-"), ("+-", "-"), ("++", "+")):
            result = result.replace(old, new)
        return result
    
    def __init__(self, coeffs, calId=None, dataset=None, reference=0, 
                 varName="x"):
        """ Construct a simple polynomial function from a set of coefficients.
            
            @param coeffs: A list of coefficients
            @keyword references: A reference value to be subtracted from the
                variable.
            @keyword varName: The name of the variable to be used in the
                string version of the polynomial. For display purposes.
        """
        self.id = calId
        self.dataset = dataset
        varName = str(varName)
        srcVarName = "x"
        self._coeffs = tuple(coeffs)
        self._variables = (varName,)
        self._references = (reference,)
        
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
    
            # optimization: v is a whole number, do integer math,
            # then make float by adding 0.0
            if v != 1 and int(v) == v:
                v = int(v)
    
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
        if '.' not in self._source:
            self._source ="%s+0.0" % self._source
        self._source = self._fixSums(self._source)
        self._function = eval(self._source)
    
    
    @property
    def coefficients(self):
        """ The polynomial's coefficients. """
        return self._coeffs
        
    @property
    def source(self):
        """ The optimized source code of the polynomial. """
        return self._source
    
    @property
    def variables(self):
        """ The name(s) of the variable(s) used in the polynomial. """
        return self._variables
    
    @property
    def references(self):
        """ The constant offset(s). """
        return self._references
    
    @property
    def function(self):
        """ The generated polynomial function itself. """
        return self._function
    
    def __str__(self):
        return self._str
    
    def __repr__(self):
        return "<%s (%s)>" % (self.__class__.__name__, self._str)


    def __call__(self, event, session=None):
        """ Apply the polynomial to an event. 
        
            @param event: The event to process (a time/value tuple or a
                `dataset.Event` named tuple).
            @keyword session: The session containing the event. Not used in
                this transform.
        """
        result = list(event)
        result[-1] = self._function(event[-1])
        return tuple(result)


class Bivariate(Univariate):
    """ A two-variable polynomial in the general form
        `v=(A*x*y)+(B*x)+(C*y)+D`.
        
        Instances are function-like objects that take one argument: a sensor
        reading time and value.
    """
    
    def __init__(self, coeffs, dataset=None, channelId=None, subchannelId=None, 
                 reference=0, reference2=0, varNames="xy", calId=None):
        """ Construct the two-variable polynomial.
            
            @param coeffs: A list of coefficients. Must contain 4!
            @keyword references: A reference value to be subtracted from the
                variables.
            @keyword varNames: The names of the variables to be used in the
                string version of the polynomial. For display purposes; they
                can be any arbitrary (but hopefully meaningful) strings.
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
        self._str = self._str.replace("x","\0"
                                      ).replace("y", varNames[1]
                                                ).replace("\0", varNames[0])

        # Optimizations: Build a simplified expression for function.
        # 1. Remove multiples of 0 and 1, addition of 0 constants.      
        src = self._stremove(src, ('(0*x*y)+', '(0*x)+', '(0*y)+'))
        src = src.replace("(1*", "(")
        src = src.replace("(x)", "x").replace("(y)", "y")
        if src.endswith('+0'):
            src = src[:-2]

        # 2. If there's a reference value, replace the variable with (v-ref)           
        references = map(self._floatOrInt, (reference, reference2))
        for i,v in enumerate("xy"):
            if references[i] != 0:
                src = src.replace(v, "(%s-%s)" % (v, references[i]))  
        
        # 3. Make sure the result is floating point. Also handles the edge-case
        # of all-zero coefficients (shouldn't exist, but could).
        if '.' not in src:
            src = "+".join([src, "0.0"])
        
        self._source = 'lambda x,y: %s' % self._fixSums(src)
        self._function = eval(self._source)


    def __call__(self, event, session=None):
        """ Apply the polynomial to an event. 
        
            @param event: The event to process (a time/value tuple or a
                `Dataset.Event` named tuple).
            @keyword session: The session containing the event.
        """
        session = self.dataset.lastSession if session is None else session
        sessionId = None if session is None else session.sessionId
        
        try:
            if self._eventlist is None or self._sessionId != sessionId:
                channel = self.dataset.channels[self.channelId][self.subchannelId]
                self._eventlist = channel.getSession(session.sessionId)
                self._sessionId = session.sessionId
                
            x = event[-1]
            y = self._eventlist.getValueAt(event[-2], outOfRange=True)
            return event[-2],self._function(x,y[-1])
        except IndexError:
            # In multithreaded environments, there's a rare race condition
            # in which the main channel can be accessed before the calibration
            # channel has loaded. This should fix it.
            return event