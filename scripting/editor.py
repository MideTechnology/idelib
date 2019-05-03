import  wx
import  wx.stc  as  stc

from python_stc import PythonSTC, faces

# XXX: hack, get rid of bad demo fonts!
faces['times'] = faces['mono']
faces['helv'] = faces['mono']
faces['other'] = faces['mono']


class ScriptEditorCtrl(PythonSTC):
    """
    """
    
    def __init__(self, *args, **kwargs):
        """
        """
        PythonSTC.__init__(self, *args, **kwargs)


    def OnKeyPressed(self, event):
        if self.CallTipActive():
            self.CallTipCancel()
            
        event.Skip()
