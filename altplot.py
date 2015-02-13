'''
Hack to generate a virtual data channel with the altitude, computed from 
the temperature and air pressure (ch 1).

EXPERIMENTAL.


Created on Feb 13, 2015

@author: dstokes
'''

import math
from mide_ebml.parsers import MPL3115PressureTempParser


class MPL3115AltitudeParser(MPL3115PressureTempParser):
    DEFAULT_SEALEVEL = 101325.0

    def unpack_from(self, data, offset=0):
        """ Special-case parsing of a temperature data block.
        """
        sealevel = self.DEFAULT_SEALEVEL
        M = 0.0289644 # [kg/mol] molar mass of Earth's air
        g = 9.80665   # [m/s^2] gravitational acceleration constant
        R = 8.31432   # [(N*m)/(mol*k)] universal gas constant
        print type(self)
        press, t = super(MPL3115AltitudeParser, self).unpack_from(data, offset)
        
        if ((sealevel/press) < 4.47704808656731):
            L_b = -0.0065 # [K/m] temperature lapse rate
            h_b = 0.0  # [m] height above sea level (differing altitudes have differing time lapse rates
            foo = math.pow((press/sealevel), (R*L_b)/(g*M))
            return (h_b+((t*((1.0/foo)-1.0))/L_b),)
        
        elif ((sealevel / press) < (18.507221149648668)):
#             h_b = 11000
#             T_2 = t - 71.5
#             h_2 = (R*T_2*(math.log(press/sealevel)))/((-g)*M)
#             p_c = 101325
#             P_1 = 22632.1
#             h_1 = ((R*T_2*(math.log(p_c/P_1)))/((-g)*M))+h_b
            T_2 = t - 71.5
            h_2 = (R*T_2*(math.log(press/sealevel)))/(-g*M)
            h_1 = ((R*T_2*(math.log(101325/22632.1)))/(-g*M))+11000
            return (h_1+h_2,)
        
        return (0,) # Is this okay?


def addAltPlot(doc, sessionId=None):
    """ Create a new sensor channel using the altitude parser, which uses the
        existing Channel 1 data.
        
        For some reason, the copy isn't getting the _data.
    """
    ch = doc.sensors[0].addChannel(name="Computed Altitude", channelId=128, parser=MPL3115AltitudeParser(),
                                   cache=True, singleSample=True)
    ch.addSubChannel(0, name="Altitude", units=("Altitude","m"),
                     displayRange=(0,20000))
    
    sourceEl = doc.channels[1].getSession(sessionId)
    el = sourceEl.copy(ch)
    el._data = sourceEl._data
    ch.sessions[sessionId] = el
    return el
#         for d in self.dataset.getPlots(debug=self.showDebugChannels):
#             el = d.getSession(self.session.sessionId)
#             p = self.plotarea.addPlot(el, title=d.name)
#             if meanSpan is not None:
#                 p.removeMean(True, meanSpan)
#         
#         self.enableChildren(True)
#         # enabling plot-specific menu items happens on page select; do manually
#         self.plotarea.getActivePage().enableMenus()
