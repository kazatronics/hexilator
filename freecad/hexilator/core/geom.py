# SPDX-License-Identifier: Apache-2.0
"""Plane geometry for the core: segments, circular arcs, loops, regions and convex polygons.

Pure Python, no FreeCAD. Points are (x, y) tuples in mm.
"""

import math

EPS = 1e-6
"""Boundary tolerance (mm). Geometry closer than this to a boundary counts as on it."""

TAU = 2.0 * math.pi


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class Seg:
    """A straight segment from a to b. `lattice` marks one that lies on a lattice line."""

    __slots__ = ("a", "b", "lattice")

    def __init__(self, a, b, lattice=False):
        self.a = (float(a[0]), float(a[1]))
        self.b = (float(b[0]), float(b[1]))
        self.lattice = lattice

    @property
    def start(self):
        return self.a

    @property
    def end(self):
        return self.b

    def bbox(self):
        return (min(self.a[0], self.b[0]), min(self.a[1], self.b[1]),
                max(self.a[0], self.b[0]), max(self.a[1], self.b[1]))

    def area_term(self):
        return 0.5 * cross(self.a, self.b)

    def crossings(self, p):
        """Crossings of the ray from p towards +x (half-open in y)."""
        (ax, ay), (bx, by) = self.a, self.b
        if (ay > p[1]) != (by > p[1]):
            x = ax + (p[1] - ay) * (bx - ax) / (by - ay)
            if x > p[0]:
                return 1
        return 0

    def transformed(self, f):
        return Seg(f(self.a), f(self.b), self.lattice)

    def reversed(self):
        return Seg(self.b, self.a, self.lattice)

    def with_start(self, p):
        return Seg(p, self.b, self.lattice)

    def hits_convex(self, poly):
        return seg_hits_convex(self.a, self.b, poly)

    def __repr__(self):
        return "Seg(%r, %r%s)" % (self.a, self.b, ", lattice" if self.lattice else "")


class Arc:
    """A circular arc: centre c, radius r, from angle a0 sweeping `sweep` radians (signed).

    The end points p0 and p1 are kept as given (computed from the angles when not given), so a
    loop can weld its joints to exactly shared points (see Loop).
    """

    __slots__ = ("c", "r", "a0", "sweep", "lattice", "p0", "p1")

    def __init__(self, c, r, a0, sweep, p0=None, p1=None):
        self.c = (float(c[0]), float(c[1]))
        self.r = float(r)
        self.a0 = float(a0)
        self.sweep = float(sweep)
        self.lattice = False
        self.p0 = (float(p0[0]), float(p0[1])) if p0 is not None else self.point(self.a0)
        self.p1 = (float(p1[0]), float(p1[1])) if p1 is not None else \
            self.point(self.a0 + self.sweep)

    def point(self, a):
        return (self.c[0] + self.r * math.cos(a), self.c[1] + self.r * math.sin(a))

    @property
    def start(self):
        return self.p0

    @property
    def end(self):
        return self.p1

    def with_start(self, p):
        return Arc(self.c, self.r, self.a0, self.sweep, p, self.p1)

    def contains_angle(self, a, tol=1e-12):
        """True if direction a (radians) lies on the arc."""
        if self.sweep >= 0:
            d = (a - self.a0) % TAU
            return d <= self.sweep + tol or d >= TAU - tol
        d = (self.a0 - a) % TAU
        return d <= -self.sweep + tol or d >= TAU - tol

    def _split_angles(self, base):
        """Angles inside the open sweep of the form base + k*pi/2 ... used for splitting."""
        out = []
        lo, hi = sorted((self.a0, self.a0 + self.sweep))
        k = math.ceil((lo - base) / (math.pi / 2))
        while True:
            a = base + k * math.pi / 2
            if a >= hi:
                break
            if a > lo:
                out.append(a)
            k += 1
        return out

    def bbox(self):
        pts = [self.start, self.end]
        for a in self._split_angles(0.0):
            pts.append(self.point(a))
        xs = [q[0] for q in pts]
        ys = [q[1] for q in pts]
        return (min(xs), min(ys), max(xs), max(ys))

    def area_term(self):
        s, e = self.start, self.end
        return 0.5 * cross(s, e) + 0.5 * self.r * self.r * (self.sweep - math.sin(self.sweep))

    def _monotone_pieces(self):
        """Pieces (a, b, ya, yb) monotone in y, cut at the top and bottom of the circle.

        The outer ends take their y from the stored end points, so they agree exactly with the
        neighbouring primitives; the cuts take exactly c ± r.
        """
        cuts = [a for a in self._split_angles(math.pi / 2) if abs(math.sin(a)) > 0.5]
        if self.sweep < 0:
            cuts = cuts[::-1]
        angles = [self.a0] + cuts + [self.a0 + self.sweep]
        ys = [self.p0[1]] + [self.c[1] + (self.r if math.sin(a) > 0 else -self.r)
                             for a in cuts] + [self.p1[1]]
        return [(angles[k], angles[k + 1], ys[k], ys[k + 1]) for k in range(len(angles) - 1)]

    def crossings(self, p):
        n = 0
        for a, b, ya, yb in self._monotone_pieces():
            if (ya > p[1]) != (yb > p[1]):
                dy = p[1] - self.c[1]
                dx = math.sqrt(max(self.r * self.r - dy * dy, 0.0))
                x = self.c[0] + (dx if math.cos(0.5 * (a + b)) > 0 else -dx)
                if x > p[0]:
                    n += 1
        return n

    def transformed(self, f, rotation=0.0, mirror=False):
        """Map by a rigid motion f whose rotation angle is `rotation` (no mirror support)."""
        return Arc(f(self.c), self.r, self.a0 + rotation, self.sweep, f(self.p0), f(self.p1))

    def reversed(self):
        return Arc(self.c, self.r, self.a0 + self.sweep, -self.sweep, self.p1, self.p0)

    def hits_convex(self, poly):
        """True if the arc meets the closed convex polygon poly (CCW)."""
        if point_in_convex(self.start, poly) or point_in_convex(self.end, poly):
            return True
        n = len(poly)
        for k in range(n):
            a, b = poly[k], poly[(k + 1) % n]
            for q in circle_segment_points(self.c, self.r, a, b):
                if self.contains_angle(math.atan2(q[1] - self.c[1], q[0] - self.c[0]), 1e-9):
                    return True
        return False

    def __repr__(self):
        return "Arc(c=%r, r=%g, a0=%g, sweep=%g)" % (self.c, self.r, self.a0, self.sweep)


