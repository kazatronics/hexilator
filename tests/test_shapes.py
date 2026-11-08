# SPDX-License-Identifier: Apache-2.0
"""Cell shapes other than the hexagon (issue #10): square, triangle, circle and polygon."""

import math
import random
import unittest

import FreeCAD as App

import helpers as h
from test_core import near_boundary, on_cell_line, polygon, rect

import freecad.hexilator as hx
from freecad.hexilator.core.clip import plan
from freecad.hexilator.core.geom import Region, halfplanes, poly_area
from freecad.hexilator.core.lattice import (CIRCLE_SIDES, DotLattice, HexLattice,
                                            SquareLattice, TriangleLattice, make_lattice)

S, W = 5.0, 1.2
P = S + W


def counts(p):
    return (p.count("whole"), p.count("exact", "fallback"), p.count("fallback"))


def poly_gap(a, b):
    """Smallest distance between two disjoint convex polygons (vertex to edge, both ways)."""
    def pt_seg(q, u, v):
        dx, dy = v[0] - u[0], v[1] - u[1]
        t = max(0.0, min(1.0, ((q[0] - u[0]) * dx + (q[1] - u[1]) * dy) / (dx * dx + dy * dy)))
        return math.hypot(u[0] + t * dx - q[0], u[1] + t * dy - q[1])

    best = float("inf")
    for p, q in ((a, b), (b, a)):
        for v in p:
            for k in range(len(q)):
                best = min(best, pt_seg(v, q[k], q[(k + 1) % len(q)]))
    return best


TILINGS = (HexLattice(S, W), SquareLattice(S, W), TriangleLattice(S, W))


class TilingLatticeTest(unittest.TestCase):
    def test_lattice_lines_cut_cells_on_chords_only(self):
        """Every lattice line, in every direction (both signs), meets each cell along a chord
        through two vertices, or misses it (touching at most along a side)."""
        for lat in TILINGS:
            cells = [lat.cell(i, j) for i in range(-4, 5) for j in range(-4, 5)]
            for k in range(2 * lat.ndir):
                period, phases = lat.family(k)
                nrm = lat.normal(k)
                for m in range(-4, 5):
                    for ph in phases:
                        c = ph + m * period
                        for cell in cells:
                            d = [nrm[0] * x + nrm[1] * y - c for x, y in cell]
                            if min(d) < -1e-9 and max(d) > 1e-9:
                                self.assertEqual(sum(abs(v) < 1e-9 for v in d), 2,
                                                 "%s: line k=%d c=%g cuts off-chord"
                                                 % (type(lat).__name__, k, c))

    def test_cell_sides_and_chords_are_lattice_lines(self):
        """So a snapped edge never cuts a cell anywhere but along its chords (or, for squares
        and triangles, along its sides, which are lattice lines there; a hexagon's aren't)."""
        for lat in TILINGS:
            for i in range(-2, 3):
                for j in range(-2, 3):
                    key = lat.key(i, j)
                    c = lat.center(i, j)
                    lines = list(lat.chords(key))
                    if not isinstance(lat, HexLattice):
                        lines += halfplanes(lat.outline(key))
                    for nrm, off in lines:
                        k = lat.direction_index(math.atan2(-nrm[0], nrm[1]))  # nrm is the left normal
                        self.assertIsNotNone(k)
                        self.assertTrue(lat.on_line(k, off + nrm[0] * c[0] + nrm[1] * c[1],
                                                    1e-9),
                                        "%s cell (%d,%d): a side or chord is off the lattice"
                                        % (type(lat).__name__, i, j))

    def test_neighbours_are_web_apart(self):
        for lat in TILINGS:
            near = [(i, j) for i in range(-2, 3) for j in range(-2, 3) if (i, j) != (0, 0)]
            gaps = [poly_gap(lat.cell(0, 0), lat.cell(i, j)) for i, j in near]
            self.assertAlmostEqual(min(gaps), W, places=9, msg=type(lat).__name__)

    def test_tiles_cover_cell(self):
        for lat in TILINGS:
            for key in lat.keys():
                self.assertAlmostEqual(sum(poly_area(t) for t in lat.tiles(key)), lat.cell_area,
                                       places=9)

    def test_square_pieces(self):
        lat = SquareLattice(S, W)
        self.assertEqual(len(lat.tiles()), 4)
        kinds = [k for k, _ in lat.candidates()]
        self.assertEqual(kinds, ["whole"] + ["half"] * 4)

    def test_triangle_cells(self):
        lat = TriangleLattice(S, W)
        self.assertEqual(lat.tiles(0), [lat.up])
        self.assertEqual([k for k, _ in lat.candidates(1)], ["whole"])
        self.assertEqual(lat.key(0, 0), 0)
        self.assertEqual(lat.key(1, 0), 1)
        self.assertEqual(lat.key(0, 1), 1)
        self.assertAlmostEqual(lat.cell_area, 3 * math.sqrt(3) * (S / 2) ** 2)
        # the inscribed circle of each cell has diameter S
        for key in (0, 1):
            self.assertAlmostEqual(min(abs(off) for _, off in halfplanes(lat.outline(key))), S / 2)


