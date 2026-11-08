# SPDX-License-Identifier: Apache-2.0
"""GUI test stage "commands", run by full FreeCAD under Xvfb (mise-tasks/test-gui).

The Hexilator toolbar and menu entries in PartDesign; the Hex Grid and Hex Grid Pad commands;
the task panel's preview, OK and Cancel; undo and redo; editing by double-click. Avoids every path that opens a
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
    from freecad.hexilator.commands import HEXGRID, HEXGRIDPAD

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

    def command_menus(name):
        """The menus showing the command's action, found through the action itself.

        Walking the menu bar is racy: FreeCAD rebuilds some menus on the fly, deleting the
        QMenu objects found a moment earlier.
        """
        menus = []
        for act in Gui.Command.get(name).getAction():
            for o in act.associatedObjects():
                if isinstance(o, QtWidgets.QMenu):
                    try:
                        menus.append((o, [a.text().replace("&", "") for a in o.actions()]))
                    except RuntimeError:  # Internal C++ object already deleted
                        pass
        return menus

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
        for text in ("Hex Grid", "Hex Grid Pad"):
            check(text in [a.text() for a in tb.actions()],
                  "the Hexilator toolbar has no %s action: %r"
                  % (text, [a.text() for a in tb.actions()]))
        check(tb.isVisible(), "the Hexilator toolbar is hidden in PartDesign")
    for _ in range(10):
        menus = command_menus(HEXGRID)
        if menus:
            break
        settle()
    if check(menus, "Hex Grid is in no menu"):
        check(any(any(t.startswith("Sprocket") for t in texts) for _, texts in menus),
              "Hex Grid isn't in the Part Design menu beside Sprocket: %r"
              % [texts for _, texts in menus])
    for _ in range(10):
        menus = command_menus(HEXGRIDPAD)
        if menus:
            break
        settle()
    if check(menus, "Hex Grid Pad is in no menu"):
        check(any(any(t.startswith("Hex Grid Pad") for t in texts)
                  and any(t.startswith("Sprocket") for t in texts) for _, texts in menus),
              "Hex Grid Pad isn't in the Part Design menu: %r" % [texts for _, texts in menus])
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

    # --- cell shape fields ---
    g.ViewObject.doubleClicked()
    settle()
    panel = taskpanel.current
    if check(panel is not None, "the third double-click didn't open the panel"):
        check(not panel.sides.isEnabled() and not panel.lattice.isEnabled(),
              "Sides or Lattice enabled for hexagons")
        panel.shape.setCurrentIndex(panel.shape.findData("Polygon"))
        check(g.CellShape == "Polygon", "CellShape didn't follow the combo box")
        check(panel.sides.isEnabled() and panel.lattice.isEnabled(),
              "Sides or Lattice disabled for polygons")
        panel.lattice.setCurrentIndex(panel.lattice.findData("Square"))
        panel.sides.setValue(6)
        check((g.Lattice, g.Sides) == ("Square", 6), "Lattice/Sides: %s %s" % (g.Lattice, g.Sides))
        panel.preview_now()
        check(g.WholeCells > 0 and g.PartialCells == 0,
              "polygon preview: %d whole, %d partial" % (g.WholeCells, g.PartialCells))
        panel.shape.setCurrentIndex(panel.shape.findData("Circle"))
        check(not panel.sides.isEnabled(), "Sides enabled for circles")
        check(panel.accept() is True, "accept after a shape edit failed")
        settle()
        check(g.CellShape == "Circle" and "Invalid" not in g.State,
              "circle grid after OK: %s %s" % (g.CellShape, g.State))

    # --- Hex Grid Pad: create, panel fields, OK, Cancel, double-click ---
    from freecad.hexilator.viewprovider import PAD_ICON, ViewProviderHexGridPad

    pdoc = h.new_doc("padcmd")
    pbody, pbox = h.plate(pdoc, 40, 40, 3.0, x=-8, y=-8)
    psk = h.sketch(pbody, z=3.0)
    h.add_rect(psk, *h.ALIGNED)
    pdoc.recompute()
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(psk)
    check(Gui.Command.get(HEXGRIDPAD).isActive(), "Hex Grid Pad is inactive with a sketch selected")
    Gui.runCommand(HEXGRIDPAD)
    settle()
    gs = grids(pdoc)
    if not check(len(gs) == 1, "the pad command made %d grids" % len(gs)):
        raise SystemExit
    pg = gs[0]
    panel = taskpanel.current
    check(pg.TypeId == "PartDesign::FeatureAdditivePython", "pad TypeId %s" % pg.TypeId)
    check(type(pg.ViewObject.Proxy) is ViewProviderHexGridPad, "no pad view provider")
    check(pg.ViewObject.Proxy.getIcon() == PAD_ICON, "pad icon: %s" % pg.ViewObject.Proxy.getIcon())
    check(Gui.Control.activeDialog(), "no task dialog after the pad command")
    if not check(panel is not None and panel.obj is pg, "the panel isn't editing the new pad"):
        raise SystemExit
    check(panel.pad and panel.mode is not None and panel.type is None,
          "the pad panel has no Mode field, or has Type")
    check({"Height", "Border"} <= set(panel.quantities) and "Depth" not in panel.quantities,
          "pad panel quantities: %r" % sorted(panel.quantities))
    check(panel.reversed is not None, "the pad panel has no Reversed box")
    check(pg.Profile[0] is psk and pbody.Tip is pg, "the pad's profile or the Tip is wrong")
    check(pg.Mode == "Walls" and panel.mode.currentData() == "Walls", "the pad isn't in Walls mode")
    check(panel.quantities["Border"].isEnabled(), "Border is disabled in Walls mode")
    check(pg.WholeCells == h.ALIGNED_WHOLE, "pad WholeCells %d" % pg.WholeCells)

    panel.quantities["Height"].setProperty("rawValue", 1.5)
    check(abs(pg.Height.Value - 1.5) < 1e-9, "Height didn't follow the field: %s" % pg.Height)
    panel.quantities["Border"].setProperty("rawValue", 0.5)
    check(abs(pg.Border.Value - 0.5) < 1e-9, "Border didn't follow the field: %s" % pg.Border)
    panel.mode.setCurrentIndex(panel.mode.findData("Cells"))
    check(pg.Mode == "Cells", "Mode didn't follow the combo box")
    check(not panel.quantities["Border"].isEnabled(), "Border is enabled in Cells mode")
    panel.reversed.setChecked(True)
    check(pg.Reversed is True, "Reversed didn't follow the box")
    panel.reversed.setChecked(False)
    check(panel.timer.isActive(), "no preview scheduled after a pad edit")
    panel.preview_now()
    check("Invalid" not in pg.State, "pad invalid after the preview: %s" % pg.State)
    check("partial" in panel.results.text(), "pad results not shown: %r" % panel.results.text())
    check(abs(pg.Shape.BoundBox.ZMax - 4.5) < 1e-6, "pad ZMax %g" % pg.Shape.BoundBox.ZMax)
    panel.mode.setCurrentIndex(panel.mode.findData("Walls"))
    check(panel.accept() is True, "pad accept failed")
    settle()
    check(not Gui.Control.activeDialog(), "the dialog is still open after pad OK")
    check(taskpanel.current is None, "the panel is still current after pad OK")
    check("Invalid" not in pg.State, "pad invalid after OK: %s" % pg.State)
    check(pg.ViewObject.Visibility and not pbox.ViewObject.Visibility,
          "visibility after pad OK")
    check(pdoc.UndoNames[:1] == ["Create HexGridPad"], "undo stack: %r" % pdoc.UndoNames[:3])
    pdoc.undo()
    settle()
    check(not grids(pdoc), "undo left the pad")
    pdoc.redo()
    settle()
    gs = grids(pdoc)
    if check(len(gs) == 1, "redo didn't bring the pad back"):
        pg = gs[0]
        check(abs(pg.Height.Value - 1.5) < 1e-9, "redo lost Height: %s" % pg.Height)
    pdoc.recompute()

    psk2 = h.sketch(pbody, z=3.0, name="Field2")
    h.add_rect(psk2, 24.0, -7.0, 31.5, 31.0)
    pdoc.recompute()
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(psk2)
    Gui.runCommand(HEXGRIDPAD)
    settle()
    panel = taskpanel.current
    if check(panel is not None and panel.obj is not pg, "no panel for the second pad"):
        name = panel.obj.Name
        check(panel.reject() is True, "pad reject didn't return True")
        settle()
        check(pdoc.getObject(name) is None, "Cancel kept the new pad")
        check(pbody.Tip is pg and pg.ViewObject.Visibility, "the Tip or its display after Cancel")
        check(len(grids(pdoc)) == 1, "pads after Cancel: %d" % len(grids(pdoc)))

    pg.ViewObject.doubleClicked()
    settle()
    panel = taskpanel.current
    if check(panel is not None and panel.obj is pg and panel.pad,
             "double-click didn't open the pad panel"):
        panel.quantities["Height"].setProperty("rawValue", 3.0)
        panel.preview_now()
        check(abs(pg.Height.Value - 3.0) < 1e-9, "Height didn't follow the field")
        panel.reject()
        settle()
        check(abs(pg.Height.Value - 1.5) < 1e-9, "Cancel didn't restore Height: %s" % pg.Height)
    pg.ViewObject.doubleClicked()
    settle()
    panel = taskpanel.current
    if check(panel is not None, "the second pad double-click didn't open the panel"):
        panel.quantities["Height"].setProperty("rawValue", 2.5)
        check(panel.accept() is True, "accept after a pad double-click edit failed")
        settle()
        check(abs(pg.Height.Value - 2.5) < 1e-9, "OK didn't keep Height: %s" % pg.Height)
        check(pdoc.UndoNames[:1] == ["Edit HexGridPad"], "undo stack: %r" % pdoc.UndoNames[:3])
        check("Invalid" not in pg.State, "pad invalid after the edit: %s" % pg.State)

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
