# SPDX-License-Identifier: Apache-2.0
"""The HexGrid PartDesign feature (see DESIGN.md).

The proxy class name and module path are stored in documents; never rename them.
"""

import math

import FreeCAD as App
import Part

from . import __version__
from .core.clip import MODES, plan
from .core.lattice import GRIDS, SHAPES
from .core.geom import Arc, Loop, Seg

TYPES = ("Dimension", "ThroughAll")

# (type, name, default, doc); group "HexGrid"
INPUTS = (
    ("App::PropertyLinkSub", "Profile", None,
     "Field sketch: outer loops are fields, inner loops keep-outs"),
    ("App::PropertyEnumeration", "CellShape", SHAPES,
     "Hexagon, Square or Triangle (these tile and snap), Circle or Polygon (Whole and Free "
     "only; see Lattice and Sides)"),
    ("App::PropertyLength", "CellSize", 5.0,
     "Inscribed-circle diameter: across flats for a hexagon, the side of a square, the "
     "diameter of a circle"),
    ("App::PropertyLength", "Web", 1.2,
     "Gap between neighbouring cells (> 0); for polygons, between their inscribed circles"),
    ("App::PropertyEnumeration", "Lattice", GRIDS,
     "Centre grid for Circle and Polygon cells; the other shapes have their own"),
    ("App::PropertyIntegerConstraint", "Sides", (8, 3, 64, 1),
     "Number of sides of a Polygon cell (3 to 64)"),
    ("App::PropertyAngle", "Angle", 0.0,
     "Lattice rotation about the anchor; 0 = flat-top (flats parallel to sketch X)"),
    ("App::PropertyDistance", "AnchorX", 0.0, "A cell centre sits here (sketch X)"),
    ("App::PropertyDistance", "AnchorY", 0.0, "A cell centre sits here (sketch Y)"),
    ("App::PropertyEnumeration", "ClipMode", MODES,
     "Snap: edges snap onto lattice lines; Whole: whole cells only; Free: clip exactly"),
    ("App::PropertyEnumeration", "Type", TYPES, "Dimension or ThroughAll, as for Pocket"),
    ("App::PropertyLength", "Depth", 3.0, "Cut depth for Type Dimension"),
    ("App::PropertyBool", "Reversed", False, "Cut along the sketch normal instead of against it"),
)

# (type, name, doc); group "Result", read-only outputs
OUTPUTS = (
    ("App::PropertyInteger", "WholeCells", "Cells cut whole"),
    ("App::PropertyInteger", "PartialCells", "Cells cut partially (fallback cells included)"),
    ("App::PropertyInteger", "FallbackCells",
     "Partial cells next to a boundary that could not snap (arcs, splines, off-angle edges)"),
    ("App::PropertyArea", "OpenArea", "Total area of the openings in the sketch plane"),
    ("App::PropertyString", "Version", "Hexilator version that last recomputed this feature"),
)

PROP_READONLY = 1
PROP_OUTPUT = 8


def _add_properties(obj):
    names = obj.PropertiesList
    for typ, name, default, doc in INPUTS:
        if name in names:
            continue
        obj.addProperty(typ, name, "HexGrid", doc)
        if typ == "App::PropertyEnumeration":
            setattr(obj, name, list(default))
            setattr(obj, name, default[0])
        elif default is not None:
            setattr(obj, name, default)
    for typ, name, doc in OUTPUTS:
        if name not in names:
            obj.addProperty(typ, name, "Result", doc, PROP_READONLY | PROP_OUTPUT)
    _update_editor_modes(obj)


EDITOR_HIDDEN = 2


def _update_editor_modes(obj):
    """Show Lattice only for Circle and Polygon cells, and Sides only for Polygon."""
    shape = getattr(obj, "CellShape", "Hexagon")
    for name, shown in (("Lattice", shape in ("Circle", "Polygon")),
                        ("Sides", shape == "Polygon")):
        if hasattr(obj, name):
            obj.setEditorMode(name, 0 if shown else EDITOR_HIDDEN)


