# SPDX-License-Identifier: Apache-2.0
"""View providers for HexGrid and HexGridPad. Their class names and module path are stored in
documents: never rename them."""

import os

ICONS = os.path.join(os.path.dirname(__file__), "resources", "icons")
ICON = os.path.join(ICONS, "Hexilator_HexGrid.svg")
PAD_ICON = os.path.join(ICONS, "Hexilator_HexGridPad.svg")

EDIT_DEFAULT = 0
"""Gui::ViewProvider::Default, the mode a double-click and setEdit(obj, 0) open."""


def is_pad(obj):
    """True for a HexGridPad (additive), false for a HexGrid (subtractive)."""
    return obj.TypeId == "PartDesign::FeatureAdditivePython"


class ViewProviderHexGrid:
    icon = ICON

    def __init__(self, vobj):
        vobj.Proxy = self
        self.Object = vobj.Object

    def attach(self, vobj):
        self.Object = vobj.Object

    def getIcon(self):
        return self.icon

    def claimChildren(self):
        link = self.Object.Profile
        if not link:
            return []
        return [link[0] if isinstance(link, tuple) else link]

    # A PartDesign Python feature must handle the default edit mode itself: PartDesign's C++
    # fallback calls getEditDialog(), which isn't implemented for Python features. Other
    # modes (Transform, Color, ...) return None so PartDesign handles them. doubleClicked is
    # left to PartDesign, which opens an "Edit <Label>" transaction and calls setEdit.
    def setEdit(self, vobj, mode):
        if mode != EDIT_DEFAULT:
            return None
        import FreeCADGui as Gui

        from .taskpanel import HexGridTaskPanel

        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        Gui.Control.showDialog(HexGridTaskPanel(vobj.Object))
        return True

    def unsetEdit(self, vobj, mode):
        if mode != EDIT_DEFAULT:
            return None
        import FreeCADGui as Gui

        Gui.Control.closeDialog()
        return True

    def dumps(self):
        return None

    def loads(self, state):
        return None


class ViewProviderHexGridPad(ViewProviderHexGrid):
    icon = PAD_ICON


def ensure_view_provider(obj):
    """Attach the view provider proxy if the object has a view object without one.

    A file saved headless has no GUI data, so its HexGrids and HexGridPads get their proxy
    here on restore.
    """
    vobj = getattr(obj, "ViewObject", None)
    if vobj is not None and not isinstance(getattr(vobj, "Proxy", None), ViewProviderHexGrid):
        (ViewProviderHexGridPad if is_pad(obj) else ViewProviderHexGrid)(vobj)