def circle_segment_points(c, r, a, b):
    """Points where the circle (c, r) meets the closed segment ab."""
    d = sub(b, a)
    f = sub(a, c)
    A = dot(d, d)
    if A == 0.0:
        return []
    B = 2.0 * dot(f, d)
    C = dot(f, f) - r * r
    disc = B * B - 4.0 * A * C
    if disc < 0.0:
        return []
    sq = math.sqrt(disc)
    out = []
    for t in ((-B - sq) / (2.0 * A), (-B + sq) / (2.0 * A)):
        if -1e-12 <= t <= 1.0 + 1e-12:
            out.append((a[0] + t * d[0], a[1] + t * d[1]))
    return out


# --- convex polygons (CCW lists of points) ---

def poly_area(poly):
    n = len(poly)
    return 0.5 * sum(cross(poly[k], poly[(k + 1) % n]) for k in range(n))


def poly_centroid(poly):
    n = len(poly)
    a = cx = cy = 0.0
    for k in range(n):
        p, q = poly[k], poly[(k + 1) % n]
        w = cross(p, q)
        a += w
        cx += (p[0] + q[0]) * w
        cy += (p[1] + q[1]) * w
    return (cx / (3.0 * a), cy / (3.0 * a))


def halfplanes(poly):
    """Inward half-planes (n, c) with n·x >= c inside, for a CCW convex polygon."""
    out = []
    n = len(poly)
    for k in range(n):
        a, b = poly[k], poly[(k + 1) % n]
        d = sub(b, a)
        ln = math.hypot(*d)
        nrm = (-d[1] / ln, d[0] / ln)
        out.append((nrm, dot(nrm, a)))
    return out


def line_intersection(n1, c1, n2, c2):
    det = n1[0] * n2[1] - n1[1] * n2[0]
    if abs(det) < 1e-12:
        return None
    return ((c1 * n2[1] - c2 * n1[1]) / det, (n1[0] * c2 - n2[0] * c1) / det)


def shrink(poly, eps=EPS):
    """The convex polygon moved inwards by eps on every side."""
    hp = [(nrm, c + eps) for nrm, c in halfplanes(poly)]
    n = len(hp)
    return [line_intersection(*hp[k - 1], *hp[k]) for k in range(n)]


