# SPDX-License-Identifier: Apache-2.0
"""View provider for HexGrid. The class name and module path are stored in documents."""

import os

ICON = os.path.join(os.path.dirname(__file__), "resources", "HexGrid.svg")


class ViewProviderHexGrid:
    def __init__(self, vobj):
        vobj.Proxy = self
        self.Object = vobj.Object

    def attach(self, vobj):
        self.Object = vobj.Object

    def getIcon(self):
        return ICON

    def claimChildren(self):
        link = self.Object.Profile
        if not link:
            return []
        return [link[0] if isinstance(link, tuple) else link]

    def dumps(self):
        return None

    def loads(self, state):
        return None


def ensure_view_provider(obj):
    """Attach the view provider proxy if the object has a view object without one.

    A file saved headless has no GUI data, so its HexGrids get their proxy here on restore.
    """
    vobj = getattr(obj, "ViewObject", None)
    if vobj is not None and not isinstance(getattr(vobj, "Proxy", None), ViewProviderHexGrid):
        ViewProviderHexGrid(vobj)
