# SPDX-License-Identifier: Apache-2.0
"""Core tests: lattice, lattice lines, snapping, clipping. No FreeCAD needed."""

import math
import random
import unittest

from helpers import ALIGNED, ALIGNED_AREA, ALIGNED_PARTIAL, ALIGNED_WHOLE, CELL_AREA, H, P, R, S, W

from freecad.hexilator.core.clip import plan, snap_loop
from freecad.hexilator.core.geom import EPS, Arc, Loop, Region, Seg, halfplanes, poly_area
from freecad.hexilator.core.lattice import Lattice


def rect(x0, y0, x1, y1):
    return polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def polygon(pts):
    n = len(pts)
    return Loop([Seg(pts[k], pts[(k + 1) % n]) for k in range(n)])


def circle(cx, cy, r):
    return Loop([Arc((cx, cy), r, 0.0, math.pi), Arc((cx, cy), r, math.pi, math.pi)])


def counts(p):
    return (p.count("whole"), p.count("exact", "fallback"), p.count("fallback"))


def total_area(p):
    return sum(pc.area for pc in p.pieces)


class LatticeTest(unittest.TestCase):
    def setUp(self):
        self.lat = Lattice(S, W)

    def test_dimensions(self):
        self.assertAlmostEqual(self.lat.p, 6.2)
        self.assertAlmostEqual(self.lat.h, 6.2 * math.sqrt(3) / 2)
        self.assertAlmostEqual(self.lat.R, 5 / math.sqrt(3))
        # neighbours across a flat are p apart; across the web, flats are w apart
        a, b = self.lat.center(0, 0), self.lat.center(0, 1)
        self.assertAlmostEqual(b[1] - a[1] - S, W)
        c = self.lat.center(1, 0)
        self.assertAlmostEqual(math.hypot(c[0] - a[0], c[1] - a[1]), P)

    def test_rejects_bad_sizes(self):
        with self.assertRaises(ValueError):
            Lattice(5, 0)
        with self.assertRaises(ValueError):
            Lattice(0, 1)

    def test_tiles_cover_cell(self):
        tiles = self.lat.tiles()
        self.assertEqual(len(tiles), 24)
        self.assertAlmostEqual(sum(poly_area(t) for t in tiles), CELL_AREA, places=9)

    def test_candidates(self):
        kinds = [k for k, _ in self.lat.candidates()]
        self.assertEqual(kinds.count("whole"), 1)
        for k, frac in (("pentagon", 5 / 6), ("half", 0.5), ("triangle", 1 / 6)):
            self.assertEqual(kinds.count(k), 6)
            for kk, poly in self.lat.candidates():
                if kk == k:
                    self.assertAlmostEqual(poly_area(poly) / CELL_AREA, frac, places=9)

    def test_lattice_lines_cut_cells_on_chords_only(self):
        """Every lattice line meets each cell along a chord through two vertices, or misses it
        (touching at most a single point)."""
        lat = self.lat
        cells = [lat.cell(i, j) for i in range(-3, 4) for j in range(-3, 4)]
        for k in range(6):
            period, phases = lat.family(k)
            a = k * math.pi / 6
            nrm = (-math.sin(a), math.cos(a))
            for m in range(-4, 5):
                for ph in phases:
                    c = ph + m * period
                    for cell in cells:
                        d = [nrm[0] * x + nrm[1] * y - c for x, y in cell]
                        on = [abs(v) < 1e-9 for v in d]
                        if min(d) < -1e-9 and max(d) > 1e-9:
                            self.assertEqual(sum(on), 2, "line k=%d c=%g cuts off-chord" % (k, c))

    def test_web_lines_clear_other_columns(self):
        # a short-diagonal line clears the next column by w*sqrt(3)/2
        self.assertAlmostEqual(H - 1.5 * R, W * math.sqrt(3) / 2)


class GeomTest(unittest.TestCase):
    def test_region_nesting(self):
        reg = Region.from_loops([rect(0, 0, 10, 10), rect(2, 2, 8, 8), rect(4, 4, 6, 6)])
        self.assertEqual(len(reg.parts), 2)
        self.assertTrue(reg.contains((1, 1)))
        self.assertFalse(reg.contains((3, 3)))
        self.assertTrue(reg.contains((5, 5)))
        self.assertFalse(reg.contains((11, 5)))

    def test_circle_contains(self):
        reg = Region.from_loops([circle(0, 0, 2)])
        self.assertTrue(reg.contains((0, 0)))
        self.assertTrue(reg.contains((1.9, 0)))
        self.assertTrue(reg.contains((0, -1.99)))
        self.assertFalse(reg.contains((1.5, 1.5)))
        self.assertFalse(reg.contains((0, 2.01)))
        self.assertAlmostEqual(circle(0, 0, 2).signed_area(), 4 * math.pi)

    def test_arc_hits(self):
        arc = Arc((0, 0), 2, 0.0, math.pi / 2)  # quarter in the first quadrant
        self.assertTrue(arc.hits_convex([(1, 1), (3, 1), (3, 3), (1, 3)]))
        self.assertFalse(arc.hits_convex([(-3, -3), (-1, -3), (-1, -1), (-3, -1)]))
        self.assertFalse(arc.hits_convex([(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)]))


