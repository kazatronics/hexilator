# SPDX-License-Identifier: Apache-2.0
"""GUI test, run by full FreeCAD under Xvfb (mise-tasks/test-gui) in two stages.

Stage "headless": open the file freecadcmd saved (no GUI data). The HexGrid must get its view
provider, icon and tree children, recompute, and log no errors. FreeCAD itself opens files
without GUI data with every object hidden, so visibility isn't checked here. Then build a
HexGrid in the GUI and save it, as a GUI save (e.g. Trellis's Xvfb saves) would.

Stage "reopen": open that GUI-saved file. The body and its Tip must be visible and the sketch
and earlier feature hidden, with no errors.

Writes "ok" or the failures to $HEXILATOR_RESULT, then quits.
"""

import os
import sys
import traceback

failures = []
stage = os.environ["HEXILATOR_STAGE"]
try:
    import FreeCAD as App
    import FreeCADGui as Gui
    from PySide import QtGui

    sys.path.insert(0, os.path.join(os.environ["HEXILATOR_ROOT"], "tests"))
    import helpers as h

    import freecad.hexilator as hx
    from freecad.hexilator.viewprovider import ICON, ViewProviderHexGrid

    def report_text():
        mw = Gui.getMainWindow()
        texts = []
        for cls in (QtGui.QTextEdit, QtGui.QPlainTextEdit):
            for w in mw.findChildren(cls):
                if "report" in (w.objectName() + w.metaObject().className()).lower():
                    texts.append(w.toPlainText())
        return "\n".join(texts)

    def check_feature(doc, name, field):
        g = doc.getObject(name)
        if not isinstance(g.ViewObject.Proxy, ViewProviderHexGrid):
            failures.append("%s has no ViewProviderHexGrid proxy: %r" % (name, g.ViewObject.Proxy))
        elif g.ViewObject.Proxy.getIcon() != ICON or not os.path.isfile(ICON):
            failures.append("%s: icon missing" % name)
        elif doc.getObject(field) not in g.ViewObject.Proxy.claimChildren():
            failures.append("%s: the profile sketch is not claimed in the tree" % name)
        return g

    def check_visibility(doc, body, grid, hidden):
        if doc.getObject(body).Tip is not doc.getObject(grid):
            failures.append("%s.Tip is %s" % (body, doc.getObject(body).Tip.Name))
        for name in (body, grid):
            if not doc.getObject(name).ViewObject.Visibility:
                failures.append("%s is hidden" % name)
        for name in hidden:
            if doc.getObject(name).ViewObject.Visibility:
                failures.append("%s is visible" % name)

    before = report_text()
    if stage == "headless":
        doc = App.openDocument(os.environ["HEXILATOR_DOC"])
        Gui.updateGui()
        g = check_feature(doc, "HexGrid", "Field")
        g.CellSize = 4.5
        doc.recompute()
        Gui.updateGui()
        if "Invalid" in g.State:
            failures.append("recompute in the GUI failed: %s" % g.State)

        # build one in the GUI, then save with GUI data
        doc2 = h.new_doc("guimade")
        body, box = h.plate(doc2, 40, 40, 3.0, x=-8, y=-8)
        sk = h.sketch(body, z=3.0)
        h.add_rect(sk, *h.ALIGNED)
        g2 = hx.make_hex_grid(body, sk)
        doc2.recompute()
        Gui.updateGui()
        check_feature(doc2, "HexGrid", "Field")
        check_visibility(doc2, "Body", "HexGrid", ("BodyPlate", "Field"))
        doc2.saveAs(os.environ["HEXILATOR_GUIDOC"])
    else:
        doc = App.openDocument(os.environ["HEXILATOR_GUIDOC"])
        Gui.updateGui()
        check_feature(doc, "HexGrid", "Field")
        check_visibility(doc, "Body", "HexGrid", ("BodyPlate", "Field"))
        shot = os.environ.get("HEXILATOR_SHOT")
        if shot:
            v = Gui.ActiveDocument.ActiveView
            v.viewIsometric()
            v.fitAll()
            Gui.updateGui()
            v.saveImage(shot, 1200, 900, "White")

    text = report_text()[len(before):]
    bad = [ln for ln in text.splitlines()
           if any(k in ln for k in ("Traceback", "Exception", "Error", "<class"))]
    if bad:
        failures.append("report view errors:\n  " + "\n  ".join(bad[:10]))
except Exception:
    failures.append(traceback.format_exc())

with open(os.environ["HEXILATOR_RESULT"], "w") as f:
    f.write("ok\n" if not failures else "fail (%s)\n" % stage + "\n".join(failures) + "\n")
os._exit(0)
