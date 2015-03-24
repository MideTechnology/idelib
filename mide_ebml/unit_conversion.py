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
    modifiesValue = True
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
    modifiesValue = True
    parameters = None
    convertsFrom = ('Altitude', 'm')
    units = ('Altitude', 'ft')
    
    def __init__(self, calId=None, dataset=None, varName='x'):
        super(Meters2Feet, self).__init__((3.2808399, 0), calId=calId, 
                                          dataset=dataset, varName=varName)


#===============================================================================
# More complex conversion
#===============================================================================

@registerConverter
class Pressure2Meters(UnitConverter, Transform):
    """ Convert pressure in Pascals to an altitude in meters.
    """
    modifiesValue = True
    
    convertsFrom = ('Pressure','Pa')
    units = ('Altitude', 'm')
    
    parameters = (('temp', 'Temperature at sea level', float),
                  ('sealevel', 'Pressure at sea level', float))
    
    def __init__(self, calId=None, dataset=None, temp=20.0, sealevel=101325.0):
        """
        """
        self._sealevel = sealevel
        self._temp = temp
        self.id = calId
        self._lastSession = None
        self._timeOffset = 0
        self._build()

    def _build(self):
        self._str = "pa2m.convert(x)"
        self._source = "lambda x: %s" % self._str
        self._function = eval(self._source, {'pa2m': self, 'math': math})
        return
    
        self.T_2 = self.temp - 71.5
        self.h_1 = (self.T_2*-0.0368096575)+11000
        
        params = dict(sealevel=self._sealevel,
                    temp=self._temp,
                    T_2=self.T_2,
                    L_b=-0.0065, # [K/m] temperature lapse rate
                    h_b = 0.0,  # [m] height above sea level (differing altitudes have differing time lapse rates
                    T_2a = 8.31432*self.T_2,
                    T_2b = (self.T_2*-0.03680966)+11000,
                    v1 = 4.477048/self._sealevel,
                    v2 = 18.507221/self._sealevel
                    )
#         self._str = ("(%(h_b)s+(x*((1.0/math.pow(x/%(sealevel)s, -1.865845))-1.0))/%(L_b)s) if %(sealevel)s/x < 4.477048 " \
#                      "else ((8.31432*%(T_2)s*(math.log(x/%(sealevel)s)))/-338.575976)+(%(T_2)s*-0.03680966)+11000 if %(sealevel)s/x < 18.507221 " \
#                      "else 0.0" % params)
        self._str = ("(%(h_b)s+(x*((1.0/math.pow(x/%(sealevel)s, -1.865845))-1.0))/%(L_b)s) if %(sealevel)s/x < 4.477048 " \
                     "else (((%(T_2a)s*(math.log(x/%(sealevel)s)))/-338.575976)+%(T_2b)s) if %(sealevel)s/x < 18.507221 " \
                     "else 0.0" % params).replace('(0.0+', '(').replace('+0.0)', ')')
        
        self._source = "lambda x: %s" % self._str
#         self._function = eval(self._source)
        
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
        print "Pressure2Feet(%r)" % press
        return 3.2808399*Pressure2Meters.function(self, press)


#===============================================================================
# 
#===============================================================================

def getApplicableConverters(doc):
    """ Get all unit converters applicable to any part of the given Dataset.
    """
    global CONVERTERS
    results = {}
    for p in doc.getPlots():
        for c in CONVERTERS:
            if c.isApplicable(p):
                results[c] = True
    return results.keys()