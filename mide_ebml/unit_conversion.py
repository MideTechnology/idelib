'''
Data type conversion. Each class contains two special attributes:

* conversion: A tuple containing a pair of tuples, the label and units of the
    'from' and 'to'. 
* parameters: If the converter has additional parameters, these are listed
    here. 

@author: dstokes
'''

import math

# from calibration import Transform
from calibration import Univariate
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

class UnitConverter(Univariate):
    """ Mix-in class for unit conversion transforms.
    """
    modifiesValue = True
    modifiesTime = False
    parameters = None
    
    @classmethod
    def isApplicable(cls, obj):
        """ Is this converter applicable to the given object?
         
            @param obj: A `Channel` or `EventList` (or a subclass of either).
                Can also be a list or tuple of said objects. In the latter case,
                the applicability of each item is tested, and `True` returned
                if they are all applicable.
        """
        if isinstance(obj, (list, tuple)):
            if len(obj) == 0:
                return False
            return all(map(cls.isApplicable, obj))
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
    
    def revert(self, v):
        """ Convert a value back to the original units. Primarily for display
            purposes.
        """
        # TODO: Make this work on Univariates with more than 2 coefficients.
        # May never be needed.
        a,b = self.coefficients
        ref = self.references[0]
        return ((v-b)/a)+ref

#===============================================================================
# Simple converters
#===============================================================================

@registerConverter
class Celsius2Fahrenheit(UnitConverter):
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
class Celsius2Kelvin(UnitConverter):
    """ Convert degrees Celsius to Kelvin. 
    """
    convertsFrom = (u'Temperature',u'\xb0C')
    units = (u'Temperature',u'\xb0K')

    def __init__(self, calId=None, dataset=None, varName="x"):
        """
        """
        super(Celsius2Kelvin, self).__init__((1, 273.15), calId=calId,
                                             dataset=dataset, varName=varName)
        

@registerConverter
class Gravity2MPerSec2(UnitConverter):
    """ Convert acceleration from g to m/s^2.
    """
    convertsFrom = (u'Acceleration',u'g')
    units = (u'Acceleration',u'm/s\u00b2')
    
    def __init__(self, calId=None, dataset=None, varName='x'):
        super(Gravity2MPerSec2, self).__init__((9.806649999788,0), calId=calId,
                                               dataset=dataset, varName=varName)

@registerConverter
class Meters2Feet(UnitConverter):
    """ Convert meters to feet.
    """
    convertsFrom = (None, 'm')
    units = (None, 'ft')
    
    def __init__(self, calId=None, dataset=None, varName='x'):
        super(Meters2Feet, self).__init__((3.2808399, 0), calId=calId, 
                                          dataset=dataset, varName=varName)

@registerConverter
class Pa2PSI(UnitConverter):
    """ Convert air pressure from Pascals to pounds per square inch.
    """
    convertsFrom = ('Pressure','Pa')
    units = ('Pressure', 'psi')
    
    def __init__(self, calId=None, dataset=None, varName='x'):
        super(Pa2PSI, self).__init__((0.000145037738, 0), calId=calId,
                                     dataset=dataset, varName=varName)

