# SPDX-License-Identifier: Apache-2.0
"""Screenshot a document off-screen (mise-tasks/shot): $HEXILATOR_DOC to $HEXILATOR_SHOT."""

import os
import traceback

try:
    import FreeCAD as App
    import FreeCADGui as Gui

    App.openDocument(os.environ["HEXILATOR_DOC"])
    Gui.updateGui()
    v = Gui.ActiveDocument.ActiveView
    getattr(v, "view" + os.environ.get("HEXILATOR_VIEW", "isometric").capitalize())()
    v.fitAll()
    Gui.updateGui()
    v.saveImage(os.environ["HEXILATOR_SHOT"], 1600, 1200, "White")
except Exception:
    traceback.print_exc()
os._exit(0)
