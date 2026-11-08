# SPDX-License-Identifier: Apache-2.0
"""GUI commands. Command names are global in FreeCAD, so they carry the Hexilator_ prefix."""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore

translate = App.Qt.translate

HEXGRID = "Hexilator_HexGrid"
HEXGRIDPAD = "Hexilator_HexGridPad"
TOOLBAR_COMMANDS = (HEXGRID, HEXGRIDPAD)
MENU_COMMANDS = (HEXGRID, HEXGRIDPAD)

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

    name = HEXGRID
    maker = "make_hex_grid"
    transaction = QtCore.QT_TRANSLATE_NOOP("Hexilator", "Create HexGrid")

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
        doc.openTransaction(translate("Hexilator", self.transaction))
        Gui.addModule("freecad.hexilator")
        Gui.doCommand("freecad.hexilator.%s(App.getDocument(%r).getObject(%r), "
                      "App.getDocument(%r).getObject(%r))"
                      % (self.maker, doc.Name, body.Name, doc.Name, profile.Name))
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
            # not every view provider has every property (e.g. a bare Body's)
            if hasattr(src.ViewObject, prop) and hasattr(grid.ViewObject, prop):
                setattr(grid.ViewObject, prop, getattr(src.ViewObject, prop))
        Gui.Selection.clearSelection()
        Gui.ActiveDocument.setEdit(grid, 0)


class HexGridPadCommand(HexGridCommand):
    """Create a HexGridPad (the additive grid) from the selected sketch, or from a sketch in
    the active Body."""

    name = HEXGRIDPAD
    maker = "make_hex_grid_pad"
    transaction = QtCore.QT_TRANSLATE_NOOP("Hexilator", "Create HexGridPad")

    def GetResources(self):
        return {
            "Pixmap": "Hexilator_HexGridPad",
            "MenuText": QtCore.QT_TRANSLATE_NOOP(HEXGRIDPAD, "Hex Grid Pad"),
            "ToolTip": QtCore.QT_TRANSLATE_NOOP(
                HEXGRIDPAD,
                "Pads a hex grid onto the body: the walls between the cells, or the cells "
                "themselves. The selected sketch's outer loops are the fields; its inner "
                "loops are keep-outs."),
        }


def register():
    Gui.addCommand(HEXGRID, HexGridCommand())
    Gui.addCommand(HEXGRIDPAD, HexGridPadCommand())