def point_in_convex(p, poly, eps=0.0):
    return all(dot(nrm, p) >= c - eps for nrm, c in halfplanes(poly))


def seg_hits_convex(a, b, poly):
    """True if segment ab meets the closed convex polygon (Cyrus-Beck)."""
    t0, t1 = 0.0, 1.0
    for nrm, c in halfplanes(poly):
        fa = dot(nrm, a) - c
        fb = dot(nrm, b) - c
        if fa < 0.0 and fb < 0.0:
            return False
        if fa >= 0.0 and fb >= 0.0:
            continue
        t = fa / (fa - fb)
        if fa < 0.0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return False
    return True


def clip_halfplane(poly, nrm, c):
    """Sutherland-Hodgman: the part of convex poly with nrm·x >= c."""
    out = []
    n = len(poly)
    for k in range(n):
        p, q = poly[k], poly[(k + 1) % n]
        fp, fq = dot(nrm, p) - c, dot(nrm, q) - c
        if fp >= 0.0:
            out.append(p)
        if (fp >= 0.0) != (fq >= 0.0):
            t = fp / (fp - fq)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return dedupe(out)


def dedupe(poly, tol=1e-12):
    out = []
    for p in poly:
        if not out or dist(p, out[-1]) > tol:
            out.append(p)
    if len(out) > 1 and dist(out[0], out[-1]) <= tol:
        out.pop()
    return out


def bbox_overlap(a, b, tol=EPS):
    return a[0] <= b[2] + tol and b[0] <= a[2] + tol and a[1] <= b[3] + tol and b[1] <= a[3] + tol


def poly_bbox(poly):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return (min(xs), min(ys), max(xs), max(ys))


# --- loops and regions ---

JOINT_TOL = 1e-6
"""Joints closer than this (mm) are welded to one exact point."""


class Loop:
    """A closed loop of Seg/Arc primitives, chained end to start.

    Joints are welded: each primitive starts at exactly the previous one's end point. Point
    containment counts ray crossings half-open in y, which is only consistent when both sides of
    a joint agree on its coordinates to the last bit (issue #5: a circle's seam computed as
    sin 0 on one side and sin 2π on the other lost a row of cells).

    `curved` marks a loop that holds anything other than straight segments (arcs, or curves
    the FreeCAD layer discretised); such loops never snap.
    """

    def __init__(self, prims, curved=None):
        prims = list(prims)
        for k in range(len(prims)):
            end = prims[k - 1].end
            if prims[k].start != end and dist(prims[k].start, end) <= JOINT_TOL:
                prims[k] = prims[k].with_start(end)
        self.prims = prims
        self.curved = any(not isinstance(p, Seg) for p in self.prims) if curved is None else curved
        self._bbox = None

    def signed_area(self):
        return sum(p.area_term() for p in self.prims)

    def reversed(self):
        return Loop([p.reversed() for p in reversed(self.prims)], self.curved)

    def oriented(self, ccw):
        return self if (self.signed_area() > 0) == ccw else self.reversed()

    def bbox(self):
        if self._bbox is None:
            bs = [p.bbox() for p in self.prims]
            self._bbox = (min(b[0] for b in bs), min(b[1] for b in bs),
                          max(b[2] for b in bs), max(b[3] for b in bs))
        return self._bbox

    def contains(self, p):
        b = self.bbox()
        if p[0] < b[0] or p[0] > b[2] or p[1] < b[1] or p[1] > b[3]:
            return False
        return sum(prim.crossings(p) for prim in self.prims) % 2 == 1

    def sample_point(self):
        return self.prims[0].start