class HexGrid:
    """Proxy for a PartDesign::FeatureSubtractivePython."""

    def __init__(self, obj):
        obj.Proxy = self
        _add_properties(obj)

    def onChanged(self, obj, prop):
        if prop == "CellShape":
            _update_editor_modes(obj)

    def onDocumentRestored(self, obj):
        _add_properties(obj)
        if App.GuiUp:
            from .viewprovider import ensure_view_provider
            ensure_view_provider(obj)

    def dumps(self):
        return None

    def loads(self, state):
        return None

    def execute(self, obj):
        base = obj.BaseFeature
        if base is None or base.Shape.isNull():
            raise ValueError("HexGrid needs a solid before it in the body (BaseFeature is empty)")
        tool, stats = build_tool(obj, base.Shape)
        obj.AddSubShape = tool
        result = base.Shape.cut(tool) if not tool.isNull() else base.Shape.copy()
        if obj.Refine:
            result = result.removeSplitter()
        solids = result.Solids
        if len(solids) != 1:
            raise ValueError("HexGrid: the result has %d solids; a body needs exactly one"
                             % len(solids))
        obj.Shape = solids[0]
        obj.WholeCells, obj.PartialCells, obj.FallbackCells, obj.OpenArea = stats
        if obj.Version != __version__:
            obj.Version = __version__


# --- profile to core loops ---

def _profile_object(obj):
    link = obj.Profile
    if not link:
        raise ValueError("HexGrid: Profile is not set")
    prof = link[0] if isinstance(link, tuple) else link
    if not hasattr(prof, "Placement") or prof.Shape.isNull():
        raise ValueError("HexGrid: Profile %s has no shape" % prof.Label)
    return prof


def _local_shape(prof):
    """The profile's shape in its own frame: the sketch plane is z = 0."""
    shp = prof.Shape.copy()
    shp.transformShape(prof.Placement.inverse().toMatrix(), True)
    bb = shp.BoundBox
    if abs(bb.ZMin) > 1e-6 or abs(bb.ZMax) > 1e-6:
        raise ValueError("HexGrid: Profile %s is not flat in its own XY plane" % prof.Label)
    return shp


def _edge_prims(e):
    """Seg/Arc primitives for one edge, from its first to its last parameter.

    Returns (prims, curved) where curved marks discretised curves.
    """
    u0, u1 = e.ParameterRange
    crv = e.Curve
    p0, p1 = e.valueAt(u0), e.valueAt(u1)
    if isinstance(crv, (Part.Line, Part.LineSegment)):
        return [Seg((p0.x, p0.y), (p1.x, p1.y))], False
    if isinstance(crv, Part.Circle):
        c = (crv.Center.x, crv.Center.y)
        r = crv.Radius

        def ang(v):
            return math.atan2(v.y - c[1], v.x - c[0])

        a0 = ang(p0)
        aq = ang(e.valueAt(u0 + (u1 - u0) / 4.0))
        ccw = (aq - a0) % (2 * math.pi) < math.pi
        if p0.distanceToPoint(p1) < 1e-9:
            s = math.pi if ccw else -math.pi
            return [Arc(c, r, a0, s), Arc(c, r, a0 + s, s)], False
        a1 = ang(p1)
        sweep = (a1 - a0) % (2 * math.pi) if ccw else -((a0 - a1) % (2 * math.pi))
        return [Arc(c, r, a0, sweep)], False
    pts = e.discretize(Deflection=1e-3)
    return [Seg((a.x, a.y), (b.x, b.y)) for a, b in zip(pts[:-1], pts[1:])], True


def _wire_loop(w):
    prims = []
    curved = False
    for e in w.OrderedEdges:
        ps, cv = _edge_prims(e)
        curved = curved or cv
        prims.append(ps)
    if len(prims) > 1:
        # orient each edge's chain to follow the previous one
        def ends(ch):
            return ch[0].start, ch[-1].end

        def rev(ch):
            return [p.reversed() for p in reversed(ch)]

        s0, e0 = ends(prims[0])
        s1, e1 = ends(prims[1])
        if min(_d(s0, s1), _d(s0, e1)) < min(_d(e0, s1), _d(e0, e1)):
            prims[0] = rev(prims[0])
        for k in range(1, len(prims)):
            prev_end = prims[k - 1][-1].end
            s, e = ends(prims[k])
            if _d(e, prev_end) < _d(s, prev_end):
                prims[k] = rev(prims[k])
    flat = [p for ch in prims for p in ch]
    if _d(flat[0].start, flat[-1].end) > 1e-5:
        raise ValueError("HexGrid: the profile has an open wire")
    return Loop(flat, curved or None)


