"""
Developer utility to dump out menus and their help text. Meant to be imported
in the Scripting Console.
"""

import csv

def dumpMenuItem(path, mi, results=None):
    results = [] if results is None else results
    p = mi.GetItemLabelText()
    if not p:
        # Probably a separator
        return results
    if path:
        p = "%s -> %s" % (path, p)
    sm = mi.GetSubMenu()
    if sm:
        results.append(['', p, '(submenu)'])
        for smi in sm.GetMenuItems():
            dumpMenuItem(p, smi, results)
    else:
        results.append(['', p, mi.GetHelp()])

    return results

def getMenus(menubar, filename="menus.csv"):
    results = []
    for i in range(menubar.GetMenuCount()):
        menu = menubar.GetMenu(i)
        title = menu.GetTitle().replace('&','')
        results.append([title,'', ''])
        for mi in menu.GetMenuItems():
            dumpMenuItem('', mi, results)

    with open(filename, 'wb') as f:
        w = csv.writer(f)
        w.writerows(results)
