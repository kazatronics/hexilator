# SPDX-License-Identifier: Apache-2.0
"""Cell lattices in their own frame (see DESIGN.md, Lattice and Cell shapes).

Every lattice has a cell size s (the cell's inscribed-circle diameter) and a web w, the gap
between neighbouring cells. Cell (i, j) has its centre at center(i, j), computed from the
integer indices, never by adding steps.

Tiling lattices (hexagon, square, triangle) have *lattice lines*: lines that cut every cell
they cross along a chord between two of its vertices, and pass through the web of every other
cell. Snap mode moves field edges onto them. Lines run in the directions k·step (k an integer);
family(k) gives their offsets along the left normal of direction k·step.

Dot lattices (circles and regular polygons on a hexagonal or square grid of centres) don't
tile, have no lattice lines, and are never snappable.
"""

import math

from .geom import clip_halfplane, poly_area

SQRT3 = math.sqrt(3.0)
DEG30 = math.pi / 6.0
ANGLE_TOL = 1e-7
"""Direction tolerance (radians) for an edge to count as running along a lattice line."""

CIRCLE_SIDES = 64
"""Circles are tested against their circumscribed 64-gon: conservative by 0.12% of r."""

SHAPES = ("Hexagon", "Square", "Triangle", "Circle", "Polygon")
GRIDS = ("Hexagonal", "Square")


def regular_polygon(r_in, n, flat_bottom=True):
    """CCW vertices of a regular n-gon with inscribed radius r_in, centred at the origin.

    With flat_bottom, one edge is horizontal at y = -r_in (a hexagon is then flat-top, a square
    axis-aligned).
    """
    rc = r_in / math.cos(math.pi / n)
    a0 = -math.pi / 2 + math.pi / n if flat_bottom else 0.0
    return [(rc * math.cos(a0 + 2 * math.pi * k / n), rc * math.sin(a0 + 2 * math.pi * k / n))
            for k in range(n)]


class Lattice:
    """Base class. Subclasses set the geometry; see the module docstring."""

    snappable = False
    round = False
    """True when cells are circles: outline() is then the circumscribed polygon."""
    step = DEG30
    ndir = 6
    """Distinct line directions modulo 180°: directions are k·step for k in range(2·ndir)."""

    def __init__(self, cell, web):
        if cell <= 0:
            raise ValueError("CellSize must be > 0")
        if web <= 0:
            raise ValueError("Web must be > 0")
        self.s = float(cell)
        self.w = float(web)
        self.p = self.s + self.w
        self._cache = {}

    # --- cells ---

    def center(self, i, j):
        raise NotImplementedError

    def key(self, i, j):
        """Which outline cell (i, j) uses (cells differ only by orientation, e.g. triangles)."""
        return 0

    def keys(self):
        return (0,)

    def outline(self, key=0):
        """The cell's polygon (CCW) at the origin."""
        raise NotImplementedError

    def cell(self, i, j):
        cx, cy = self.center(i, j)
        return [(cx + x, cy + y) for x, y in self.outline(self.key(i, j))]

    def radius(self):
        """Distance from a cell's centre to its farthest point."""
        return max(math.hypot(x, y) for k in self.keys() for x, y in self.outline(k))

    def cells_in(self, bbox):
        """(i, j) for every cell whose bounding circle meets bbox (a superset is fine)."""
        raise NotImplementedError

    # --- lattice lines ---

    def direction_index(self, angle):
        """k in range(2·ndir) for an edge direction within ANGLE_TOL of k·step, else None."""
        k = round(angle / self.step)
        if abs(angle - k * self.step) > ANGLE_TOL:
            return None
        return k % (2 * self.ndir)

    def normal(self, k):
        """The left normal of direction k·step."""
        a = k * self.step
        return (-math.sin(a), math.cos(a))

    def _family(self, k):
        """(period, phases) for direction k in range(ndir)."""
        raise NotImplementedError

    def family(self, k):
        """(period, phases) of the lattice-line offsets along normal(k), for any integer k."""
        k %= 2 * self.ndir
        period, phases = self._family(k % self.ndir)
        if k >= self.ndir:  # the opposite direction: its normal is negated
            phases = tuple(-ph for ph in phases)
        return period, phases

    def snap_up(self, k, c, tol):
        """Smallest lattice-line offset >= c - tol for direction k."""
        period, phases = self.family(k)
        return min(ph + period * math.ceil((c - ph - tol) / period) for ph in phases)

    def on_line(self, k, c, tol):
        period, phases = self.family(k)
        for ph in phases:
            m = round((c - ph) / period)
            if abs(ph + m * period - c) <= tol:
                return True
        return False

    # --- one cell's chord arrangement, in cell-local coordinates ---

    def chords(self, key=0):
        """Lines through two non-adjacent vertices of the cell, as (normal, offset)."""
        return []

    def tiles(self, key=0):
        """The convex faces the chords cut the cell into (CCW)."""
        ck = ("tiles", key)
        if ck not in self._cache:
            area = poly_area(self.outline(key))
            faces = [self.outline(key)]
            for nrm, c in self.chords(key):
                nxt = []
                neg = ((-nrm[0], -nrm[1]), -c)
                for f in faces:
                    for part in (clip_halfplane(f, nrm, c), clip_halfplane(f, *neg)):
                        if len(part) >= 3 and poly_area(part) > 1e-12 * area:
                            nxt.append(part)
                faces = nxt
            self._cache[ck] = faces
        return self._cache[ck]

    def candidates(self, key=0):
        """Single-chord pieces of the cell, largest first: (kind, polygon), 'whole' first."""
        ck = ("cand", key)
        if ck not in self._cache:
            outline = self.outline(key)
            area = poly_area(outline)
            pieces = []
            for nrm, c in self.chords(key):
                neg = ((-nrm[0], -nrm[1]), -c)
                for part in (clip_halfplane(outline, nrm, c), clip_halfplane(outline, *neg)):
                    if len(part) >= 3:
                        pieces.append(part)
            pieces.sort(key=lambda q: -poly_area(q))
            self._cache[ck] = [("whole", outline)] + [(self._piece_kind(poly_area(q) / area), q)
                                                      for q in pieces]
        return self._cache[ck]

    @staticmethod
    def _piece_kind(frac):
        for name, f in (("pentagon", 5 / 6), ("half", 0.5), ("triangle", 1 / 6)):
            if abs(frac - f) < 1e-9:
                return name
        return "part"