def _d(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def lattice_placement(obj):
    """Placement of the lattice frame in the sketch frame."""
    return App.Placement(App.Vector(obj.AnchorX.Value, obj.AnchorY.Value, 0),
                         App.Rotation(App.Vector(0, 0, 1), obj.Angle.Value))


def profile_loops(local, lat_pl):
    """Core loops in the lattice frame, from the profile's local shape."""
    # Rotation.Angle is in radians, about Axis (which may point along -z)
    a = -lat_pl.Rotation.Angle * (1 if lat_pl.Rotation.Axis.z >= 0 else -1)
    ca, sa = math.cos(a), math.sin(a)
    ox, oy = lat_pl.Base.x, lat_pl.Base.y

    def f(p):
        x, y = p[0] - ox, p[1] - oy
        return (ca * x - sa * y, sa * x + ca * y)

    loops = []
    for w in local.Wires:
        lp = _wire_loop(w)
        prims = [p.transformed(f) if isinstance(p, Seg) else p.transformed(f, a)
                 for p in lp.prims]
        loops.append(Loop(prims, lp.curved))
    return loops


# --- tool ---

def _face(loops):
    wires = [Part.makePolygon([App.Vector(x, y, 0) for x, y in lp + [lp[0]]]) for lp in loops]
    if len(wires) == 1:
        return Part.Face(wires[0])
    return Part.makeFace(wires, "Part::FaceMakerBullseye")


def build_tool(obj, base_shape):
    """The cutting tool (a compound of prisms, in body coordinates) and the result counts."""
    prof = _profile_object(obj)
    local = _local_shape(prof)
    lat_pl = lattice_placement(obj)
    loops = profile_loops(local, lat_pl)
    mode = obj.ClipMode
    p = plan(loops, obj.CellSize.Value, obj.Web.Value, mode,
             obj.CellShape, obj.Lattice, obj.Sides)
    for w in p.warnings:
        App.Console.PrintWarning("%s: %s\n" % (obj.Label, w))

    if obj.Type == "ThroughAll":
        bb = base_shape.BoundBox
        length = 2.0 * bb.DiagonalLength + 1.0
    else:
        length = obj.Depth.Value
        if length <= 0:
            raise ValueError("HexGrid: Depth must be > 0")
    vec = App.Vector(0, 0, length if obj.Reversed else -length)

    lat = p.lattice
    cell_faces = {key: _cell_face(lat, key) for key in lat.keys()}
    templates = {}
    region_face = None
    prisms = []
    whole = partial = fallback = 0
    area = 0.0
    for pc in p.pieces:
        cx, cy = lat.center(pc.i, pc.j)
        key = lat.key(pc.i, pc.j)
        if pc.kind == "whole":
            if key not in templates:
                templates[key] = cell_faces[key].extrude(vec)
            prisms.append(templates[key].translated(App.Vector(cx, cy, 0)))
            whole += 1
            area += pc.area
        elif pc.kind in ("exact", "fallback"):
            prisms.append(_face(pc.loops).extrude(vec))
            partial += 1
            fallback += pc.kind == "fallback"
            area += pc.area
        else:  # free
            if region_face is None:
                region_face = _region_face(local, lat_pl)
            cellf = cell_faces[key].translated(App.Vector(cx, cy, 0))
            common = cellf.common(region_face)
            faces = [f for f in common.Faces if f.Area > 1e-9]
            if not faces:
                continue
            for f in faces:
                prisms.append(f.extrude(vec))
                area += f.Area
            partial += 1
    if not prisms:
        return Part.Shape(), (0, 0, 0, 0.0)
    tool = Part.makeCompound(prisms)
    tool.Placement = prof.Placement.multiply(lat_pl)
    return tool, (whole, partial, fallback, area)


def _cell_face(lat, key):
    """The face of one cell at the origin: a true circle for round cells."""
    if lat.round:
        return Part.Face(Part.Wire(Part.makeCircle(lat.s / 2.0)))
    return _face([lat.outline(key)])


def _region_face(local, lat_pl):
    face = Part.makeFace(local.Wires, "Part::FaceMakerBullseye")
    face.transformShape(lat_pl.inverse().toMatrix(), True)
    return face


# --- creation ---

def make_hex_grid(body, profile, name="HexGrid", **props):
    """Add a HexGrid to body, cutting the field drawn in profile. props set its properties.

    Hides the profile and the previous feature as the GUI would, so a headless save opens
    with the body and its Tip showing.
    """
    obj = body.newObject("PartDesign::FeatureSubtractivePython", name)
    HexGrid(obj)
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