class WholeBruteForceTest(unittest.TestCase):
    def test_whole_cells_are_exactly_the_cells_inside(self):
        """Whole mode, convex fields: the whole cells are exactly the cells with every vertex
        inside the field (brute force over a wide range of indices)."""
        rng = random.Random(7)
        lats = [("Hexagon", {}), ("Square", {}), ("Triangle", {}),
                ("Polygon", {"grid": "Hexagonal", "sides": 5}),
                ("Polygon", {"grid": "Square", "sides": 8})]
        for shape, kw in lats:
            lat = make_lattice(S, W, shape, kw.get("grid", "Hexagonal"), kw.get("sides", 8))
            for trial in range(6):
                x0, y0 = rng.uniform(-20, 0), rng.uniform(-20, 0)
                x1, y1 = x0 + rng.uniform(15, 45), y0 + rng.uniform(15, 45)
                p = plan([rect(x0, y0, x1, y1)], S, W, "Whole", shape=shape, **kw)
                got = sorted((pc.i, pc.j) for pc in p.pieces)
                expect = sorted((i, j) for i in range(-30, 31) for j in range(-30, 31)
                                if all(x0 - 1e-9 <= x <= x1 + 1e-9 and y0 - 1e-9 <= y <= y1 + 1e-9
                                       for x, y in lat.cell(i, j)))
                self.assertEqual(got, expect, "%s %r trial %d" % (shape, kw, trial))


class DotLatticeTest(unittest.TestCase):
    def test_circle_spacing(self):
        for grid in ("Hexagonal", "Square"):
            lat = DotLattice(S, W, grid)
            c0 = lat.center(0, 0)
            ds = sorted(math.dist(c0, lat.center(i, j))
                        for i in range(-2, 3) for j in range(-2, 3) if (i, j) != (0, 0))
            self.assertAlmostEqual(ds[0], P)  # nearest neighbours: a gap of exactly W
            self.assertAlmostEqual(lat.cell_area, math.pi * (S / 2) ** 2)
            self.assertFalse(lat.snappable)
            self.assertEqual(len(lat.outline()), CIRCLE_SIDES)

    def test_polygon_shape(self):
        lat = DotLattice(S, W, "Square", 8)
        self.assertEqual(len(lat.outline()), 8)
        offs = [off for _, off in halfplanes(lat.outline())]
        for off in offs:
            self.assertAlmostEqual(abs(off), S / 2)  # every flat touches the inscribed circle
        # flats face the square grid's neighbours, so those walls are exactly W
        self.assertAlmostEqual(poly_gap(lat.cell(0, 0), lat.cell(1, 0)), W)
        with self.assertRaises(ValueError):
            DotLattice(S, W, "Square", 2)
        with self.assertRaises(ValueError):
            make_lattice(S, W, "Blob")


