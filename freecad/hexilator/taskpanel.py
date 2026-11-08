# SPDX-License-Identifier: Apache-2.0
"""The task panel of HexGrid and HexGridPad (see DESIGN.md, GUI).

Shaped like PartDesign's own feature dialogs (TaskDlgFeatureParameters): edits apply to the
feature as they're made, with a debounced preview; OK recomputes, checks the result and
commits the transaction; Cancel aborts it, which also deletes a feature that was just created.
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

from .commands import body_of, is_profile
from .viewprovider import ICON, PAD_ICON, is_pad

translate = App.Qt.translate

PREVIEW_MS = 300
"""Debounce for the preview recompute, so typing doesn't recompute a big grid per key."""

current = None
"""The open panel, if any (for tests and macros)."""

# (property, label, unit, minimum)
# the lattice and field fields, shared by both features
QUANTITIES = (
    ("CellSize", QtCore.QT_TRANSLATE_NOOP("Hexilator", "Cell size"), "mm", 0.0),
    ("Web", QtCore.QT_TRANSLATE_NOOP("Hexilator", "Web"), "mm", 0.0),
    ("Angle", QtCore.QT_TRANSLATE_NOOP("Hexilator", "Angle"), "deg", -360.0),
    ("AnchorX", QtCore.QT_TRANSLATE_NOOP("Hexilator", "Anchor X"), "mm", -1e9),
    ("AnchorY", QtCore.QT_TRANSLATE_NOOP("Hexilator", "Anchor Y"), "mm", -1e9),
)
# what follows the Edges and Type or Mode fields
CUT_QUANTITIES = (
    ("Depth", QtCore.QT_TRANSLATE_NOOP("Hexilator", "Depth"), "mm", 0.0),
)
PAD_QUANTITIES = (
    ("Height", QtCore.QT_TRANSLATE_NOOP("Hexilator", "Height"), "mm", 0.0),
    ("Border", QtCore.QT_TRANSLATE_NOOP("Hexilator", "Border"), "mm", 0.0),
)

ENUM_TEXT = {
    "Snap": QtCore.QT_TRANSLATE_NOOP("Hexilator", "Snap to the lattice"),
    "Whole": QtCore.QT_TRANSLATE_NOOP("Hexilator", "Whole cells only"),
    "Free": QtCore.QT_TRANSLATE_NOOP("Hexilator", "Clip exactly"),
    "Dimension": QtCore.QT_TRANSLATE_NOOP("Hexilator", "Dimension"),
    "ThroughAll": QtCore.QT_TRANSLATE_NOOP("Hexilator", "Through all"),
    "Walls": QtCore.QT_TRANSLATE_NOOP("Hexilator", "Walls (ribs)"),
    "Cells": QtCore.QT_TRANSLATE_NOOP("Hexilator", "Cells (bosses)"),
    "Hexagon": QtCore.QT_TRANSLATE_NOOP("Hexilator", "Hexagon"),
    "Square": QtCore.QT_TRANSLATE_NOOP("Hexilator", "Square"),
    "Triangle": QtCore.QT_TRANSLATE_NOOP("Hexilator", "Triangle"),
    "Circle": QtCore.QT_TRANSLATE_NOOP("Hexilator", "Circle"),
    "Polygon": QtCore.QT_TRANSLATE_NOOP("Hexilator", "Polygon"),
    "Hexagonal": QtCore.QT_TRANSLATE_NOOP("Hexilator", "Hexagonal"),
}


def _has_expression(obj, prop):
    return any(path == prop for path, _ in obj.ExpressionEngine)


def _solid_features(body):
    return [o for o in body.Group if o.isDerivedFrom("PartDesign::Feature")]


