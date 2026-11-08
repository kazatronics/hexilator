# SPDX-License-Identifier: Apache-2.0
"""Snapping and clipping (see DESIGN.md, Clipping). Works in the lattice frame."""

import math

from .geom import EPS, Loop, Region, Seg, dot, dist, line_intersection, poly_area, \
    poly_centroid, seg_hits_convex, union_tiles
from .lattice import DEG30, Lattice

MODES = ("Snap", "Whole", "Free")


class Piece:
    """One cell's opening.

    kind: 'whole', 'exact' (snapped clip), 'fallback' (single-chord piece) or 'free' (to be
    clipped exactly by the FreeCAD layer). loops: CCW outer loops and CW holes, in the lattice
    frame (None for 'whole' and 'free').
    """

    __slots__ = ("i", "j", "kind", "loops", "area")

    def __init__(self, i, j, kind, loops=None, area=0.0):
        self.i, self.j, self.kind, self.loops, self.area = i, j, kind, loops, area

    def __repr__(self):
        return "Piece(%d, %d, %s, area=%.4g)" % (self.i, self.j, self.kind, self.area)


class Plan:
    def __init__(self, lattice, pieces, warnings):
        self.lattice = lattice
        self.pieces = pieces
        self.warnings = warnings

    def count(self, *kinds):
        return sum(1 for pc in self.pieces if pc.kind in kinds)


# --- snapping ---

def _direction(seg):
    return math.atan2(seg.b[1] - seg.a[1], seg.b[0] - seg.a[0])


def _merge_collinear(segs):
    """Merge consecutive segments that run in the same direction on the same line."""
    segs = [s for s in segs if dist(s.a, s.b) > EPS]
    changed = True
    while changed and len(segs) > 2:
        changed = False
        for k in range(len(segs)):
            a, b = segs[k - 1], segs[k]
            da, db = _direction(a), _direction(b)
            dd = (db - da + math.pi) % (2 * math.pi) - math.pi
            if abs(dd) < 1e-9:
                merged = Seg(a.a, b.b)
                if k == 0:
                    segs = [merged] + segs[1:-1]
                else:
                    segs = segs[:k - 1] + [merged] + segs[k + 1:]
                changed = True
                break
    return segs


def _simple(poly):
    """True if no two non-adjacent edges of the closed polygon meet."""
    n = len(poly)
    for a in range(n):
        p0, p1 = poly[a], poly[(a + 1) % n]
        for b in range(a + 2, n):
            if a == 0 and b == n - 1:
                continue
            q0, q1 = poly[b], poly[(b + 1) % n]
            if _segments_meet(p0, p1, q0, q1):
                return False
    return True