class SquarePlanTest(unittest.TestCase):
    a = S / 2

    def test_aligned_field(self):
        # 4 x 3 cells, field edges on the cell sides
        p = plan([rect(-self.a, -self.a, 3 * P + self.a, 2 * P + self.a)], S, W, shape="Square")
        self.assertEqual(counts(p), (12, 0, 0))

    def test_snaps_inward(self):
        # an edge inside column 0 snaps to that column's far side, dropping it
        p = plan([rect(-self.a + 0.3, -self.a - 0.4, 3 * P + self.a + 0.5, 2 * P + self.a)],
                 S, W, shape="Square")
        self.assertEqual(counts(p), (9, 0, 0))
        # an edge in the web snaps onto the side of the next cell in
        p = plan([rect(-self.a - 0.5, -self.a, 3 * P + self.a + 0.5, 2 * P + self.a)],
                 S, W, shape="Square")
        self.assertEqual(counts(p), (12, 0, 0))

    def test_diagonal_edge_halves_cells(self):
        a = self.a
        p = plan([polygon([(-a, -a), (3 * P + a, -a), (3 * P + a, 3 * P + a)])],
                 S, W, shape="Square")
        self.assertEqual(counts(p), (6, 4, 0))
        self.assertAlmostEqual(sum(pc.area for pc in p.pieces), 6 * S * S + 4 * S * S / 2)

    def test_keepout_snaps_out(self):
        a = self.a
        loops = [rect(-a, -a, 5 * P + a, 5 * P + a), rect(2 * P - 0.2, 2 * P - 0.2,
                                                          2 * P + 0.2, 2 * P + 0.2)]
        p = plan(loops, S, W, shape="Square")
        self.assertEqual(counts(p)[0], 35)  # the keep-out snaps out to its cell's sides

    def test_random_fields_obey_the_rule(self):
        rng = random.Random(99)
        lat = SquareLattice(S, W)
        for trial in range(20):
            field = random_polygon(rng, 8, 50)
            drawn = Region.from_loops([field])
            p = plan([field], S, W, shape="Square")
            for pc in p.pieces:
                polys = [lat.cell(pc.i, pc.j)] if pc.kind == "whole" else pc.loops
                for poly in polys:
                    for q in poly:
                        self.assertTrue(drawn.contains(q) or near_boundary(drawn, q),
                                        "trial %d: %r leaves the field" % (trial, pc))
                    for k in range(len(poly)):
                        self.assertTrue(on_cell_line(lat, (pc.i, pc.j), poly[k],
                                                     poly[(k + 1) % len(poly)]),
                                        "trial %d: %r has an off-chord edge" % (trial, pc))


class TrianglePlanTest(unittest.TestCase):
    def setUp(self):
        self.lat = TriangleLattice(S, W)

    def big_triangle(self, grow):
        return big_triangle(self.lat, grow)

    def test_one_cell(self):
        self.assertEqual(counts(plan([self.big_triangle(0.0)], S, W, shape="Triangle")),
                         (1, 0, 0))
        # slightly larger snaps back onto the cell
        self.assertEqual(counts(plan([self.big_triangle(0.4)], S, W, shape="Triangle")),
                         (1, 0, 0))

    def test_larger_triangle_snaps_to_whole_rows(self):
        # each side moved out by one row height Ht = 3·rt: the field's sides are lattice lines
        # again, bounding the tiling triangle of inscribed radius 4·rt, i.e. 4 tiling triangles
        # a side: 16 cells (10 up, 6 down), all whole.
        lat = self.lat
        p = plan([self.big_triangle(lat.Ht)], S, W, shape="Triangle")
        self.assertEqual(counts(p), (16, 0, 0))
        self.assertEqual(sum(lat.key(pc.i, pc.j) for pc in p.pieces), 6)
        # each side moved in by 0.4: horizontal lattice lines come in pairs w apart, one pair
        # per row (Ht), so each side snaps in by nearly a whole row, back to cell (0, 0)
        # alone. Whole keeps more of the drawn field, with a sawtooth edge.
        shrunk = [self.big_triangle(lat.Ht - 0.4)]
        self.assertEqual(counts(plan(shrunk, S, W, shape="Triangle")), (1, 0, 0))
        self.assertGreater(plan(shrunk, S, W, "Whole", shape="Triangle").count("whole"), 1)
        drawn = Region.from_loops([self.big_triangle(lat.Ht)])
        for pc in p.pieces:
            for q in lat.cell(pc.i, pc.j):
                self.assertTrue(drawn.contains(q) or near_boundary(drawn, q))

    def test_rectangle_does_not_snap(self):
        # vertical edges aren't triangle-lattice directions: the field acts as Whole
        loops = [rect(-10, -10, 30, 25)]
        self.assertEqual(counts(plan(loops, S, W, shape="Triangle")),
                         counts(plan(loops, S, W, "Whole", shape="Triangle")))


