# SPDX-License-Identifier: Apache-2.0
"""The HexGridPad PartDesign feature: the additive counterpart of HexGrid (see DESIGN.md).

The proxy class name and module path are stored in documents; never rename them.
"""

import FreeCAD as App
import Part

from . import __version__
from .feature import (EDITOR_HIDDEN, LATTICE_INPUTS, _add_properties,
                      field_face, openings, plan_grid)

MODES = ("Walls", "Cells")

# (type, name, default, doc); group "HexGrid", after the lattice inputs (feature.LATTICE_INPUTS)
PAD_ONLY_INPUTS = (
    ("App::PropertyEnumeration", "Mode", MODES,
     "Walls pads the field minus the cells (ribs); Cells pads the cells (bosses)"),
    ("App::PropertyLength", "Height", 2.0, "Pad height (> 0)"),
    ("App::PropertyBool", "Reversed", False,
     "Pad against the sketch normal instead of along it, as Pad does"),
    ("App::PropertyLength", "Border", 0.0,
     "Walls only: width of a rib along the inside of the field's outline and around each "
     "keep-out; 0 = none"),
)
PAD_INPUTS = LATTICE_INPUTS + PAD_ONLY_INPUTS


def _update_editor_modes(obj):
    """Lattice and Sides only for the shapes that use them; Border only for Walls."""
    from .feature import _update_editor_modes as lattice_modes
    lattice_modes(obj)
    if hasattr(obj, "Border"):
        obj.setEditorMode("Border", 0 if getattr(obj, "Mode", "Walls") == "Walls"
                          else EDITOR_HIDDEN)


class HexGridPad:
    """Proxy for a PartDesign::FeatureAdditivePython."""

    def __init__(self, obj):
        obj.Proxy = self
        _add_properties(obj, PAD_INPUTS)
        _update_editor_modes(obj)

    def onChanged(self, obj, prop):
        if prop in ("CellShape", "Mode"):
            _update_editor_modes(obj)

    def onDocumentRestored(self, obj):
        _add_properties(obj, PAD_INPUTS)
        _update_editor_modes(obj)
        if App.GuiUp:
            from .viewprovider import ensure_view_provider
            ensure_view_provider(obj)

    def dumps(self):
        return None

    def loads(self, state):
        return None

    def execute(self, obj):
        base = obj.BaseFeature
        if base is not None and base.Shape.isNull():
            raise ValueError("HexGridPad: the feature before it in the body has no shape")
        tool, stats = build_pad_tool(obj)
        obj.AddSubShape = tool
        if base is None:
            # the feature's own shape sits in body coordinates, without a Placement
            result = tool.copy()
            matrix = result.Placement.toMatrix()
            result.Placement = App.Placement()
            result.transformShape(matrix, True)
        else:
            result = base.Shape.fuse(tool)
        if obj.Refine:
            result = result.removeSplitter()
        solids = result.Solids
        if len(solids) != 1:
            hint = (" (Cells mode with nothing to stand on gives separate bosses; pad it onto "
                    "a solid)" if obj.Mode == "Cells" and base is None else "")
            raise ValueError("HexGridPad: the result has %d solids; a body needs exactly one%s"
                             % (len(solids), hint))
        obj.Shape = solids[0]
        obj.WholeCells, obj.PartialCells, obj.FallbackCells, obj.OpenArea = stats
        if obj.Version != __version__:
            obj.Version = __version__


def build_pad_tool(obj):
    """The pad's solid (in body coordinates) and the result counts (as HexGrid's)."""
    height = obj.Height.Value
    if height <= 0:
        raise ValueError("HexGridPad: Height must be > 0")
    border = obj.Border.Value
    if border < 0:
        raise ValueError("HexGridPad: Border must be >= 0")
    prof, local, lat_pl, p = plan_grid(obj)
    region = field_face(local, lat_pl)
    faces, whole, partial, fallback, area = openings(p, local, lat_pl, None, region)
    if obj.Mode == "Cells":
        if not faces:
            raise ValueError("HexGridPad: no cells fit the field; there is nothing to pad")
        profile2d = Part.makeCompound(faces)
    else:
        profile2d = walls_face(region, faces, border)
    vec = App.Vector(0, 0, -height if obj.Reversed else height)
    tool = profile2d.extrude(vec)
    tool.Placement = prof.Placement.multiply(lat_pl)
    return tool, (whole, partial, fallback, area)


def walls_face(region, cells, border):
    """The walls' 2D shape: the field minus the cells, with a rib of width border along its
    outline and around each keep-out (the cells are only cut where they are inside the rib's
    inner edge). region is the field's face and cells are the cell faces, in one frame."""
    if cells:
        openings2d = Part.makeCompound(cells)
        if border > 0:
            inner = inset(region, border)
            openings2d = openings2d.common(inner) if inner is not None else None
    else:
        openings2d = None
    walls = region.cut(openings2d) if openings2d is not None and openings2d.Faces else region
    faces = [f for f in walls.removeSplitter().Faces if f.Area > 1e-9]
    if not faces:
        raise ValueError("HexGridPad: the cells leave no walls to pad")
    return Part.makeCompound(faces)


def inset(region, border):
    """The field's face offset inwards by border (its outline moves in, keep-outs grow), as a
    compound of faces, or None when nothing is left.

    OCC's 2D offset of a face with holes is wrong (it shrinks the holes too, or drops the
    outline), so each loop is offset as a face of its own, and the holes are subtracted.
    """
    out = []
    for face in region.Faces:
        shrunk = _grow(face.OuterWire, -border)
        if shrunk is None:
            continue
        for hole in face.Wires:
            if not hole.isSame(face.OuterWire):
                grown = _grow(hole, border)
                if grown is not None:
                    shrunk = shrunk.cut(grown)
        out.extend(f for f in shrunk.Faces if f.Area > 1e-9)
    return Part.makeCompound(out) if out else None


def _grow(wire, d):
    """The area inside the closed wire, offset outwards by d (inwards if d < 0), as a face.
    None if it vanishes. Arcs round the corners that open up."""
    face = Part.Face(wire)
    for sign in (1, -1):  # the offset's direction follows the wire's, so check which way grew
        try:
            r = face.makeOffset2D(sign * d, 0)
        except Exception:  # OCC reports a collapsed offset as an error
            return None
        if r.isNull() or not r.Faces:
            return None
        if (r.Area > face.Area) == (d > 0):
            return r
    return None


# --- creation ---

def make_hex_grid_pad(body, profile, name="HexGridPad", **props):
    """Add a HexGridPad to body, padding the field drawn in profile. props set its properties.

    Hides the profile and the previous feature as the GUI would, so a headless save opens
    with the body and its Tip showing.
    """
    obj = body.newObject("PartDesign::FeatureAdditivePython", name)
    HexGridPad(obj)
    obj.Profile = (profile, [])
    for k, v in props.items():
        setattr(obj, k, v)
    if App.GuiUp:
        from .viewprovider import ensure_view_provider
        ensure_view_provider(obj)
    base = obj.BaseFeature
    if base is not None:
        base.Visibility = False
    profile.Visibility = False
    obj.Visibility = True
    return obj