class HexGridTaskPanel:
    """Edits a HexGrid, or a HexGridPad (which has Mode, Height and Border instead of Type and
    Depth). The feature decides which fields show."""

    def __init__(self, obj):
        global current
        self.obj = obj
        self.pad = is_pad(obj)
        self.doc = obj.Document
        self.body = body_of(obj)
        self.selecting = False
        self.closed = False
        # A new feature comes with its "Create" transaction open; an edit opens its own (a
        # double-click's empty "Edit" transaction is simply replaced).
        if not self.doc.HasPendingTransaction:
            self.doc.openTransaction(translate("Hexilator", "Edit %s") % obj.Label)
        # Show this feature while editing, and put the body's display back afterwards.
        self.shown = []
        if self.body is not None:
            self.shown = [o for o in _solid_features(self.body) if o.Visibility]
            for o in self.shown:
                if o is not obj:
                    o.Visibility = False
        obj.Visibility = True

        self.timer = QtCore.QTimer()
        self.timer.setSingleShot(True)
        self.timer.setInterval(PREVIEW_MS)
        self.timer.timeout.connect(self.preview_now)

        self.form = self._build()
        self._load()
        self._update_results()
        current = self

    # --- form ---

    def _build(self):
        form = QtWidgets.QWidget()
        form.setWindowTitle(translate("Hexilator", "Hex grid pad" if self.pad else "Hex grid"))
        form.setWindowIcon(QtGui.QIcon(PAD_ICON if self.pad else ICON))
        top = QtWidgets.QVBoxLayout(form)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel(translate("Hexilator", "Field:")))
        self.profile_label = QtWidgets.QLabel()
        row.addWidget(self.profile_label, 1)
        self.select_button = QtWidgets.QPushButton(translate("Hexilator", "Select…"))
        self.select_button.setCheckable(True)
        self.select_button.setToolTip(translate(
            "Hexilator", "Pick another sketch in this body as the field"))
        self.select_button.toggled.connect(self._toggle_select)
        row.addWidget(self.select_button)
        top.addLayout(row)

        grid = QtWidgets.QFormLayout()
        loader = Gui.UiLoader()
        self.shape = self._combo("CellShape")
        grid.addRow(translate("Hexilator", "Shape") + ":", self.shape)
        self.lattice = self._combo("Lattice")
        grid.addRow(translate("Hexilator", "Lattice") + ":", self.lattice)
        self.sides = loader.createWidget("Gui::IntSpinBox")
        self.sides.setRange(3, 64)
        self.sides.setToolTip(self.obj.getDocumentationOfProperty("Sides"))
        grid.addRow(translate("Hexilator", "Sides") + ":", self.sides)
        self.quantities = {}
        self.bindings = []
        self.type = self.mode = None
        for prop, label, unit, minimum in QUANTITIES:
            self._quantity(grid, loader, prop, label, unit, minimum)
        self.clip = self._combo("ClipMode")
        grid.addRow(translate("Hexilator", "Edges") + ":", self.clip)
        if self.pad:
            self.mode = self._combo("Mode")
            grid.addRow(translate("Hexilator", "Mode") + ":", self.mode)
        else:
            self.type = self._combo("Type")
            grid.addRow(translate("Hexilator", "Type") + ":", self.type)
        for prop, label, unit, minimum in PAD_QUANTITIES if self.pad else CUT_QUANTITIES:
            self._quantity(grid, loader, prop, label, unit, minimum)
        self.reversed = QtWidgets.QCheckBox(translate("Hexilator", "Reversed"))
        self.reversed.setToolTip(self.obj.getDocumentationOfProperty("Reversed"))
        grid.addRow(self.reversed)
        self.refine = QtWidgets.QCheckBox(translate("Hexilator", "Refine"))
        self.refine.setToolTip(self.obj.getDocumentationOfProperty("Refine"))
        grid.addRow(self.refine)
        top.addLayout(grid)

        self.results = QtWidgets.QLabel()
        self.results.setWordWrap(True)
        top.addWidget(self.results)
        return form

    def _quantity(self, grid, loader, prop, label, unit, minimum):
        w = loader.createWidget("Gui::QuantitySpinBox")
        w.setProperty("unit", unit)
        w.setProperty("minimum", minimum)
        w.setProperty("maximum", 1e9 if unit == "mm" else 360.0)
        w.setToolTip(self.obj.getDocumentationOfProperty(prop))
        self.quantities[prop] = w
        grid.addRow(translate("Hexilator", label) + ":", w)

    def _combo(self, prop):
        c = QtWidgets.QComboBox()
        for value in self.obj.getEnumerationsOfProperty(prop):
            c.addItem(translate("Hexilator", ENUM_TEXT.get(value, value)), value)
        c.setToolTip(self.obj.getDocumentationOfProperty(prop))
        return c

    def _load(self):
        """Fill the widgets from the feature, then connect them."""
        obj = self.obj
        for prop, w in self.quantities.items():
            w.setProperty("rawValue", getattr(obj, prop).Value)
            b = Gui.ExpressionBinding(w)
            b.bind(obj, prop)
            b.setAutoApply(True)  # an expression set in the f(x) editor applies at once
            self.bindings.append(b)
            w.valueChanged.connect(lambda _q, p=prop, w=w: self._quantity_changed(p, w))
        self.sides.setValue(obj.Sides)
        b = Gui.ExpressionBinding(self.sides)
        b.bind(obj, "Sides")
        b.setAutoApply(True)
        self.bindings.append(b)
        self.sides.valueChanged.connect(self._sides_changed)
        combos = [("CellShape", self.shape), ("Lattice", self.lattice), ("ClipMode", self.clip),
                  ("Mode", self.mode) if self.pad else ("Type", self.type)]
        for prop, c in combos:
            c.setCurrentIndex(c.findData(getattr(obj, prop)))
            c.currentIndexChanged.connect(lambda _i, p=prop, c=c: self._set(p, c.currentData()))
        self.reversed.setChecked(obj.Reversed)
        self.reversed.toggled.connect(lambda v: self._set("Reversed", bool(v)))
        self.refine.setChecked(obj.Refine)
        self.refine.toggled.connect(lambda v: self._set("Refine", bool(v)))
        self._update_profile_label()
        self._update_enabled()

    def _update_profile_label(self):
        link = self.obj.Profile
        prof = (link[0] if isinstance(link, tuple) else link) if link else None
        self.profile_label.setText(prof.Label if prof is not None
                                   else translate("Hexilator", "(none)"))

    def _update_enabled(self):
        if self.pad:
            self.quantities["Border"].setEnabled(self.obj.Mode == "Walls")
        else:
            self.quantities["Depth"].setEnabled(self.obj.Type == "Dimension")
        shape = self.obj.CellShape
        self.lattice.setEnabled(shape in ("Circle", "Polygon"))
        self.sides.setEnabled(shape == "Polygon")

    def _update_results(self):
        obj = self.obj
        if "Invalid" in obj.State or "Error" in obj.State:
            text = translate("Hexilator", "Error: %s") % obj.getStatusString()
        else:
            text = translate(
                "Hexilator", "%d whole cells, %d partial (%d fallback); open area %s") % (
                obj.WholeCells, obj.PartialCells, obj.FallbackCells, obj.OpenArea.UserString)
        self.results.setText(text)

    # --- edits ---

    def _quantity_changed(self, prop, w):
        if _has_expression(self.obj, prop):
            self.schedule()  # the binding set the expression; just refresh
            return
        self._set(prop, App.Units.Quantity(w.property("rawValue"),
                                           getattr(self.obj, prop).Unit))

    def _sides_changed(self, value):
        if _has_expression(self.obj, "Sides"):
            self.schedule()
            return
        self._set("Sides", int(value))

    def _set(self, prop, value):
        if getattr(self.obj, prop) != value:
            setattr(self.obj, prop, value)
        if prop in ("Type", "CellShape", "Mode"):
            self._update_enabled()
        self.schedule()

    def schedule(self):
        self.timer.start()

    def preview_now(self):
        self.timer.stop()
        if self.closed:
            return
        self.obj.touch()
        self.doc.recompute()
        self._update_results()

    # --- picking a profile ---

    def _toggle_select(self, on):
        if on and not self.selecting:
            Gui.Selection.clearSelection()
            Gui.Selection.addObserver(self)
            self.selecting = True
        elif not on and self.selecting:
            Gui.Selection.removeObserver(self)
            self.selecting = False

    def addSelection(self, doc, obj, sub, pnt):
        """Selection observer: take the first 2D object picked in this body as the field."""
        for o in Gui.Selection.getSelection():
            if o is not self.obj and is_profile(o) and body_of(o) is self.body:
                self.set_profile(o)
                break
        QtCore.QTimer.singleShot(0, Gui.Selection.clearSelection)

    def set_profile(self, prof):
        old = self.obj.Profile
        old = (old[0] if isinstance(old, tuple) else old) if old else None
        self.obj.Profile = (prof, [])
        prof.Visibility = False
        if old is not None and old is not prof:
            old.Visibility = False
        self._update_profile_label()
        self.select_button.setChecked(False)
        self.schedule()

    # --- closing ---

    def _detach(self):
        global current
        self.timer.stop()
        self.closed = True
        if self.selecting:
            Gui.Selection.removeObserver(self)
            self.selecting = False
        if current is self:
            current = None

    def _restore_display(self):
        """After editing a feature that wasn't showing (e.g. one below the Tip), show what was."""
        if self.shown and self.obj not in self.shown:
            self.obj.Visibility = False
            for o in self.shown:
                o.Visibility = True

    def accept(self):
        self.timer.stop()
        self.obj.touch()
        self.doc.recompute()
        if "Invalid" in self.obj.State or not self.obj.isValid():
            QtWidgets.QMessageBox.warning(
                Gui.getMainWindow(), translate("Hexilator", "Input error"),
                self.obj.getStatusString() or translate(
                    "Hexilator", "The hex grid could not be built with these parameters."))
            self._update_results()
            return False
        self._detach()
        self._restore_display()
        base = self.obj.BaseFeature
        if base is not None and self.obj.Visibility:
            base.Visibility = False
        Gui.ActiveDocument.resetEdit()
        self.doc.commitTransaction()
        return True

    def reject(self):
        self._detach()
        name = self.obj.Name
        previous = self.obj.BaseFeature
        body = self.body
        self.doc.abortTransaction()  # deletes a feature created in this transaction
        if self.doc.getObject(name) is None:
            target = previous if previous is not None else (body.Tip if body else None)
            if target is not None:
                target.Visibility = True
        else:
            self._restore_display()
        self.doc.recompute()
        Gui.ActiveDocument.resetEdit()
        return True