class DotPlanTest(unittest.TestCase):
    def test_circles_whole_count(self):
        x0, y0, x1, y1 = -11.3, -7.9, 40.6, 31.7
        for grid in ("Hexagonal", "Square"):
            lat = DotLattice(S, W, grid)
            p = plan([rect(x0, y0, x1, y1)], S, W, "Whole", shape="Circle", grid=grid)
            r = S / 2
            expect = 0
            for i, j in lat.cells_in((x0, y0, x1, y1)):
                cx, cy = lat.center(i, j)
                margin = min(cx - x0, x1 - cx, cy - y0, y1 - cy)
                self.assertGreater(abs(margin - r), 0.01, "test field too close to a cell")
                expect += margin > r
            self.assertEqual(counts(p), (expect, 0, 0), grid)
            # Snap means Whole for circles
            self.assertEqual(counts(plan([rect(x0, y0, x1, y1)], S, W, shape="Circle",
                                         grid=grid)), (expect, 0, 0))
            free = plan([rect(x0, y0, x1, y1)], S, W, "Free", shape="Circle", grid=grid)
            self.assertEqual(free.count("whole"), expect)
            self.assertGreater(free.count("free"), 0)

    def test_polygon_whole(self):
        lat = DotLattice(S, W, "Square", 8)
        p = plan([rect(-S / 2, -S / 2, 3 * P + S / 2, 2 * P + S / 2)], S, W, "Whole",
                 shape="Polygon", grid="Square", sides=8)
        self.assertEqual(counts(p), (12, 0, 0))
        self.assertAlmostEqual(sum(pc.area for pc in p.pieces), 12 * lat.cell_area)


def big_triangle(lat, grow):
    """The CCW triangle bounded by cell (0, 0)'s three sides, each moved out by grow."""
    lines = []
    for k in (0, 2, 4):  # base, right side, left side: their left normals point inwards
        nrm = lat.normal(k)
        off = min(nrm[0] * x + nrm[1] * y for x, y in lat.up)
        lines.append((nrm, off - grow))
    pts = []
    for (n1, c1), (n2, c2) in zip(lines[-1:] + lines[:-1], lines):
        det = n1[0] * n2[1] - n1[1] * n2[0]
        pts.append(((c1 * n2[1] - c2 * n1[1]) / det, (n1[0] * c2 - n2[0] * c1) / det))
    return polygon(pts)


def random_polygon(rng, ndirs, size):
    """A convex polygon with edges at multiples of 360°/ndirs, random offsets."""
    while True:
        angles = sorted(rng.sample(range(ndirs), rng.randint(3, ndirs)))
        gaps = [(angles[(k + 1) % len(angles)] - angles[k]) % ndirs for k in range(len(angles))]
        if 2 * max(gaps) < ndirs:
            break
    hp = []
    for k in angles:
        a = k * 2 * math.pi / ndirs + math.pi / 2
        hp.append(((math.cos(a), math.sin(a)), rng.uniform(0.35, 0.5) * size))
    pts = []
    for k in range(len(hp)):
        (n1, c1), (n2, c2) = hp[k - 1], hp[k]
        det = n1[0] * n2[1] - n1[1] * n2[0]
        pts.append(((c1 * n2[1] - c2 * n1[1]) / det, (n1[0] * c2 - n2[0] * c1) / det))
    lp = polygon(pts)
    return lp if lp.signed_area() > 0 else lp.reversed()


