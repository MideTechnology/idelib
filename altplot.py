'''
Hack to generate a virtual data channel with the altitude, computed from 
the temperature and air pressure (channel 1).

EXPERIMENTAL.


Created on Feb 13, 2015

@author: dstokes
'''

import math
from mide_ebml.parsers import MPL3115PressureTempParser


class MPL3115AltitudeParser(MPL3115PressureTempParser):
    types = (float,)
    ranges = ((-2**20,2**20),)
    DEFAULT_SEALEVEL = 101325.0


    def __init__(self, sealevel=DEFAULT_SEALEVEL):
        self.sealevel = sealevel
        

    def unpack_from(self, data, offset=0):
        """ Special-case parsing of a temperature data block.
        """
        sealevel = self.sealevel
#         M = 0.0289644 # [kg/mol] molar mass of Earth's air
#         g = 9.80665   # [m/s^2] gravitational acceleration constant
#         R = 8.31432   # [(N*m)/(mol*k)] universal gas constant
        press, t = super(MPL3115AltitudeParser, self).unpack_from(data, offset)
        
        if ((sealevel/press) < 4.47704808656731):
            L_b = -0.0065 # [K/m] temperature lapse rate
            h_b = 0.0  # [m] height above sea level (differing altitudes have differing time lapse rates
#             foo = math.pow((press/sealevel), (R*L_b)/(g*M))
#             return (h_b+((t*((1.0/foo)-1.0))/L_b),)
            foo = math.pow((press/sealevel), -1.8658449683059204)
            return (h_b+((t*((1.0/foo)-1.0))/L_b),)
        
        elif ((sealevel / press) < (18.507221149648668)):
            T_2 = t - 71.5
#             h_b = 11000
#             h_2 = (R*T_2*(math.log(press/sealevel)))/((-g)*M)
#             p_c = 101325
#             P_1 = 22632.1
#             h_1 = ((R*T_2*(math.log(p_c/P_1)))/((-g)*M))+h_b
#             h_2 = (R*T_2*(math.log(press/sealevel)))/(-g*M)
#             h_1 = ((R*T_2*(math.log(101325/22632.1)))/(-g*M))+11000
            h_2 = (8.31432*T_2*(math.log(press/sealevel)))/-338.5759760257419
#             h_1 = ((T_2*12.462865699354536)/-338.5759760257419)+11000
            h_1 = (T_2*-0.03680965745309403)+11000
            return (h_1+h_2,)
        
        return (0,) # Is this okay?


def addAltChannel(doc, chId=128, subChId=0, sessionId=None, sourceId=1):
    """ Create a new sensor channel using the altitude parser, which uses the
        existing Channel 1 data.
        
        For some reason, the copy isn't getting the _data.
    """
    if sessionId is None:
        sessionId = doc.lastSession.sessionId
    if chId in doc.channels:
        return doc.channels[chId][subChId].getSession(sessionId)
    ch = doc.addChannel(name="Computed Altitude", channelId=chId, 
                                   parser=MPL3115AltitudeParser(),
                                   sensor=doc.sensors[0],
                                   cache=True, singleSample=True)
    ch.addSubChannel(subChId, name="Altitude", units=("Altitude","m"),
                     displayRange=(0,20000))
    
    sourceEl = doc.channels[sourceId].getSession(sessionId)
    el = sourceEl.copy(ch)
    print el, el._parentList
    el._data = sourceEl._data
    ch.sessions[sessionId] = el
#     return el
    return doc.channels[chId][subChId].getSession(sessionId)


def updateAltChannel(doc, chId=128, subChId=0, sessionId=None, sourceId=1):
    """ Update the 
    """
    sourceEl = doc.channels[sourceId].getSession(sessionId)
    doc.channels[chId].getSession(sessionId)._data = sourceEl._data
    doc.channels[chId][subChId].getSession(sessionId)._data = sourceEl._data


def addAltPlot(view, chId=128, subChId=0):
    """ Adds a temp/pressure-as-altitude plot to the viewer.
    """
    if chId not in view.dataset.channels:
        el = addAltChannel(view.dataset, chId, subChId)
        p = view.plotarea.addPlot(el, title=el.parent.name)
#         for d in view.dataset.getPlots(debug=view.showDebugChannels):
#             el = d.getSession(view.session.sessionId)
#             p = view.plotarea.addPlot(el, title=d.name)
         
        view.enableChildren(True)
        # enabling plot-specific menu items happens on page select; do manually
        view.plotarea.getActivePage().enableMenus()
        return p
    