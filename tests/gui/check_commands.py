# SPDX-License-Identifier: Apache-2.0
"""GUI test stage "commands", run by full FreeCAD under Xvfb (mise-tasks/test-gui).

The Hexilator toolbar and menu entry in PartDesign; the Hex Grid command; the task panel's
preview, OK and Cancel; undo and redo; editing by double-click. Avoids every path that opens a
modal message box, which would hang the run.

Writes "ok" or the failures to $HEXILATOR_RESULT, then quits.
"""

import os
import sys
import traceback

failures = []


def check(cond, what):
    if not cond:
        failures.append(what)
    return cond


try:
    import FreeCAD as App
    import FreeCADGui as Gui
    from PySide import QtWidgets

    sys.path.insert(0, os.path.join(os.environ["HEXILATOR_ROOT"], "tests"))
    import helpers as h

    from freecad.hexilator import taskpanel
    from freecad.hexilator.commands import HEXGRID

    mw = Gui.getMainWindow()

    def report_text():
        texts = []
        for cls in (QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit):
            for w in mw.findChildren(cls):
                if "report" in (w.objectName() + w.metaObject().className()).lower():
                    texts.append(w.toPlainText())
        return "\n".join(texts)

    def toolbar():
        return mw.findChild(QtWidgets.QToolBar, "Hexilator")

    def menu_with(text):
        """The menu holding an action with this text, searched through the menu bar."""
        todo = [a.menu() for a in mw.menuBar().actions() if a.menu()]
        while todo:
            m = todo.pop()
            texts = [a.text().replace("&", "") for a in m.actions()]
            if text in texts:
                return m
            todo += [a.menu() for a in m.actions() if a.menu()]
        return None

    def grids(doc):
        return [o for o in doc.Objects if hasattr(o, "CellSize")]

    def settle():
        for _ in range(3):
            Gui.updateGui()

    before = report_text()

    # --- toolbar and menu ---
    Gui.activateWorkbench("PartDesignWorkbench")
    settle()
    tb = toolbar()
    if check(tb is not None, "no Hexilator toolbar in PartDesign"):
        check("Hex Grid" in [a.text() for a in tb.actions()],
              "the Hexilator toolbar has no Hex Grid action: %r"
              % [a.text() for a in tb.actions()])
        check(tb.isVisible(), "the Hexilator toolbar is hidden in PartDesign")
    m = menu_with("Hex Grid")
    if check(m is not None, "Hex Grid is in no menu"):
        texts = [a.text().replace("&", "") for a in m.actions()]
        check(any(t.startswith("Sprocket") for t in texts),
              "Hex Grid isn't in the Part Design menu beside Sprocket: %r" % texts)
    Gui.activateWorkbench("PartWorkbench")
    settle()
    tb = toolbar()
    check(tb is None or not tb.isVisible(), "the Hexilator toolbar shows in Part")
    Gui.activateWorkbench("PartDesignWorkbench")
    settle()

    # --- create, preview, OK ---
    doc = h.new_doc("cmd")
    body, box = h.plate(doc, 40, 40, 3.0, x=-8, y=-8)
    sk = h.sketch(body, z=3.0)
    h.add_rect(sk, *h.ALIGNED)
    doc.recompute()
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(sk)
    cmd = Gui.Command.get(HEXGRID)
    check(cmd.isActive(), "Hex Grid is inactive with a sketch selected")
    Gui.runCommand(HEXGRID)
    settle()
    gs = grids(doc)
    if not check(len(gs) == 1, "the command made %d grids" % len(gs)):
        raise SystemExit
    g = gs[0]
    panel = taskpanel.current
    check(Gui.Control.activeDialog(), "no task dialog after the command")
    if not check(panel is not None and panel.obj is g, "the panel isn't editing the new grid"):
        raise SystemExit
    check(g.Profile[0] is sk, "the grid's profile isn't the selected sketch")
    check(body.Tip is g, "the body's Tip isn't the new grid")
    check(not sk.ViewObject.Visibility, "the sketch is visible while editing")
    whole0 = g.WholeCells
    check(whole0 == h.ALIGNED_WHOLE, "WholeCells %d, expected %d" % (whole0, h.ALIGNED_WHOLE))

    panel.quantities["CellSize"].setProperty("rawValue", 4.0)
    check(abs(g.CellSize.Value - 4.0) < 1e-9, "CellSize didn't follow the field: %s" % g.CellSize)
    check(panel.timer.isActive(), "no preview scheduled after an edit")
    panel.preview_now()
    check(g.WholeCells != whole0, "the preview didn't recompute (WholeCells %d)" % g.WholeCells)
    check("partial" in panel.results.text(), "results not shown: %r" % panel.results.text())

    ok = panel.accept()
    settle()
    check(ok is True, "accept returned %r" % ok)
    check(not Gui.Control.activeDialog(), "the dialog is still open after OK")
    check(Gui.ActiveDocument.getInEdit() is None, "still in edit after OK")
    check(taskpanel.current is None, "the panel is still current after OK")
    check("Invalid" not in g.State, "grid invalid after OK: %s" % g.State)
    check(g.ViewObject.Visibility, "the grid is hidden after OK")
    check(not box.ViewObject.Visibility, "the base feature is visible after OK")
    check(doc.UndoNames[:1] == ["Create HexGrid"], "undo stack: %r" % doc.UndoNames[:3])

    doc.undo()
    settle()
    check(not grids(doc), "undo left the grid")
    doc.redo()
    settle()
    gs = grids(doc)
    if check(len(gs) == 1, "redo didn't bring the grid back"):
        g = gs[0]
        check(abs(g.CellSize.Value - 4.0) < 1e-9, "redo lost CellSize: %s" % g.CellSize)
    doc.recompute()

    # --- create, Cancel ---
    sk2 = h.sketch(body, z=3.0, name="Field2")
    h.add_rect(sk2, 24.0, -7.0, 31.5, 31.0)  # a strip clear of the first grid
    doc.recompute()
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(sk2)
    Gui.runCommand(HEXGRID)
    settle()
    panel = taskpanel.current
    if check(panel is not None and panel.obj is not g, "no panel for the second grid"):
        name = panel.obj.Name
        check(panel.reject() is True, "reject didn't return True")
        settle()
        check(doc.getObject(name) is None, "Cancel kept the new grid")
        check(not Gui.Control.activeDialog(), "the dialog is still open after Cancel")
        check(body.Tip is g, "the Tip moved after Cancel: %s" % body.Tip.Name)
        check(g.ViewObject.Visibility, "the previous grid isn't shown after Cancel")
        check(len(grids(doc)) == 1, "grids after Cancel: %d" % len(grids(doc)))

    # --- double-click edit: Cancel restores, OK keeps ---
    g.ViewObject.doubleClicked()
    settle()
    panel = taskpanel.current
    if check(panel is not None and panel.obj is g, "double-click didn't open the panel"):
        panel.quantities["Web"].setProperty("rawValue", 2.0)
        panel.preview_now()
        check(abs(g.Web.Value - 2.0) < 1e-9, "Web didn't follow the field")
        panel.reject()
        settle()
        check(abs(g.Web.Value - 1.2) < 1e-9, "Cancel didn't restore Web: %s" % g.Web)
        check(Gui.ActiveDocument.getInEdit() is None, "still in edit after Cancel")
    g.ViewObject.doubleClicked()
    settle()
    panel = taskpanel.current
    if check(panel is not None, "the second double-click didn't open the panel"):
        panel.quantities["Web"].setProperty("rawValue", 1.5)
        panel.type.setCurrentIndex(panel.type.findData("ThroughAll"))
        check(g.Type == "ThroughAll", "Type didn't follow the combo box")
        check(not panel.quantities["Depth"].isEnabled(), "Depth enabled for Through all")
        check(panel.accept() is True, "accept after a double-click edit failed")
        settle()
        check(abs(g.Web.Value - 1.5) < 1e-9, "OK didn't keep Web: %s" % g.Web)
        check(doc.UndoNames[:1] == ["Edit HexGrid"], "undo stack: %r" % doc.UndoNames[:3])
        check("Invalid" not in g.State, "grid invalid after the edit: %s" % g.State)

    text = report_text()[len(before):]
    bad = [ln for ln in text.splitlines()
           if any(k in ln for k in ("Traceback", "Exception", "Error", "<class"))]
    check(not bad, "report view errors:\n  " + "\n  ".join(bad[:10]))
except SystemExit:
    pass
except Exception:
    failures.append(traceback.format_exc())

with open(os.environ["HEXILATOR_RESULT"], "w") as f:
    f.write("ok\n" if not failures else "fail (commands)\n" + "\n".join(failures) + "\n")
os._exit(0)