class ShapeFeatureTest(unittest.TestCase):
    """The FreeCAD layer: shapes cut what the plan says."""

    def grid(self, sketch_fn, **props):
        doc = h.new_doc("shapes")
        body, box = h.plate(doc, 70, 70, 3.0, x=-30, y=-25)
        sk = h.sketch(body, z=3.0)
        sketch_fn(sk)
        g = hx.make_hex_grid(body, sk, **props)
        doc.recompute()
        self.assertNotIn("Invalid", g.State, g.getStatusString())
        self.assertEqual(len(g.Shape.Solids), 1)
        removed = box.Shape.Volume - g.Shape.Volume
        self.addCleanup(App.closeDocument, doc.Name)
        return g, removed

    def test_square(self):
        a = S / 2
        g, removed = self.grid(lambda sk: h.add_rect(sk, -a, -a, 3 * P + a, 2 * P + a),
                               CellShape="Square", Depth=2.0)
        self.assertEqual((g.WholeCells, g.PartialCells), (12, 0))
        self.assertAlmostEqual(removed, 12 * S * S * 2.0, places=6)
        self.assertAlmostEqual(g.OpenArea.Value, 12 * S * S, places=6)

    def test_triangle(self):
        lat = TriangleLattice(S, W)
        loop = big_triangle(lat, lat.Ht)
        g, removed = self.grid(lambda sk: h.add_polygon(sk, [s.a for s in loop.prims]),
                               CellShape="Triangle", Type="ThroughAll")
        self.assertEqual((g.WholeCells, g.PartialCells), (16, 0))
        self.assertAlmostEqual(removed, 16 * lat.cell_area * 3.0, places=6)

    def test_circle(self):
        g, removed = self.grid(lambda sk: h.add_rect(sk, -8, -8, 40, 30),
                               CellShape="Circle", Lattice="Square", Depth=1.5)
        self.assertGreater(g.WholeCells, 0)
        self.assertEqual(g.PartialCells, 0)
        area = g.WholeCells * math.pi * (S / 2) ** 2
        self.assertAlmostEqual(g.OpenArea.Value, area, places=6)
        self.assertAlmostEqual(removed, area * 1.5, delta=area * 1.5 * 1e-6)

    def test_circle_free(self):
        g, removed = self.grid(lambda sk: h.add_rect(sk, -8, -8, 40, 30),
                               CellShape="Circle", ClipMode="Free", Depth=1.5)
        self.assertGreater(g.PartialCells, 0)
        self.assertAlmostEqual(removed, g.OpenArea.Value * 1.5, delta=1e-6 * removed)

    def test_polygon(self):
        a = S / 2
        g, removed = self.grid(lambda sk: h.add_rect(sk, -a, -a, 3 * P + a, 2 * P + a),
                               CellShape="Polygon", Lattice="Square", Sides=8, Depth=2.0)
        self.assertEqual((g.WholeCells, g.PartialCells), (12, 0))
        lat = DotLattice(S, W, "Square", 8)
        self.assertAlmostEqual(removed, 12 * lat.cell_area * 2.0, places=6)

    def test_defaults_and_editor_modes(self):
        g, _ = self.grid(lambda sk: h.add_rect(sk, *h.ALIGNED))
        self.assertEqual((g.CellShape, g.Lattice, g.Sides), ("Hexagon", "Hexagonal", 8))
        self.assertEqual((g.WholeCells, g.PartialCells), (h.ALIGNED_WHOLE, h.ALIGNED_PARTIAL))
        self.assertIn("Hidden", g.getEditorMode("Sides"))
        self.assertIn("Hidden", g.getEditorMode("Lattice"))
        g.CellShape = "Polygon"
        self.assertNotIn("Hidden", g.getEditorMode("Sides"))
        self.assertNotIn("Hidden", g.getEditorMode("Lattice"))
        g.CellShape = "Circle"
        self.assertIn("Hidden", g.getEditorMode("Sides"))
        with self.assertRaises(Exception):
            g.CellShape = "Blob"
        g.Sides = 2
        self.assertEqual(g.Sides, 3)  # clamped by the constraint

    def test_expression_drives_shape(self):
        g, _ = self.grid(lambda sk: h.add_rect(sk, -S / 2, -S / 2, 3 * P + S / 2, 2 * P + S / 2))
        g.CellShape = "Polygon"
        g.Lattice = "Square"
        g.setExpression("Sides", "2 * 2")
        g.Document.recompute()
        self.assertEqual(g.Sides, 4)
        self.assertEqual(g.WholeCells, 12)


class OldFileTest(unittest.TestCase):
    def test_file_without_shape_properties(self):
        """A file saved before cell shapes (no CellShape, Lattice or Sides) reopens as a
        hexagon grid with the same cut, and gains the properties."""
        import os
        path = os.path.join(os.environ["HEXILATOR_TMP"], "preshapes.FCStd")
        doc = h.new_doc("preshapes")
        body, box = h.plate(doc, 40, 40, 3.0, x=-8, y=-8)
        sk = h.sketch(body, z=3.0)
        h.add_rect(sk, *h.ALIGNED)
        g = hx.make_hex_grid(body, sk)
        doc.recompute()
        vol = g.Shape.Volume
        for name in ("CellShape", "Lattice", "Sides"):
            g.removeProperty(name)
        doc.saveAs(path)
        App.closeDocument(doc.Name)
        out = h.run_freecad("""
            import FreeCAD as App
            d = App.openDocument(%r)
            g = d.getObject("HexGrid")
            out["props"] = [g.CellShape, g.Lattice, g.Sides]
            g.touch()
            d.recompute()
            out["state"] = list(g.State)
            out["vol"] = g.Shape.Volume
            out["cells"] = [g.WholeCells, g.PartialCells]
        """ % path)
        self.assertNotIn("error", out, out.get("error"))
        self.assertEqual(out["props"], ["Hexagon", "Hexagonal", 8])
        self.assertNotIn("Invalid", out["state"])
        self.assertAlmostEqual(out["vol"], vol, places=6)
        self.assertEqual(out["cells"], [h.ALIGNED_WHOLE, h.ALIGNED_PARTIAL])


if __name__ == "__main__":
    unittest.main()