class SnapTest(unittest.TestCase):
    def setUp(self):
        self.lat = Lattice(S, W)

    def test_aligned_loop_stays(self):
        lp, why = snap_loop(rect(*ALIGNED), self.lat)
        self.assertIsNone(why)
        xs = sorted({round(p.a[0], 9) for p in lp.prims})
        ys = sorted({round(p.a[1], 9) for p in lp.prims})
        self.assertAlmostEqual(xs[0], ALIGNED[0])
        self.assertAlmostEqual(xs[-1], ALIGNED[2])
        self.assertAlmostEqual(ys[0], ALIGNED[1])
        self.assertAlmostEqual(ys[-1], ALIGNED[3])

    def test_field_shrinks_and_keepout_grows(self):
        x0, y0, x1, y1 = ALIGNED
        lp, _ = snap_loop(rect(x0 - 0.4, y0 - 0.4, x1 + 0.4, y1 + 0.4), self.lat)
        b = lp.bbox()
        for got, want in zip(b, ALIGNED):
            self.assertAlmostEqual(got, want)
        # a keep-out (clockwise: region outside) grows onto the next lines out
        hole = rect(10.0, 10.0, 12.0, 11.0).oriented(False)
        lp, _ = snap_loop(hole, self.lat)
        b = lp.bbox()
        self.assertLessEqual(b[0], 10.0)
        self.assertGreaterEqual(b[2], 12.0)
        self.assertAlmostEqual(b[1], 9.3)
        self.assertAlmostEqual(b[3], 12.4)

    def test_unsnappable(self):
        self.assertEqual(snap_loop(circle(0, 0, 3), self.lat)[1], "has curves")
        tilted = polygon([(0, 0), (10, 1), (9, 11), (-1, 10)])
        self.assertEqual(snap_loop(tilted, self.lat)[1], "edge off the lattice directions")

    def test_step_that_snaps_away(self):
        """Issue #1: a step between two edges that snap onto one lattice line vanishes; the
        loop still snaps, to the same shape as without the step."""
        stepped = polygon([(-6, 0), (6, 0), (6, 8), (-6.3, 8), (-6.3, 4), (-6, 4)])
        lp, why = snap_loop(stepped.oriented(False), self.lat)
        self.assertIsNone(why)
        self.assertEqual(len(lp.prims), 4)
        plain, _ = snap_loop(rect(-6.3, 0, 6, 8).oriented(False), self.lat)
        for got, want in zip(lp.bbox(), plain.bbox()):
            self.assertAlmostEqual(got, want)

    def test_collapse(self):
        # narrower than any pair of lattice lines across the columns: collapses
        self.assertIsNotNone(snap_loop(rect(0.5, 0.5, 20, 2.5), self.lat)[1])