class HexLattice(Lattice):
    """Flat-top hexagons: vertices at 0°, 60°, … 300°. Cell (i, j) at (i·h, i·p/2 + j·p).

    Long-diagonal lines (even k: 0°, 60°, 120°) lie at offsets m·p/2; short-diagonal lines
    (odd k) at m·h ± R/2.
    """

    snappable = True
    step = DEG30
    ndir = 6

    def __init__(self, cell, web):
        super().__init__(cell, web)
        self.h = self.p * SQRT3 / 2.0
        self.R = self.s / SQRT3
        self.hexagon = [(self.R * math.cos(k * math.pi / 3), self.R * math.sin(k * math.pi / 3))
                        for k in range(6)]
        self.cell_area = SQRT3 / 2.0 * self.s * self.s

    def center(self, i, j):
        return (i * self.h, i * self.p / 2.0 + j * self.p)

    def outline(self, key=0):
        return self.hexagon

    def cells_in(self, bbox):
        x0, y0, x1, y1 = bbox
        for i in range(math.ceil((x0 - self.R) / self.h), math.floor((x1 + self.R) / self.h) + 1):
            base = i * self.p / 2.0
            lo = math.ceil((y0 - self.s / 2.0 - base) / self.p)
            hi = math.floor((y1 + self.s / 2.0 - base) / self.p)
            for j in range(lo, hi + 1):
                yield i, j

    def _family(self, k):
        if k % 2 == 0:
            return self.p / 2.0, (0.0,)
        return self.h, (self.R / 2.0, -self.R / 2.0)

    def chords(self, key=0):
        """The 9 lines through two vertices of the cell (3 long diagonals, 6 short)."""
        out = []
        for k in range(6):
            nrm = self.normal(k)
            if k % 2 == 0:
                out.append((nrm, 0.0))
            else:
                out.append((nrm, self.R / 2.0))
                out.append((nrm, -self.R / 2.0))
        return out


class SquareLattice(Lattice):
    """Axis-aligned squares of side s, cell (i, j) at (i·p, j·p).

    Lines along the cell sides (even k: 0°, 90°) lie at offsets m·p ± s/2; they cut no cell.
    Diagonal lines (odd k: 45°, 135°) run through cell centres, at offsets m·p/√2, halving the
    cells they cross and clearing the others by w/√2.
    """

    snappable = True
    step = math.pi / 4.0
    ndir = 4

    def __init__(self, cell, web):
        super().__init__(cell, web)
        a = self.s / 2.0
        self.square = [(-a, -a), (a, -a), (a, a), (-a, a)]
        self.cell_area = self.s * self.s

    def center(self, i, j):
        return (i * self.p, j * self.p)

    def outline(self, key=0):
        return self.square

    def cells_in(self, bbox):
        x0, y0, x1, y1 = bbox
        a = self.s / 2.0
        for i in range(math.ceil((x0 - a) / self.p), math.floor((x1 + a) / self.p) + 1):
            for j in range(math.ceil((y0 - a) / self.p), math.floor((y1 + a) / self.p) + 1):
                yield i, j

    def _family(self, k):
        if k % 2 == 0:
            return self.p, (self.s / 2.0, -self.s / 2.0)
        return self.p / math.sqrt(2.0), (0.0,)

    def chords(self, key=0):
        return [(self.normal(1), 0.0), (self.normal(3), 0.0)]


