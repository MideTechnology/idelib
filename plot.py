import wx
wx = wx

from wx.lib.plot import PlotCanvas, PlotGraphics, PolySpline, PolyLine, PolyMarker

colors = [
    "BLACK",
    "BLUE",
    "BLUE VIOLET",
    "BROWN",
    "CYAN",
    "DARK GREY",
    "DARK GREEN",
    "GOLD",
    "GREY",
    "GREEN",
    "MAGENTA",
    "NAVY",
    "PINK",
    "RED",
    "SKY BLUE",
    "VIOLET",
    "YELLOW",
    ]

import random
random.seed(1234)

numPoints = 500
pointRange = (000, 500)

lineMaker = PolyLine
# lineMaker = PolySpline
# lineMaker = PolyMarker

dataset = []
for c in colors:
    testPoints = [(x,random.randint(*pointRange)) for x in xrange(0,numPoints,random.randint(10,50))]
    dataset.append(lineMaker(testPoints, colour=c))
    dataset.append(PolyMarker(testPoints[::random.randint(1,5)], colour=c))
    
lines = []
# for i in xrange(0, len(testPoints)-1):
#     lines.append(testPoints[i] + testPoints[i+1])
    
# testplot = PlotGraphics([PolySpline(lines)], "Test")
testplot = PlotGraphics(dataset, "Test")

class DrawPanel(wx.Panel):
    def __init__(self, parent):
        wx.Panel.__init__(self, parent, -1)
        self.SetBackgroundColour(wx.WHITE)
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.font = wx.Font(9, wx.SWISS, wx.NORMAL, wx.BOLD)
        self.dumped = False
        
    def scale(self, p, size):
        """
        """
        return (p[0]/500.0)*size.x, (p[1]/800.0)*size.y 

    def OnPaint(self, evt):
        self.InvalidateBestSize()
#         dc = wx.BufferedPaintDC(self)
        dc = wx.PaintDC(self)
#         dc = wx.GCDC(wx.PaintDC(self))
        if not self.dumped:
#             print dir(dc.GetSize())
            self.dumped = True

        dc.Clear()
        dc.SetFont(self.font)
        lines = []
        
        dc.BeginDrawing()
        size = dc.GetSize()
        dc.SetPen(wx.Pen("BLACK", 2))
#         print size
#         for i in xrange(0, len(testPoints)-1):
#             p =self.scale(testPoints[i], size) + self.scale(testPoints[i+1], size)
#             lines.append(self.scale(testPoints[i], size) + self.scale(testPoints[i+1], size))
# #             dc.DrawText("%d\n%r" % (i, testPoints[i]), p[0],p[1])
# #             dc.DrawText("%d\n%r" % (i, testPoints[i]), p[0],p[1]+12)
#         dc.SetPen(wx.Pen("YELLOW", 2))
#         dc.DrawLineList(lines)
#         dc.SetPen(wx.Pen("BLACK", 2))
#         for i in xrange(0, len(testPoints)-1):
#             p =self.scale(testPoints[i], size) + self.scale(testPoints[i+1], size)
#             lines.append(self.scale(testPoints[i], size) + self.scale(testPoints[i+1], size))
#             dc.DrawText("%d\n%r" % (i, testPoints[i]), p[0],p[1])
#             dc.DrawText("%.2f, %.2f" % (p[0],p[1]), p[0],p[1]+12)
        
        
        gc = wx.GraphicsContext.Create(dc)
        p = gc.CreatePath()
#         p.AddPath()
        p.MoveToPoint(498.34889,584.12651);
        p.AddLineToPoint(498.34889,576.4851600000001);
        p.AddLineToPoint(418.64855,590.92061);
        p.CloseSubpath();
        
#         p.AddPath()
        p.MoveToPoint(279.79962,636.53538);
#         p.bezierCurveTo(279.79962,648.9278,268.19691,648.9278,268.19691,648.9278);
        p.AddLineToPoint(204.48907,648.9278);
        p.AddLineToPoint(204.48907,670.6721100000001);
        p.AddLineToPoint(268.19691,670.6721100000001);
#         p.bezierCurveTo(268.19691,670.6721100000001,309.4059,669.2141700000001,309.2812,636.53538);
#         p.bezierCurveTo(309.16932,603.85658,268.19691,601.8615100000001,268.19691,601.8615100000001);
        p.AddLineToPoint(204.48907,601.8615100000001);
        p.AddLineToPoint(204.48907,624.28043);
        p.AddLineToPoint(268.19691,624.28043);
#         p.bezierCurveTo(268.19691,624.28043,279.79962,624.4179,279.79962,636.53538);
        p.CloseSubpath();        
        gc.DrawPath(p)
        gc.StrokePath(p)
        gc.FillPath(p)
        dc.EndDrawing()
        # Do drawing here


class TestPlotter(wx.App):
    def __init__(self, *args, **kwargs):
        super(TestPlotter,self).__init__(*args, **kwargs)
        
    def OnInit(self):
        self.frame =wx.Frame(None, -1, 'simple.py')#, style=wx.DEFAULT_FRAME_STYLE|wx.FULL_REPAINT_ON_RESIZE)
        self.plot = PlotCanvas(self.frame)
        self.plot.SetEnableAntiAliasing(True)
        self.plot.SetEnableHiRes(True)
        self.frame.Show(True)
        self.SetTopWindow(self.frame)
        self.plot.SetShowScrollbars(True)
        self.plot.Draw(testplot)
        return True


class ScratchPlotter(wx.App):
    def OnInit(self):
        frame = wx.Frame(None, -1, 'simple.py', style=wx.DEFAULT_FRAME_STYLE|wx.FULL_REPAINT_ON_RESIZE)
        p = DrawPanel(frame)
#         p = PlotCanvas(frame)
        frame.Show()
        p.Show()
        return True

# app = wx.App()
# app = TestPlotter()
app = ScratchPlotter()
# frame = wx.Frame(None, -1, 'simple.py', style=wx.DEFAULT_FRAME_STYLE|wx.FULL_REPAINT_ON_RESIZE)
#p = DrawPanel(frame)
# p = PlotCanvas(frame)
# frame.Show()
#p.Show()

app.MainLoop()
# p.Draw(testplot)
