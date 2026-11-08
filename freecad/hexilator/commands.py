# SPDX-License-Identifier: Apache-2.0
"""GUI commands. Command names are global in FreeCAD, so they carry the Hexilator_ prefix."""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore

translate = App.Qt.translate

HEXGRID = "Hexilator_HexGrid"
TOOLBAR_COMMANDS = (HEXGRID,)
MENU_COMMANDS = (HEXGRID,)

# What PartDesign copies from the base feature onto a new feature's view (finishFeature).
VIEW_PROPS = ("ShapeAppearance", "LineColor", "PointColor", "Transparency", "DisplayMode")


def is_profile(obj):
    """A 2D object (a sketch, or another Part2DObject) that can be a HexGrid's field."""
    return obj is not None and obj.isDerivedFrom("Part::Part2DObject")


def body_of(obj):
    """The PartDesign Body that holds obj, or None."""
    for parent in obj.InList:
        if parent.isDerivedFrom("PartDesign::Body") and parent.hasObject(obj):
            return parent
    return None


def active_body():
    view = getattr(Gui.ActiveDocument, "ActiveView", None) if Gui.ActiveDocument else None
    if view is None or not hasattr(view, "getActiveObject"):
        return None
    return view.getActiveObject("pdbody")


def selected_profiles():
    return [o for o in Gui.Selection.getSelection() if is_profile(o)]


def body_profiles(body):
    """The 2D objects in body, in tree order."""
    return [o for o in body.Group if is_profile(o)]


def _warn(text):
    from PySide import QtWidgets

    QtWidgets.QMessageBox.warning(Gui.getMainWindow(), translate("Hexilator", "Hex grid"), text)


def _choose_profile(body):
    """The profile to use when none is selected: the body's only one, or the user's pick."""
    profiles = body_profiles(body)
    if not profiles:
        return None
    if len(profiles) == 1:
        return profiles[0]
    from PySide import QtWidgets

    labels = ["%s (%s)" % (o.Label, o.Name) for o in profiles]
    label, ok = QtWidgets.QInputDialog.getItem(
        Gui.getMainWindow(), translate("Hexilator", "Hex grid"),
        translate("Hexilator", "Field sketch:"), labels, len(labels) - 1, False)
    if not ok:
        return False
    return profiles[labels.index(label)]


class HexGridCommand:
    """Create a HexGrid from the selected sketch, or from a sketch in the active Body."""

    def GetResources(self):
        return {
            "Pixmap": "Hexilator_HexGrid",
            "MenuText": QtCore.QT_TRANSLATE_NOOP(HEXGRID, "Hex Grid"),
            "ToolTip": QtCore.QT_TRANSLATE_NOOP(
                HEXGRID,
                "Cuts a hex grid into the body. The selected sketch's outer loops are the "
                "fields; its inner loops are keep-outs."),
        }

    def IsActive(self):
        if App.ActiveDocument is None:
            return False
        sel = selected_profiles()
        if sel:
            return body_of(sel[0]) is not None
        return active_body() is not None

    def Activated(self):
        doc = App.ActiveDocument
        sel = selected_profiles()
        if sel:
            profile = sel[0]
            body = body_of(profile)
        else:
            body = active_body()
            if body is None:
                _warn(translate("Hexilator", "Select a sketch in a body, or activate a body."))
                return
            profile = _choose_profile(body)
            if profile is False:
                return
            if profile is None:
                _warn(translate("Hexilator",
                                "The active body has no sketch to use as the grid's field."))
                return
        if body is None:
            _warn(translate("Hexilator", "The sketch %s is not in a body.") % profile.Label)
            return
        before = set(o.Name for o in doc.Objects)
        doc.openTransaction(translate("Hexilator", "Create HexGrid"))
        Gui.addModule("freecad.hexilator")
        Gui.doCommand("freecad.hexilator.make_hex_grid(App.getDocument(%r).getObject(%r), "
                      "App.getDocument(%r).getObject(%r))"
                      % (doc.Name, body.Name, doc.Name, profile.Name))
        new = [o for o in doc.Objects if o.Name not in before and hasattr(o, "CellSize")]
        grid = new[0] if len(new) == 1 else None
        if grid is None:
            doc.abortTransaction()
            _warn(translate("Hexilator", "The hex grid could not be created."))
            return
        doc.recompute()
        base = grid.BaseFeature
        src = base if base is not None else body
        for prop in VIEW_PROPS:
            try:
                setattr(grid.ViewObject, prop, getattr(src.ViewObject, prop))
            except Exception:
                pass
        Gui.Selection.clearSelection()
        Gui.ActiveDocument.setEdit(grid, 0)


def register():
    Gui.addCommand(HEXGRID, HexGridCommand())