@registerConverter
class Pa2atm(UnitConverter):
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
class Pressure2Meters(UnitConverter):
    """ Convert pressure in Pascals to an altitude in meters.
    """
    convertsFrom = ('Pressure','Pa')
    units = ('Altitude', 'm')
    
    # Parameters: name, description, type, range, and default value.
    # The names must match keyword arguments in __init__ and object attributes.
    parameters = (('temp', u'Temperature at sea level (\xb0C)', float, (-100,100), 15.0),
                  ('sealevel', u'Pressure at sea level (Pa)', int, (0,150000), 101325.0))
    
    def copy(self):
        """ Create a duplicate of this unit converter.
        """
        t = self.__class__(self.id, self.dataset, self._temp, self._sealevel)
        return t
    
    def __init__(self, calId=None, dataset=None, temp=15.0, sealevel=101325.0):
        """ Constructor.
            @keyword dataset: The `Dataset` to which this applies. 
            @keyword temp: Temperature at sea level (degrees C)
            @keyword sealevel: Air pressure at sea level (Pascals)
        """
        self._sealevel = sealevel
        self._temp = temp
        self._tempK = temp + 273.15
        self.id = calId
        self._lastSession = None
        self._timeOffset = 0
        self._build()

    def __hash__(self):
        return hash((self.__class__, self._temp, self._sealevel))

    def _build(self):
        # This is sort of a special case; the function is too complex to
        # nicely represent as a lambda, so the 'source' calls the object itself.
        # This is so the polynomial combination/reduction will work.
        # `_function` is never actually called; `function` is overridden.
        self.T_2 = self._tempK - 71.5
        self.h_1 = ((8.31432*self.T_2*(math.log(101325/22632.1)))/((-9.80665)*0.0289644))
        self._str = "Pressure2Meters.convert(x)"
        self._source = "lambda x: %s" % self._str
        self._function = eval(self._source, 
                              {'Pressure2Meters': self, 'math': math})
    
        
    @property
    def sealevel(self):
        return self._sealevel
    
    @sealevel.setter
    def sealevel(self, p):
        self._sealevel = float(p)
        self._build()
        
    @property
    def temp(self):
        return self._temp
    
    @temp.setter
    def temp(self, t):
        self._temp = t
        self._tempK = t + 273.15
        self._build()


    def function(self, p):
        sp = self._sealevel / p
        if (sp < 4.47704808656731):
            foo = math.pow((p/self._sealevel), -0.1902632365084836)
            return ((self._tempK*((1.0/foo)-1.0))/-0.0065)
        elif (sp < 18.507221149648668):
            T_2 = self._tempK - 71.5
#             h_2 = (8.31432*T_2*(math.log(p/self._sealevel)))/-0.28404373326
#             h_1 = ((T_2*12.462865699354536)/-0.28404373326)+11000
            h_2 = (T_2*math.log(p/self._sealevel))/-0.03416319473631036
            h_1 = (T_2/-0.02279120549896569)+11000.0
            return h_1+h_2
        
        return 20000.0


    def revert(self, h):
        M = 0.0289644 # [kg/mol] molar mass of Earth's air
        g = 9.80665 # [m/s^2] gravitational acceleration constant
        R = 8.31432 # [(N*m)/(mol*k)] universal gas constant
        
        t = self._tempK
        p_a = self._sealevel
        
        if h < 11000:
            L_a = -0.0065 #; // [K/m] temperature lapse rate
            h_a = 0.0 #;  // [m] height above sea level (differing altitudes have differing time lapse rates
            return self._sealevel*math.pow(self._tempK/(self._tempK+(L_a*(h-h_a))),(g*M)/(R*L_a))
        elif h <= 20000:
            L_a = -0.0065
            h_a = 0.0
            h_b = 11000
            p_b = p_a*math.pow(t/(t+(L_a*(h_b-h_a))),(g*M)/(R*L_a))
            T_1 = t+(11000*(-0.0065))
            return p_b*math.exp(((-g)*M*(h-h_b))/(R*T_1))
        
        return 5474.89
             

@registerConverter
class Pressure2Feet(Pressure2Meters):
    """ Convert pressure in Pascals to an altitude in feet.
    """
    convertsFrom = ('Pressure','Pa')
    units = ('Altitude', 'ft')
    
    def _build(self):
        super(Pressure2Feet, self)._build()
        self._str = "Pressure2Feet.convert(x)"
        self._source = "lambda x: %s" % self._str
        self._function = eval(self._source, 
                              {'Pressure2Feet': self, 'math': math})

    def function(self, press):
        return 3.2808399*Pressure2Meters.function(self, press)

    def revert(self, v):
        return Pressure2Meters.revert(self, v/3.2808399)

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