class PlanTest(unittest.TestCase):
    def test_aligned_field(self):
        p = plan([rect(*ALIGNED)], S, W)
        self.assertEqual(counts(p), (ALIGNED_WHOLE, ALIGNED_PARTIAL, 0))
        self.assertAlmostEqual(total_area(p), ALIGNED_AREA, places=6)

    def test_snap_inward_matches_aligned(self):
        x0, y0, x1, y1 = ALIGNED
        p = plan([rect(x0 - 0.5, y0 - 0.5, x1 + 0.5, y1 + 0.5)], S, W)
        self.assertEqual(counts(p), (ALIGNED_WHOLE, ALIGNED_PARTIAL, 0))
        self.assertAlmostEqual(total_area(p), ALIGNED_AREA, places=6)

    def test_stepped_keepout_matches_rectangle(self):
        """Issue #1, as reported: a stepped keep-out that snaps to the same region as a
        rectangle gives the same plan, with no fallback cells and no warning."""
        field = rect(-30, -20, 30, 20)
        stepped = plan([field, polygon([(-6, 0), (6, 0), (6, 8), (-6.3, 8), (-6.3, 4),
                                        (-6, 4)])], S, W)
        plain = plan([field, rect(-6.3, 0, 6, 8)], S, W)
        self.assertEqual(stepped.warnings, [])
        self.assertEqual(counts(stepped), counts(plain))
        self.assertEqual(counts(plain), (43, 27, 0))
        self.assertAlmostEqual(total_area(stepped), total_area(plain), places=9)

    def test_stepped_field_edge(self):
        """The same on a field's outer loop: the step at x = 0..0.2 snaps away inwards."""
        stepped = plan([polygon([(0, 0), (40, 0), (40, 30), (0.2, 30), (0.2, 15), (0, 15)])],
                       S, W)
        plain = plan([rect(0, 0, 40, 30)], S, W)
        self.assertEqual(stepped.warnings, [])
        self.assertEqual(counts(stepped), counts(plain))
        self.assertAlmostEqual(total_area(stepped), total_area(plain), places=9)

    def test_whole_mode(self):
        p = plan([rect(*ALIGNED)], S, W, "Whole")
        self.assertEqual(counts(p), (ALIGNED_WHOLE, 0, 0))

    def test_free_mode_marks_edge_cells(self):
        p = plan([rect(*ALIGNED)], S, W, "Free")
        self.assertEqual(p.count("whole"), ALIGNED_WHOLE)
        self.assertGreaterEqual(p.count("free"), ALIGNED_PARTIAL)

    def test_round_keepout_falls_back(self):
        p = plan([rect(-20, -20, 40, 40), circle(10, 10, 6)], S, W)
        self.assertGreater(p.count("fallback"), 0)
        for pc in p.pieces:
            if pc.kind == "fallback":
                self.assertTrue(any(abs(pc.area / CELL_AREA - f) < 1e-9
                                    for f in (5 / 6, 0.5, 1 / 6)))

    def test_bad_mode(self):
        with self.assertRaises(ValueError):
            plan([rect(0, 0, 10, 10)], S, W, "Bogus")

    def test_pieces_obey_the_rule(self):
        """Random fields: every piece lies inside the field as drawn, outside keep-outs, and
        each of its edges lies on its cell's boundary or on a vertex-to-vertex line."""
        rng = random.Random(1234)
        lat = Lattice(S, W)
        for trial in range(25):
            loops = [random_lattice_polygon(rng, 0, 0, 60, 3)]
            # keep-outs in separate quadrants, so they never overlap
            for qx, qy in rng.sample([(-14, -14), (2, -14), (-14, 2), (2, 2)], rng.randint(0, 2)):
                if rng.random() < 0.5:
                    loops.append(rect(*sorted_box(rng, qx, qy, qx + 2, qy + 2, 3, 10)))
                else:
                    loops.append(circle(qx + 6, qy + 6, rng.uniform(1.5, 5.5)))
            drawn = Region.from_loops(loops)
            p = plan(loops, S, W)
            for pc in p.pieces:
                c = lat.center(pc.i, pc.j)
                polys = [lat.cell(pc.i, pc.j)] if pc.kind == "whole" else pc.loops
                for poly in polys:
                    for q in poly:
                        self.assertTrue(drawn.contains(q) or near_boundary(drawn, q),
                                        "trial %d: piece %r leaves the field" % (trial, pc))
                    for k in range(len(poly)):
                        a, b = poly[k], poly[(k + 1) % len(poly)]
                        self.assertTrue(on_cell_line(lat, c, a, b),
                                        "trial %d: %r has an off-chord edge" % (trial, pc))


def sorted_box(rng, xa, ya, xb, yb, smin, smax):
    x0 = rng.uniform(xa, xb)
    y0 = rng.uniform(ya, yb)
    return (x0, y0, x0 + rng.uniform(smin, smax), y0 + rng.uniform(smin, smax))


def random_lattice_polygon(rng, cx, cy, size, _):
    """A convex hexagon-ish polygon with edges at multiples of 30°, offsets random."""
    while True:  # consecutive edge directions must turn by less than 180°
        angles = sorted(rng.sample(range(12), rng.randint(4, 6)))
        gaps = [(angles[(k + 1) % len(angles)] - angles[k]) % 12 for k in range(len(angles))]
        if max(gaps) < 6:
            break
    import math as m
    hp = []
    for k in angles:
        a = k * m.pi / 6 + m.pi / 2  # outward normal of an edge running at k*30°
        hp.append(((m.cos(a), m.sin(a)), rng.uniform(0.35, 0.5) * size))
    pts = []
    n = len(hp)
    for k in range(n):
        (n1, c1), (n2, c2) = hp[k - 1], hp[k]
        det = n1[0] * n2[1] - n1[1] * n2[0]
        pts.append(((c1 * n2[1] - c2 * n1[1]) / det + cx, (n1[0] * c2 - n2[0] * c1) / det + cy))
    lp = polygon(pts)
    return lp if lp.signed_area() > 0 else lp.reversed()


def near_boundary(region, q, tol=1e-6):
    for p in region.prims:
        if isinstance(p, Seg):
            (ax, ay), (bx, by) = p.a, p.b
            dx, dy = bx - ax, by - ay
            t = max(0.0, min(1.0, ((q[0] - ax) * dx + (q[1] - ay) * dy) / (dx * dx + dy * dy)))
            if math.hypot(ax + t * dx - q[0], ay + t * dy - q[1]) < tol:
                return True
        else:
            if abs(math.hypot(q[0] - p.c[0], q[1] - p.c[1]) - p.r) < tol:
                return True
    return False


def on_cell_line(lat, c, a, b):
    la = (a[0] - c[0], a[1] - c[1])
    lb = (b[0] - c[0], b[1] - c[1])
    lines = list(lat.chords()) + halfplanes(lat.hexagon)
    for nrm, off in lines:
        if abs(nrm[0] * la[0] + nrm[1] * la[1] - off) < 1e-6 and \
                abs(nrm[0] * lb[0] + nrm[1] * lb[1] - off) < 1e-6:
            return True
    return False


if __name__ == "__main__":
    unittest.main()