class TriangleLattice(Lattice):
    """Equilateral triangles with inscribed radius r = s/2, alternately pointing up and down.

    The cells are the triangles of a tiling with inscribed radius rt = r + w/2 (side
    L = 2√3·rt, row height Ht = 3·rt), each shrunk by w/2, so parallel sides of neighbours are
    w apart. Cell (i, j) is in row j; it points up when i + j is even. Up cell (0, 0) is
    centred on the origin, with its base horizontal at y = -r.

    Lattice lines are the cell sides, at offsets m·Ht + t ± w/2 where t is the tiling line
    (-rt for 0° and 120°, +rt for 60°). They cut no cell: a triangle has no chord between two
    vertices that isn't a side, so triangle cells are only ever cut whole.
    """

    snappable = True
    step = math.pi / 3.0
    ndir = 3

    def __init__(self, cell, web):
        super().__init__(cell, web)
        self.r = self.s / 2.0
        self.rt = self.r + self.w / 2.0
        self.L = 2.0 * SQRT3 * self.rt
        self.Ht = 3.0 * self.rt
        r = self.r
        self.up = [(-SQRT3 * r, -r), (SQRT3 * r, -r), (0.0, 2.0 * r)]
        self.down = [(SQRT3 * r, r), (-SQRT3 * r, r), (0.0, -2.0 * r)]
        self.cell_area = 3.0 * SQRT3 * r * r

    def key(self, i, j):
        return (i + j) % 2  # 0 up, 1 down

    def keys(self):
        return (0, 1)

    def center(self, i, j):
        return (i * self.L / 2.0, j * self.Ht + (self.rt if (i + j) % 2 else 0.0))

    def outline(self, key=0):
        return self.down if key else self.up

    def cells_in(self, bbox):
        x0, y0, x1, y1 = bbox
        rc = 2.0 * self.r
        for j in range(math.ceil((y0 - rc - self.rt) / self.Ht), math.floor((y1 + rc) / self.Ht) + 1):
            for i in range(math.ceil((x0 - rc) / (self.L / 2.0)),
                           math.floor((x1 + rc) / (self.L / 2.0)) + 1):
                yield i, j

    def _family(self, k):
        t = self.rt if k == 1 else -self.rt
        return self.Ht, (t - self.w / 2.0, t + self.w / 2.0)


class DotLattice(Lattice):
    """Circles or regular n-gons centred on a hexagonal or square grid of pitch p = s + w.

    Hexagonal: cell (i, j) at (i·p·√3/2, i·p/2 + j·p), as for hexagons. Square: (i·p, j·p).
    Polygons have a flat at the bottom (normal -y). Not snappable.
    """

    def __init__(self, cell, web, grid="Hexagonal", sides=None):
        super().__init__(cell, web)
        if grid not in GRIDS:
            raise ValueError("Lattice must be one of %s" % ", ".join(GRIDS))
        self.grid = grid
        r = self.s / 2.0
        if sides is None:
            self.round = True
            self.sides = None
            self.poly = regular_polygon(r, CIRCLE_SIDES)
            self.cell_area = math.pi * r * r
        else:
            if sides < 3:
                raise ValueError("Sides must be >= 3")
            self.sides = int(sides)
            self.poly = regular_polygon(r, self.sides)
            self.cell_area = poly_area(self.poly)
        self.rc = max(math.hypot(x, y) for x, y in self.poly)

    def center(self, i, j):
        if self.grid == "Square":
            return (i * self.p, j * self.p)
        return (i * self.p * SQRT3 / 2.0, i * self.p / 2.0 + j * self.p)

    def outline(self, key=0):
        return self.poly

    def cells_in(self, bbox):
        x0, y0, x1, y1 = bbox
        rc = self.rc
        dx = self.p if self.grid == "Square" else self.p * SQRT3 / 2.0
        for i in range(math.ceil((x0 - rc) / dx), math.floor((x1 + rc) / dx) + 1):
            base = 0.0 if self.grid == "Square" else i * self.p / 2.0
            for j in range(math.ceil((y0 - rc - base) / self.p),
                           math.floor((y1 + rc - base) / self.p) + 1):
                yield i, j


def make_lattice(cell, web, shape="Hexagon", grid="Hexagonal", sides=8):
    """The lattice for a cell shape (see SHAPES); grid and sides apply to Circle and Polygon."""
    if shape == "Hexagon":
        return HexLattice(cell, web)
    if shape == "Square":
        return SquareLattice(cell, web)
    if shape == "Triangle":
        return TriangleLattice(cell, web)
    if shape == "Circle":
        return DotLattice(cell, web, grid)
    if shape == "Polygon":
        return DotLattice(cell, web, grid, sides)
    raise ValueError("CellShape must be one of %s" % ", ".join(SHAPES))
