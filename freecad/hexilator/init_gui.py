# SPDX-License-Identifier: Apache-2.0
"""GUI start-up, imported by FreeCAD for the freecad.hexilator namespace package.

Registers the icon path and the commands, and adds a Hexilator toolbar to PartDesign with a
workbench manipulator (FreeCAD 1.0+), so there's no workbench of our own. Keep this cheap:
it runs at every GUI start.
"""

import FreeCADGui as Gui

from . import commands
from .viewprovider import ICONS

TOOLBAR = "Hexilator"
"""Toolbar name. It's also the key FreeCAD stores the toolbar's visibility under: never rename."""

WORKBENCH = "PartDesignWorkbench"


def active_workbench_name():
    """The active workbench's registered name.

    activeWorkbench().name() raises during a C++ workbench's first activation, so look it up
    by identity.
    """
    active = Gui.activeWorkbench()
    for name, wb in Gui.listWorkbenches().items():
        if wb is active:
            return name
    return ""


class Manipulator:
    """Adds the commands to PartDesign: a toolbar, and the Subtractive Features menu."""

    def modifyToolBars(self):
        if active_workbench_name() != WORKBENCH:
            return []
        return [{"append": TOOLBAR, "toolBar": ""}] + [
            {"append": name, "toolBar": TOOLBAR} for name in commands.TOOLBAR_COMMANDS]

    def modifyMenuBar(self):
        # menuItem names an entry of the target menu. FreeCAD 1.1.4's MenuItem::findParentOf
        # returns the wrong menu for entries two levels down (e.g. Pocket, in Part Design ›
        # Subtractive Features), so the commands go at the end of the Part Design menu,
        # beside Involute Gear and Sprocket.
        if active_workbench_name() != WORKBENCH:
            return []
        anchor = "PartDesign_Sprocket"
        return [{"append": "Separator", "menuItem": anchor}] + [
            {"append": name, "menuItem": anchor} for name in commands.MENU_COMMANDS]


MANIPULATOR = Manipulator()

Gui.addIconPath(ICONS)
commands.register()
Gui.addWorkbenchManipulator(MANIPULATOR)
