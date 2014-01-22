'''
Generate some fake graph data for previewing the graphing window.

FOR TESTING PURPOSES ONLY.

Created on Nov 6, 2013

@author: dstokes
'''

import random

def makeFakeData():
    class FakeSource(list):
        def __init__(self, *args):
            self.units=('','')
            self.name = "Fake Data"
            self.extend(args)
        
        def iterResampledRange(self, *args, **kwargs):
            return iter(self)
    
    fakedata = []
    for n,u in (("Accelerometer X",('G','G')), 
              ("Accelerometer Y",('G','G')), 
              ("Accelerometer Z",('G','G')), 
              ("Pressure",('Pascals','Pa')),
              ("Temperature",(u'\xb0C',u'\xb0C'))):
        d = FakeSource()
        d.name = n
        d.units = u
        for i in xrange(1043273, 1043273 + 200000, 200):
            d.append((i,random.randint(128,65407)))
        fakedata.append(d)
    return fakedata



