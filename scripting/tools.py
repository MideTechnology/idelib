'''
Some convenience functions to simplify common scripting activities.
'''

import os.path

import wx


def getRecordings(default="", message=None, multi=False):
    """ Show an 'open file' dialog for the selection of IDE recordings.
    
        @keyword default: The default file and/or directory to start in.
        @keyword message: The prompt shown in the dialog. Defaults to
            "Select IDE Recording File".
        @keyword multi: If `True`, allow multiple file selection.
        @return: If the dialog is not cancelled, either a filename (if `multi`
            is `False`), or a list of filenames (if `multi` is `True`). If the
            dialog is cancelled, the function returns `None` or an empty list
            (if `multi` is `False` or `True`, respectively).
    """
    wildcard = "MIDE Data File (*.ide)|*.ide"
    if not message:
        message = "Select IDE Recording File:"
        if multi:
            message += "s"
        message += ":"
    
    if os.path.isfile(default):
        defaultDir, defaultFile = os.path.split(default)
    else:
        defaultDir, defaultFile = default, ''
    
    style = wx.FD_OPEN|wx.FD_CHANGE_DIR|wx.FD_FILE_MUST_EXIST
    if multi:
        style |= wx.FD_MULTIPLE
    
    
    dlg = wx.FileDialog(None, message=message, defaultDir=defaultDir,
                        defaultFile=defaultFile, wildcard=wildcard,
                        style=style)
    
    if dlg.ShowModal() == wx.ID_OK:
        if multi:
            result = [os.path.realpath(p) for p in dlg.GetPaths()]
        else:
            result = os.path.realpath(dlg.GetPath())
    else:
        result = [] if multi else None
    
    dlg.Destroy()
    
    return result


def collectFiles(path):
    """ Get all recording files within a directory and any subdirectories
        within it.
        
        @param path: The starting directory.
        @return: A list of IDE filenames.
    """
    ides = []
    for root, dirs, files in os.walk(path):
        ides.extend(map(lambda x: os.path.join(root, x),
                        filter(lambda x: x.upper().endswith('.IDE'), files)))
        for d in dirs:
            if d.startswith('.'):
                dirs.remove(d)
    return sorted(ides)


def getContents(default="", message=None, crawl=False):
    """ Show an 'open' dialog for selecting a directory of IDE recordings.
    
        @keyword default: The default directory to start in.
        @keyword message: The prompt shown in the dialog. Defaults to
            "Select a Directory of IDE Files".
        @keyword crawl: If `False`, only the contents of the selected
            directory will be returned. If `True`, the contents of the
            selected directory and all subdirectories will be returned.
        @return: A list of found IDE filenames, or an empty list if the dialog
            was cancelled.
    """
    if not message:
        message = "Select a Directory of IDE Files:"
    
    if os.path.isfile(default):
        default = os.path.dirname(default)
    
    dlg = wx.DirDialog(None, message, default)
    if dlg.ShowModal() != wx.ID_OK:
        dlg.Destroy()
        return []
    
    path = os.path.realpath(dlg.GetPath())
    dlg.Destroy()
    
    if not crawl:
        return [os.path.join(path, f) for f in os.listdir(path) 
                if f.upper().endswith('.IDE')]
    
    return collectFiles(path)