def _segments_meet(p0, p1, q0, q1):
    def orient(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return 0 if abs(v) < 1e-12 else (1 if v > 0 else -1)

    o1, o2 = orient(p0, p1, q0), orient(p0, p1, q1)
    o3, o4 = orient(q0, q1, p0), orient(q0, q1, p1)
    if o1 != o2 and o3 != o4:
        return True
    return False


def snap_loop(loop, lattice):
    """The loop with each edge moved onto the nearest lattice line on the region's side.

    The loop must be oriented with the region on its left. Returns (Loop, None) on success,
    (None, reason) when the loop can't snap.
    """
    if loop.curved:
        return None, "has curves"
    segs = _merge_collinear(loop.prims)
    if len(segs) < 3:
        return None, "degenerate"
    lines = []
    for s in segs:
        k = Lattice.direction_index(_direction(s))
        if k is None:
            return None, "edge off the lattice directions"
        a = k * DEG30
        d = (math.cos(a), math.sin(a))
        nl = (-d[1], d[0])  # left normal: points into the region
        mid = ((s.a[0] + s.b[0]) / 2, (s.a[1] + s.b[1]) / 2)
        c = lattice.snap_up(k % 6, dot(nl, mid), EPS)
        lines.append((d, nl, c))
    n = len(lines)
    verts = []
    for k in range(n):
        q = line_intersection(lines[k - 1][1], lines[k - 1][2], lines[k][1], lines[k][2])
        if q is None:
            return None, "collapses when snapped"
        verts.append(q)
    new = []
    for k in range(n):
        a, b = verts[k], verts[(k + 1) % n]
        d = lines[k][0]
        if dot((b[0] - a[0], b[1] - a[1]), d) <= EPS:
            return None, "collapses when snapped"
        new.append(Seg(a, b, lattice=True))
    if not _simple(verts):
        return None, "self-intersects when snapped"
    out = Loop(new, curved=False)
    if (out.signed_area() > 0) != (loop.signed_area() > 0):
        return None, "collapses when snapped"
    return out, None


def mark_lattice_segments(loop, lattice):
    """Flag straight edges of an unsnapped loop that already lie on lattice lines."""
    prims = []
    for p in loop.prims:
        if isinstance(p, Seg):
            k = Lattice.direction_index(_direction(p))
            if k is not None:
                a = k * DEG30
                nl = (-math.sin(a), math.cos(a))
                if lattice.on_line(k % 6, dot(nl, p.a), EPS) and \
                        lattice.on_line(k % 6, dot(nl, p.b), EPS):
                    p = Seg(p.a, p.b, lattice=True)
        prims.append(p)
    return Loop(prims, loop.curved)


def snap_region(region, lattice):
    """Snap every loop that can snap. Returns (Region, warnings)."""
    warnings = []
    parts = []
    for outer, holes in region.parts:
        new = []
        for lp in [outer] + holes:
            snapped, why = snap_loop(lp, lattice)
            if snapped is None:
                if why not in ("has curves", "edge off the lattice directions"):
                    warnings.append("a loop %s; it is kept as drawn" % why)
                snapped = mark_lattice_segments(lp, lattice)
            new.append(snapped)
        parts.append((new[0], new[1:]))
    return Region(parts), warnings


# --- planning ---

def _translate(poly, c):
    return [(x + c[0], y + c[1]) for x, y in poly]


def plan(loops, cell, web, mode="Snap"):
    """Decide every cell's opening for a field given as loops in the lattice frame."""
    if mode not in MODES:
        raise ValueError("ClipMode must be one of %s" % ", ".join(MODES))
    lat = Lattice(cell, web)
    region = Region.from_loops(loops)
    warnings = []
    if mode == "Snap":
        region, warnings = snap_region(region, lat)
    pieces = []
    box = region.bbox()
    if box is None:
        return Plan(lat, pieces, warnings)
    tiles = lat.tiles()
    cands = lat.candidates()
    for i, j in lat.cells_in(box):
        c = lat.center(i, j)
        hexa = _translate(lat.hexagon, c)
        hits = region.hits(hexa)
        if not hits:
            if region.contains(c):
                pieces.append(Piece(i, j, "whole", None, lat.cell_area))
            continue
        if mode == "Whole":
            continue
        if mode == "Free":
            pieces.append(Piece(i, j, "free"))
            continue
        if all(p.lattice for p in hits):
            inside = [_translate(t, c) for t in tiles
                      if region.contains(poly_centroid(_translate(t, c)))]
            if not inside:
                continue
            area = sum(poly_area(t) for t in inside)
            if area >= lat.cell_area * (1 - 1e-9):
                pieces.append(Piece(i, j, "whole", None, lat.cell_area))
            else:
                pieces.append(Piece(i, j, "exact", union_tiles(inside), area))
            continue
        for kind, poly in cands:
            q = _translate(poly, c)
            if region.classify(q) == "in":
                if kind == "whole":
                    pieces.append(Piece(i, j, "whole", None, lat.cell_area))
                else:
                    pieces.append(Piece(i, j, "fallback", [q], poly_area(q)))
                break
    return Plan(lat, pieces, warnings)
