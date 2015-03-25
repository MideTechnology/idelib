'''
Data type conversion. Each class contains two special attributes:

* conversion: A tuple containing a pair of tuples, the label and units of the
    'from' and 'to'. 
* parameters: If the converter has additional parameters, these are listed
    here. 

@author: dstokes
'''

import math

from calibration import Transform, Univariate
from dataset import Channel

#===============================================================================
# 
#===============================================================================

CONVERTERS = []

def registerConverter(cls):
    """ Decorator. Used to register classes as parsers of data payloads. 
    """
    global CONVERTERS
    CONVERTERS.append(cls)
    return cls


#===============================================================================
# 
#===============================================================================

class UnitConverter(object):
    """ Mix-in class for unit conversion transforms.
    """
    modifiesValue = True
    modifiesTime = False
    parameters = None
    
    @classmethod
    def isApplicable(cls, obj):
        if isinstance(obj, Channel):
            sourceUnits = obj.units
        else:
            sourceUnits = obj.parent.units
        fromUnits = cls.convertsFrom
        if sourceUnits is None:
            return False
        if sourceUnits == fromUnits:
            return True
        if None not in cls.convertsFrom:
            return False
        units = (fromUnits[0] or sourceUnits[0], fromUnits[1] or sourceUnits[1])
        return units == sourceUnits
    
    def convert(self, v):
        return self.function(v)

#===============================================================================
# Simple converters
#===============================================================================

@registerConverter
class Celsius2Fahrenheit(UnitConverter, Univariate):
    """ Convert degrees Celsius to Fahrenheit. 
    """
    convertsFrom = (u'Temperature',u'\xb0C')
    units = (u'Temperature',u'\xb0F')
    
    def __init__(self, calId=None, dataset=None, varName="x"):
        """
        """
        super(Celsius2Fahrenheit, self).__init__((1.8, 32), calId=calId,
                                                 dataset=dataset, varName=varName)

@registerConverter
class Celsius2Kelvin(Celsius2Fahrenheit):
    """ Convert degrees Celsius to Kelvin. 
    """
    units = (u'Temperature',u'\xb0K')

    def __init__(self, calId=None, dataset=None, varName="x"):
        """
        """
        super(Celsius2Kelvin, self).__init__((1, 273.15), calId=calId,
                                             dataset=dataset, varName=varName)    

@registerConverter
class Gravity2MPerSec2(UnitConverter, Univariate):
    """ Convert acceleration from g to m/s^2.
    """
    convertsFrom = (u'Acceleration',u'g')
    units = (u'Acceleration',u'm/s\u00b2')
    
    def __init__(self, calId=None, dataset=None, varName='x'):
        super(Gravity2MPerSec2, self).__init__((9.806649999788,0), calId=calId,
                                               dataset=dataset, varName=varName)

@registerConverter
class Meters2Feet(UnitConverter, Univariate):
    """ Convert meters to feet.
    """
    convertsFrom = (None, 'm')
    units = (None, 'ft')
    
    def __init__(self, calId=None, dataset=None, varName='x'):
        super(Meters2Feet, self).__init__((3.2808399, 0), calId=calId, 
                                          dataset=dataset, varName=varName)

@registerConverter
class Pa2PSI(UnitConverter, Univariate):
    """ Convert air pressure from Pascals to pounds per square inch.
    """
    convertsFrom = ('Pressure','Pa')
    units = ('Pressure', 'psi')
    
    def __init__(self, calId=None, dataset=None, varName='x'):
        super(Pa2PSI, self).__init__((0.000145037738, 0), calId=calId,
                                     dataset=dataset, varName=varName)

@registerConverter
class Pa2atm(UnitConverter, Univariate):
    """ Convert air pressure from Pascals to atmospheres.
    """
    convertsFrom = ('Pressure','Pa')
    units = ('Pressure', 'atm')
    # 9.86923266716e-06
    
    def __init__(self, calId=None, dataset=None, varName='x'):
        super(Pa2atm, self).__init__((9.86923266716e-06, 0), calId=calId,
                                     dataset=dataset, varName=varName)

#===============================================================================
# More complex conversion
#===============================================================================

@registerConverter
class Pressure2Meters(UnitConverter, Transform):
    """ Convert pressure in Pascals to an altitude in meters.
    """
    convertsFrom = ('Pressure','Pa')
    units = ('Altitude', 'm')
    
    # Parameters: name, description, type, range, and default value.
    # The names must match keyword arguments in __init__ and object attributes.
    parameters = (('temp', u'Temperature at sea level (\xb0C)', float, (-100,100), 20.0),
                  ('sealevel', u'Pressure at sea level (Pa)', int, (0,150000), 101325.0))
    
    def __init__(self, calId=None, dataset=None, temp=20.0, sealevel=101325.0):
        """ Constructor.
            @keyword dataset: The `Dataset` to which this applies. 
            @keyword temp: Temperature at sea level (degrees C)
            @keyword sealevel: Air pressure at sea level (Pascals)
        """
        self._sealevel = sealevel
        self._temp = temp
        self.id = calId
        self._lastSession = None
        self._timeOffset = 0
        self._build()

    def _build(self):
        # This is sort of a special case; the function is too complex to
        # nicely represent as a lambda, so the 'source' calls the object itself.
        # This is so the polynomial combination/reduction will work.
        # `_function` is never actually called; `function` is overridden.
        self._str = "Pressure2Meters.convert(x)"
        self._source = "lambda x: %s" % self._str
        self._function = eval(self._source, 
                              {'Pressure2Meters': self, 'math': math})
    
        
    @property
    def sealevel(self):
        return self._sealevel
    
    @sealevel.setter
    def sealevel(self, p):
        self._sealevel = p
        self._build()
        
    @property
    def temp(self):
        return self._temp
    
    @temp.setter
    def temp(self, t):
        self._temp = t
        self._build()


    def function(self, press):
        if ((self._sealevel/press) < 4.47704808656731):
            L_b = -0.0065 # [K/m] temperature lapse rate
            h_b = 0.0  # [m] height above sea level (differing altitudes have differing time lapse rates
            foo = math.pow((press/self._sealevel), -1.8658449683059204)
            return h_b+((self._temp*((1.0/foo)-1.0))/L_b)
        
        elif ((self._sealevel/press / press) < (18.507221149648668)):
            h_2 = (8.31432*self.T_2*(math.log(press/self._sealevel/press)))/-338.5759760257419
            return self.h_1+h_2
        
        return 0.0 # Is this okay?


@registerConverter
class Pressure2Feet(Pressure2Meters):
    """ Convert pressure in Pascals to an altitude in feet.
    """
    convertsFrom = ('Pressure','Pa')
    units = ('Altitude', 'ft')
    
    def _build(self):
        super(Pressure2Feet, self)._build()
        self._str = "3.2808399*(%s)" % self._str
        self._source = "lambda x: %s" % self._str

    def function(self, press):
        return 3.2808399*Pressure2Meters.function(self, press)


#===============================================================================
# 
#===============================================================================

def getApplicableConverters(doc):
    """ Get all unit converters applicable to any part of the given Dataset.
    
        @param doc: a `Dataset` instance.
        @return: A list of `UnitConverter` classes.
    """
    global CONVERTERS
    results = {}
    for p in doc.getPlots():
        for c in CONVERTERS:
            if c.isApplicable(p):
                results[c] = True
    return results.keys()