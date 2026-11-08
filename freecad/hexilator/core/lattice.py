# SPDX-License-Identifier: Apache-2.0
"""The hex lattice in its own frame (see DESIGN.md, Lattice).

Flat-top cells: vertices at 0°, 60°, … 300°. Cell (i, j) is centred at (i·h, i·p/2 + j·p).
"""

import math

from .geom import clip_halfplane, poly_area

SQRT3 = math.sqrt(3.0)
DEG30 = math.pi / 6.0
ANGLE_TOL = 1e-7
"""Direction tolerance (radians) for an edge to count as running along a lattice line."""


class Lattice:
    def __init__(self, cell, web):
        if cell <= 0:
            raise ValueError("CellSize must be > 0")
        if web <= 0:
            raise ValueError("Web must be > 0")
        self.s = float(cell)
        self.w = float(web)
        self.p = self.s + self.w
        self.h = self.p * SQRT3 / 2.0
        self.R = self.s / SQRT3
        self.hexagon = [(self.R * math.cos(k * math.pi / 3), self.R * math.sin(k * math.pi / 3))
                        for k in range(6)]
        self.cell_area = SQRT3 / 2.0 * self.s * self.s
        self._chords = None
        self._tiles = None
        self._candidates = None

    def center(self, i, j):
        return (i * self.h, i * self.p / 2.0 + j * self.p)

    def cell(self, i, j):
        cx, cy = self.center(i, j)
        return [(cx + x, cy + y) for x, y in self.hexagon]

    def cells_in(self, bbox):
        """(i, j) for every cell whose bounding box meets bbox."""
        x0, y0, x1, y1 = bbox
        for i in range(math.ceil((x0 - self.R) / self.h), math.floor((x1 + self.R) / self.h) + 1):
            base = i * self.p / 2.0
            lo = math.ceil((y0 - self.s / 2.0 - base) / self.p)
            hi = math.floor((y1 + self.s / 2.0 - base) / self.p)
            for j in range(lo, hi + 1):
                yield i, j

    # --- lattice lines ---

    @staticmethod
    def direction_index(angle):
        """k for an edge direction within ANGLE_TOL of k·30°, else None."""
        k = round(angle / DEG30)
        if abs(angle - k * DEG30) > ANGLE_TOL:
            return None
        return k % 12

    def family(self, k):
        """(period, phases) of the lattice-line offsets along the normal of direction k·30°.

        Even k: long diagonals, offsets m·p/2. Odd k: short diagonals, offsets m·h ± R/2.
        Both sets are symmetric under negation, so either normal sign gives the same set.
        """
        if k % 2 == 0:
            return self.p / 2.0, (0.0,)
        return self.h, (self.R / 2.0, -self.R / 2.0)

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

    def chords(self):
        """The 9 lines through two vertices of the cell at the origin, as (normal, offset)."""
        if self._chords is None:
            out = []
            for k in range(6):
                a = k * DEG30
                nrm = (-math.sin(a), math.cos(a))
                if k % 2 == 0:
                    out.append((nrm, 0.0))
                else:
                    out.append((nrm, self.R / 2.0))
                    out.append((nrm, -self.R / 2.0))
            self._chords = out
        return self._chords

    def tiles(self):
        """The convex faces the 9 chords cut the cell at the origin into (CCW)."""
        if self._tiles is None:
            faces = [self.hexagon]
            for nrm, c in self.chords():
                nxt = []
                neg = ((-nrm[0], -nrm[1]), -c)
                for f in faces:
                    for part in (clip_halfplane(f, nrm, c), clip_halfplane(f, *neg)):
                        if len(part) >= 3 and poly_area(part) > 1e-12 * self.cell_area:
                            nxt.append(part)
                faces = nxt
            self._tiles = faces
        return self._tiles

    def candidates(self):
        """Single-chord pieces of the cell at the origin, largest first: (kind, polygon).

        whole, then 6 pentagons (5/6), 6 halves (1/2), 6 triangles (1/6).
        """
        if self._candidates is None:
            pent, half, tri = [], [], []
            for nrm, c in self.chords():
                neg = ((-nrm[0], -nrm[1]), -c)
                a = clip_halfplane(self.hexagon, nrm, c)
                b = clip_halfplane(self.hexagon, *neg)
                if c == 0.0:
                    half += [a, b]
                else:
                    big, small = (a, b) if poly_area(a) > poly_area(b) else (b, a)
                    pent.append(big)
                    tri.append(small)
            self._candidates = ([("whole", self.hexagon)] + [("pentagon", q) for q in pent]
                                + [("half", q) for q in half] + [("triangle", q) for q in tri])
        return self._candidates
