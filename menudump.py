import csv

def dumpMenuItem(path, mi, results=None):
    results = [] if results is None else results
    p = mi.GetItemLabelText()
    if not p:
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

def getMenus(viewer, filename="menus.csv"):
    results = []
    mb = viewer.GetMenuBar()
    for i in range(mb.GetMenuCount()):
        menu = mb.GetMenu(i)
        title = menu.GetTitle().replace('&','')
        results.append([title,'', ''])
        for mi in menu.GetMenuItems():
            dumpMenuItem('', mi, results)

    with open(filename, 'wb') as f:
        w = csv.writer(f)
        w.writerows(results)