class Region:
    """Fields (outer loops, CCW) each minus their keep-outs (holes, CW).

    Built from loops in any orientation by nesting depth: even depth is a field, odd depth a
    keep-out of the loop that immediately contains it.
    """

    def __init__(self, parts):
        self.parts = parts  # list of (outer Loop, [hole Loops])
        self.prims = [p for o, hs in parts for lp in [o] + hs for p in lp.prims]
        self._prim_boxes = [p.bbox() for p in self.prims]

    @classmethod
    def from_loops(cls, loops):
        loops = [lp for lp in loops if abs(lp.signed_area()) > EPS * EPS]
        depth = []
        parent = []
        for i, lp in enumerate(loops):
            q = _interior_probe(lp)
            containers = [j for j, other in enumerate(loops)
                          if j != i and abs(other.signed_area()) > abs(lp.signed_area())
                          and other.contains(q)]
            depth.append(len(containers))
            parent.append(containers)
        parts = {}
        for i, lp in enumerate(loops):
            if depth[i] % 2 == 0:
                parts[i] = (lp.oriented(True), [])
        for i, lp in enumerate(loops):
            if depth[i] % 2 == 1:
                # the smallest field containing it (overlapping keep-outs are not valid
                # sketches, but shouldn't crash)
                fields = [j for j in parent[i] if j in parts]
                if fields:
                    j = min(fields, key=lambda j: abs(loops[j].signed_area()))
                    parts[j][1].append(lp.oriented(False))
        return cls([parts[k] for k in sorted(parts)])

    def contains(self, p):
        for outer, holes in self.parts:
            if outer.contains(p) and not any(h.contains(p) for h in holes):
                return True
        return False

    def bbox(self):
        bs = [o.bbox() for o, _ in self.parts]
        if not bs:
            return None
        return (min(b[0] for b in bs), min(b[1] for b in bs),
                max(b[2] for b in bs), max(b[3] for b in bs))

    def hits(self, poly):
        """Boundary primitives that meet the convex polygon shrunk by EPS (its interior)."""
        sp = shrink(poly)
        box = poly_bbox(sp)
        return [p for p, b in zip(self.prims, self._prim_boxes)
                if bbox_overlap(box, b, 0.0) and p.hits_convex(sp)]

    def classify(self, poly):
        """'in', 'out' or 'cross' for a convex polygon (CCW)."""
        if self.hits(poly):
            return "cross"
        return "in" if self.contains(poly_centroid(poly)) else "out"


def _interior_probe(loop):
    """A point just inside the loop, used to test nesting against other loops."""
    lp = loop.oriented(True)
    p = lp.prims[0]
    if isinstance(p, Seg):
        m = ((p.a[0] + p.b[0]) / 2, (p.a[1] + p.b[1]) / 2)
        d = sub(p.b, p.a)
    else:
        a = p.a0 + p.sweep / 2
        m = p.point(a)
        s = 1.0 if p.sweep > 0 else -1.0
        d = (-math.sin(a) * s, math.cos(a) * s)
    ln = math.hypot(*d)
    off = 1e-4
    return (m[0] - d[1] / ln * off, m[1] + d[0] / ln * off)


# --- unions of polygons that tile without overlap ---

def union_tiles(tiles, tol=1e-9):
    """Outline loops of a union of non-overlapping CCW convex tiles that share edges.

    Returns CCW outer loops and CW holes, collinear vertices removed.
    """
    pts = [p for t in tiles for p in t]

    def key(p):
        return (round(p[0] / tol), round(p[1] / tol))

    edges = {}
    for t in tiles:
        n = len(t)
        for k in range(n):
            a, b = t[k], t[(k + 1) % n]
            d = sub(b, a)
            L2 = dot(d, d)
            inner = []
            for q in pts:
                s = dot(sub(q, a), d) / L2
                if 1e-9 < s < 1 - 1e-9 and abs(cross(d, sub(q, a))) / math.sqrt(L2) < tol * 10:
                    inner.append((s, q))
            chain = [a] + [q for _, q in sorted(inner)] + [b]
            for u, v in zip(chain[:-1], chain[1:]):
                ku, kv = key(u), key(v)
                if ku == kv:
                    continue
                if (kv, ku) in edges:
                    del edges[(kv, ku)]
                else:
                    edges[(ku, kv)] = (u, v)
    nxt = {}
    for (ku, kv), (u, v) in edges.items():
        nxt.setdefault(ku, []).append((kv, u))
    loops = []
    while nxt:
        start = next(iter(nxt))
        loop = []
        k = start
        while True:
            outs = nxt.get(k)
            if not outs:
                break
            kv, u = outs.pop()
            if not outs:
                del nxt[k]
            loop.append(u)
            k = kv
            if k == start:
                break
        if len(loop) >= 3:
            loops.append(_drop_collinear(loop))
    return [lp for lp in loops if len(lp) >= 3]


def _drop_collinear(loop):
    out = []
    n = len(loop)
    for k in range(n):
        a, b, c = loop[k - 1], loop[k], loop[(k + 1) % n]
        if abs(cross(sub(b, a), sub(c, b))) > 1e-12 * (dist(a, b) + dist(b, c)) ** 2:
            out.append(b)
    return out
