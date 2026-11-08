# SPDX-License-Identifier: Apache-2.0
"""HexGridPad feature tests (issue #14), under freecadcmd."""

import math
import os
import time
import unittest

import FreeCAD as App

import helpers as h
from helpers import ALIGNED, ALIGNED_AREA, ALIGNED_PARTIAL, ALIGNED_WHOLE

import freecad.hexilator as hx

T = 3.0  # plate thickness
HT = 2.0  # pad height
FIELD = (ALIGNED[2] - ALIGNED[0]) * (ALIGNED[3] - ALIGNED[1])  # the aligned field's area
# a field off the lattice, with a keep-out, for the shape and border tests
OFF = (0.0, 0.0, 26.0, 26.0)
KEEPOUT = (13.0, 13.0, 3.0)


class PadTest(unittest.TestCase):
    def setUp(self):
        self.doc = h.new_doc("pad")
        self.body, self.box = h.plate(self.doc, 50, 50, T, x=-8, y=-8)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def pad(self, rect=ALIGNED, z=T, keepout=None, body=None, **props):
        body = body or self.body
        self.sk = h.sketch(body, z=z, name="Field")
        h.add_rect(self.sk, *rect)
        if keepout:
            h.add_circle(self.sk, *keepout)
        g = hx.make_hex_grid_pad(body, self.sk, **props)
        self.doc.recompute()
        return g

    def assertGood(self, g):
        self.assertNotIn("Invalid", g.State, g.State)
        self.assertTrue(g.Shape.isValid())
        self.assertEqual(len(g.Shape.Solids), 1)

    def added(self, g):
        return g.Shape.Volume - self.box.Shape.Volume

    # --- volumes ---

    def test_defaults(self):
        g = self.pad()
        self.assertGood(g)
        self.assertEqual(g.TypeId, "PartDesign::FeatureAdditivePython")
        self.assertEqual((g.Mode, g.Height.Value, g.Border.Value, g.Reversed),
                         ("Walls", 2.0, 0.0, False))
        self.assertEqual(g.Version, hx.__version__)
        self.assertIs(self.body.Tip, g)

    def test_same_lattice_inputs_as_hexgrid(self):
        """Same names, defaults and meanings, so a pad and a pocket grid can share a lattice."""
        from freecad.hexilator.feature import LATTICE_INPUTS
        g = self.pad()
        sk = h.sketch(self.body, z=T, name="Other")
        h.add_rect(sk, *ALIGNED)
        c = hx.make_hex_grid(self.body, sk)
        for typ, name, default, _doc in LATTICE_INPUTS:
            self.assertEqual(g.getTypeIdOfProperty(name), typ, name)
            if name != "Profile":
                self.assertEqual(getattr(g, name), getattr(c, name), name)

    def test_walls_volume(self):
        g = self.pad()
        self.assertGood(g)
        self.assertEqual((g.WholeCells, g.PartialCells, g.FallbackCells),
                         (ALIGNED_WHOLE, ALIGNED_PARTIAL, 0))
        self.assertAlmostEqual(g.OpenArea.Value, ALIGNED_AREA, places=6)
        self.assertAlmostEqual(self.added(g), (FIELD - ALIGNED_AREA) * HT, places=4)
        self.assertAlmostEqual(g.AddSubShape.Volume, (FIELD - ALIGNED_AREA) * HT, places=4)
        bb = g.Shape.BoundBox
        self.assertAlmostEqual(bb.ZMax, T + HT, places=9)
        # the web above the cell at (1, 0) is a wall; the cell itself is bare plate
        cx, cy = h.H, h.P / 2
        self.assertTrue(g.Shape.isInside(App.Vector(cx, cy + h.P / 2, T + HT / 2),
                                         1e-6, True))
        self.assertFalse(g.Shape.isInside(App.Vector(cx, cy, T + HT / 2), 1e-6, True))

    def test_cells_volume(self):
        g = self.pad(Mode="Cells")
        self.assertGood(g)
        self.assertEqual((g.WholeCells, g.PartialCells), (ALIGNED_WHOLE, ALIGNED_PARTIAL))
        self.assertAlmostEqual(self.added(g), g.OpenArea.Value * HT, places=4)
        self.assertAlmostEqual(self.added(g), ALIGNED_AREA * HT, places=4)
        # a boss at the centre of cell (1, 0); the web above it is bare plate
        cx, cy = h.H, h.P / 2
        self.assertTrue(g.Shape.isInside(App.Vector(cx, cy, T + HT / 2), 1e-6, True))
        self.assertFalse(g.Shape.isInside(App.Vector(cx, cy + h.P / 2, T + HT / 2),
                                          1e-6, True))

    def test_walls_and_cells_cover_the_field(self):
        w = self.pad(Mode="Walls")
        w_vol = self.added(w)
        w.Mode = "Cells"
        self.doc.recompute()
        self.assertAlmostEqual(w_vol + self.added(w), FIELD * HT, places=4)

    def test_height(self):
        g = self.pad(Height=3.5)
        self.assertGood(g)
        self.assertAlmostEqual(self.added(g), (FIELD - ALIGNED_AREA) * 3.5, places=4)
        self.assertAlmostEqual(g.Shape.BoundBox.ZMax, T + 3.5, places=9)

    def test_off_lattice_field_snaps_inward(self):
        x0, y0, x1, y1 = ALIGNED
        g = self.pad(rect=(x0 - 0.45, y0 - 0.45, x1 + 0.45, y1 + 0.45), Mode="Cells")
        self.assertGood(g)
        self.assertEqual((g.WholeCells, g.PartialCells), (ALIGNED_WHOLE, ALIGNED_PARTIAL))
        self.assertAlmostEqual(self.added(g), ALIGNED_AREA * HT, places=4)
        # the walls keep the strip between the snapped and the drawn edge: field minus cells
        g.Mode = "Walls"
        self.doc.recompute()
        self.assertGood(g)
        area = (x1 - x0 + 0.9) * (y1 - y0 + 0.9)
        self.assertAlmostEqual(self.added(g), (area - ALIGNED_AREA) * HT, places=4)

    def test_keepout_is_not_padded_and_cells_stay_out(self):
        g = self.pad(rect=OFF, keepout=KEEPOUT, Mode="Walls", ClipMode="Free")
        self.assertGood(g)
        region = 26.0 * 26.0 - math.pi * 9.0
        self.assertAlmostEqual(self.added(g), (region - g.OpenArea.Value) * HT, places=3)
        self.assertFalse(g.Shape.isInside(App.Vector(13, 13, T + HT / 2), 1e-6, True))

    # --- every cell shape ---

    def test_every_shape(self):
        region = 26.0 * 26.0 - math.pi * 9.0
        for shape in ("Hexagon", "Square", "Triangle", "Circle", "Polygon"):
            for clip in ("Snap", "Free"):
                with self.subTest(shape=shape, clip=clip):
                    g = self.pad(rect=OFF, keepout=KEEPOUT, CellShape=shape, ClipMode=clip,
                                 Mode="Walls")
                    self.assertGood(g)
                    self.assertGreater(g.WholeCells, 0)
                    walls = self.added(g)
                    g.Mode = "Cells"
                    self.doc.recompute()
                    self.assertGood(g)
                    cells = self.added(g)
                    tol = 2e-3 if shape == "Circle" else 1e-6  # circles: a 64-gon's area
                    self.assertAlmostEqual(cells, g.OpenArea.Value * HT,
                                           delta=tol * g.OpenArea.Value * HT + 1e-6)
                    self.assertAlmostEqual(walls + cells, region * HT, places=3)
                    self.doc.removeObject(g.Name)
                    self.doc.removeObject(self.sk.Name)
                    self.doc.recompute()

    # --- border ---

    def free_open_area(self, rects, circles=(), x=0.0):
        """Area of the lattice's cells inside a field, by a HexGrid in Free mode in a body of
        its own: an independent measure."""
        body, _ = h.plate(self.doc, 50, 50, T, x=-8, y=-8, name="Ref%d" % len(self.doc.Objects))
        sk = h.sketch(body, z=T, name="RefField")
        for r in rects:
            h.add_rect(sk, *r)
        for c in circles:
            h.add_circle(sk, *c)
        g = hx.make_hex_grid(body, sk, ClipMode="Free")
        self.doc.recompute()
        self.assertNotIn("Invalid", g.State, g.State)
        return g.OpenArea.Value

    def test_border_adds_a_rib_along_the_outline(self):
        b = 1.0
        g0 = self.pad(rect=OFF, ClipMode="Free")
        base = self.added(g0)
        g0.Border = b
        self.doc.recompute()
        self.assertGood(g0)
        # walls = field - (cells inside the rib's inner edge)
        inner = (OFF[0] + b, OFF[1] + b, OFF[2] - b, OFF[3] - b)
        expected = (26.0 * 26.0 - self.free_open_area([inner])) * HT
        self.assertAlmostEqual(self.added(g0), expected, places=3)
        self.assertGreater(self.added(g0), base + 1.0)
        # OpenArea still counts the planned cells; the rib isn't subtracted from it
        self.assertAlmostEqual(g0.OpenArea.Value, self.free_open_area([OFF]), places=6)
        # along the outline, every point 0.5 inside the edge is solid
        for t in (3.1, 7.7, 12.2, 19.4, 24.9):
            for x, y in ((t, 0.5), (t, 25.5), (0.5, t), (25.5, t)):
                self.assertTrue(g0.Shape.isInside(App.Vector(x, y, T + HT / 2), 1e-6, True),
                                (x, y))

    def test_border_without_border_cells_reach_the_edge(self):
        g = self.pad(rect=OFF, ClipMode="Free")
        solid = 0
        for t in [1.0 + 0.7 * k for k in range(35)]:
            solid += g.Shape.isInside(App.Vector(t, 0.5, T + HT / 2), 1e-6, True)
        self.assertLess(solid, 35)  # some of the edge is cell opening

    def test_border_rings_a_keepout(self):
        b = 1.0
        g = self.pad(rect=OFF, keepout=KEEPOUT, ClipMode="Free", Border=b)
        self.assertGood(g)
        for k in range(24):
            a = 2 * math.pi * k / 24
            r = 3.0 + b / 2
            p = App.Vector(13 + r * math.cos(a), 13 + r * math.sin(a), T + HT / 2)
            self.assertTrue(g.Shape.isInside(p, 1e-6, True), "no rib at %d deg" % (k * 15))
        # the same ring without a border has gaps (cell openings touch the keep-out)
        g.Border = 0.0
        self.doc.recompute()
        solid = 0
        for k in range(48):
            a = 2 * math.pi * k / 48
            p = App.Vector(13 + 3.2 * math.cos(a), 13 + 3.2 * math.sin(a), T + HT / 2)
            solid += g.Shape.isInside(p, 1e-6, True)
        self.assertLess(solid, 48)

    def test_border_on_arcs_and_holes(self):
        """The OCC offset of a face with a hole is wrong; each loop is offset by itself."""
        b = 1.0
        sk = h.sketch(self.body, z=T, name="Round")
        h.add_circle(sk, 12.0, 12.0, 11.0)
        h.add_circle(sk, 12.0, 12.0, 4.0)
        g = hx.make_hex_grid_pad(self.body, sk, ClipMode="Free", Border=b)
        self.doc.recompute()
        self.assertGood(g)
        annulus = math.pi * (11.0 ** 2 - 4.0 ** 2)
        inner = self.free_open_area([], [(12.0, 12.0, 10.0)]) - \
            self.free_open_area([], [(12.0, 12.0, 5.0)])
        self.assertAlmostEqual(self.added(g), (annulus - inner) * HT, places=2)

    def test_border_larger_than_the_field(self):
        g = self.pad(rect=OFF, ClipMode="Free", Border=20.0)
        self.assertGood(g)  # the whole field is rib
        self.assertAlmostEqual(self.added(g), 26.0 * 26.0 * HT, places=3)

    def test_border_does_nothing_in_cells_mode(self):
        g = self.pad(Mode="Cells", Border=1.0)
        self.assertGood(g)
        self.assertAlmostEqual(self.added(g), ALIGNED_AREA * HT, places=4)

    # --- direction ---

    def test_reversed(self):
        """False pads along the sketch normal, True against it, as Pad does."""
        g = self.pad(z=T)  # on the plate's top face, normal +z
        self.assertAlmostEqual(g.Shape.BoundBox.ZMax, T + HT, places=9)
        self.assertAlmostEqual(self.added(g), (FIELD - ALIGNED_AREA) * HT, places=4)
        g.Reversed = True  # into the plate: nothing added
        self.doc.recompute()
        self.assertGood(g)
        self.assertAlmostEqual(self.added(g), 0.0, places=4)
        self.assertAlmostEqual(g.Shape.BoundBox.ZMax, T, places=9)
        # from the plate's bottom face, away from it
        self.sk.Placement = App.Placement()
        self.doc.recompute()
        self.assertGood(g)
        self.assertAlmostEqual(g.Shape.BoundBox.ZMin, -HT, places=9)
        self.assertAlmostEqual(self.added(g), (FIELD - ALIGNED_AREA) * HT, places=4)
        g.Reversed = False
        self.doc.recompute()
        self.assertAlmostEqual(self.added(g), 0.0, places=4)

    def test_reversed_with_a_flipped_sketch(self):
        body, box = h.plate(self.doc, 50, 50, T, x=-8, y=-42, name="Flipped")
        rot = App.Rotation(App.Vector(1, 0, 0), 180)  # sketch normal = -z, y mirrored
        sk = h.sketch(body, z=0, rot=rot, name="Under")
        h.add_rect(sk, *ALIGNED)
        g = hx.make_hex_grid_pad(body, sk, Mode="Cells")  # along -z, away from the plate
        self.doc.recompute()
        self.assertGood(g)
        self.assertAlmostEqual(g.Shape.BoundBox.ZMin, -HT, places=9)
        self.assertAlmostEqual(g.Shape.Volume - box.Shape.Volume, ALIGNED_AREA * HT, places=4)
        g.Reversed = True  # into the plate
        self.doc.recompute()
        self.assertGood(g)
        self.assertAlmostEqual(g.Shape.Volume - box.Shape.Volume, 0.0, places=4)

    def test_sketch_on_other_plane(self):
        body, box = h.plate(self.doc, 40, 3, 40, x=-8, y=0, name="Wall")
        rot = App.Rotation(App.Vector(1, 0, 0), 90)  # sketch normal = -y
        sk = h.sketch(body, z=0, rot=rot, name="WallField")
        sk.Placement = App.Placement(App.Vector(0, 0, 8), rot)
        h.add_rect(sk, *ALIGNED)
        g = hx.make_hex_grid_pad(body, sk, Mode="Cells")  # along the normal, -y: off the wall
        self.doc.recompute()
        self.assertGood(g)
        self.assertAlmostEqual(g.Shape.BoundBox.YMin, -HT, places=9)
        self.assertAlmostEqual(g.Shape.Volume - box.Shape.Volume, ALIGNED_AREA * HT, places=4)

    def test_body_placement(self):
        self.body.Placement = App.Placement(App.Vector(100, 50, 20), App.Rotation(30, 10, 5))
        g = self.pad(Mode="Cells")
        self.assertGood(g)
        self.assertAlmostEqual(self.added(g), ALIGNED_AREA * HT, places=4)

    # --- one solid ---

    def test_walls_and_cells_fuse_onto_the_plate(self):
        for mode in ("Walls", "Cells"):
            g = self.pad(Mode=mode)
            self.assertGood(g)
            self.assertAlmostEqual(g.Shape.BoundBox.ZMin, 0.0, places=9)
            self.assertAlmostEqual(g.Shape.BoundBox.ZMax, T + HT, places=9)
            self.doc.removeObject(g.Name)
            self.doc.recompute()

    def test_refine_merges_the_plate_top(self):
        g = self.pad(Mode="Cells")
        n = len(g.Shape.Faces)
        g.Refine = False
        self.doc.recompute()
        self.assertGood(g)
        self.assertGreaterEqual(len(g.Shape.Faces), n)

    def test_disjoint_cells_are_an_error(self):
        # bosses floating above the plate, touching nothing
        g = self.pad(z=T + 5.0, Mode="Cells")
        self.assertIn("Invalid", g.State)
        self.assertIn("solids", g.getStatusString())

    def test_cells_with_no_base_are_an_error(self):
        doc = h.new_doc("nobase")
        try:
            body = doc.addObject("PartDesign::Body", "Body")
            sk = h.sketch(body, z=T)
            h.add_rect(sk, *ALIGNED)
            g = hx.make_hex_grid_pad(body, sk, Mode="Cells")
            doc.recompute()
            self.assertIn("Invalid", g.State)
            self.assertIn("solids", g.getStatusString())
        finally:
            App.closeDocument(doc.Name)

    def test_walls_with_no_base_are_the_shape(self):
        doc = h.new_doc("nobase")
        try:
            body = doc.addObject("PartDesign::Body", "Body")
            sk = h.sketch(body, z=T)
            h.add_rect(sk, *ALIGNED)
            g = hx.make_hex_grid_pad(body, sk)
            doc.recompute()
            self.assertGood(g)
            self.assertAlmostEqual(g.Shape.Volume, (FIELD - ALIGNED_AREA) * HT, places=4)
            bb = g.Shape.BoundBox
            self.assertAlmostEqual(bb.ZMin, T, places=9)
            self.assertAlmostEqual(bb.ZMax, T + HT, places=9)
            self.assertAlmostEqual(bb.XMin, ALIGNED[0], places=6)
            self.assertAlmostEqual(bb.YMax, ALIGNED[3], places=6)
        finally:
            App.closeDocument(doc.Name)

    def test_a_single_cell_with_no_base(self):
        doc = h.new_doc("onecell")
        try:
            body = doc.addObject("PartDesign::Body", "Body")
            sk = h.sketch(body, z=0)
            h.add_rect(sk, -3.1, -2.6, 3.1, 2.6)
            g = hx.make_hex_grid_pad(body, sk, Mode="Cells", ClipMode="Whole")
            doc.recompute()
            self.assertGood(g)
            self.assertEqual(g.WholeCells, 1)
            self.assertAlmostEqual(g.Shape.Volume, h.CELL_AREA * HT, places=6)
        finally:
            App.closeDocument(doc.Name)

    def test_errors(self):
        g = self.pad(Height=0.0)
        self.assertIn("Invalid", g.State)
        g.Height = 2.0
        g.setExpression("Border", "-1 mm")  # the property itself won't take a negative value
        self.doc.recompute()
        self.assertIn("Invalid", g.State)
        g.setExpression("Border", None)
        g.Border = 0.0
        g.Web = 0.0
        self.doc.recompute()
        self.assertIn("Invalid", g.State)
        g.Web = 1.2
        self.doc.recompute()
        self.assertGood(g)

    def test_no_cells_in_cells_mode(self):
        g = self.pad(rect=(0, 0, 3, 3), Mode="Cells", ClipMode="Whole")
        self.assertIn("Invalid", g.State)

    # --- expressions, visibility, editor modes ---

    def test_expressions(self):
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Params")
        for cell, alias, val in (("A1", "Cell", "5 mm"), ("A2", "Web", "1.2 mm"),
                                 ("A3", "Rib", "0.5 mm"), ("A4", "Up", "2 mm")):
            sheet.set(cell, val)
            sheet.setAlias(cell, alias)
        self.doc.recompute()
        g = self.pad(rect=OFF, ClipMode="Free")
        g.setExpression("CellSize", "Params.Cell")
        g.setExpression("Web", "Params.Web")
        g.setExpression("Height", "Params.Up * 2")
        g.setExpression("Border", "Params.Rib")
        self.doc.recompute()
        self.assertGood(g)
        self.assertAlmostEqual(g.Height.Value, 4.0)
        self.assertAlmostEqual(g.Border.Value, 0.5)
        v = self.added(g)
        sheet.set("A4", "1 mm")
        sheet.set("A1", "4 mm")
        self.doc.recompute()
        self.assertGood(g)
        self.assertAlmostEqual(g.Height.Value, 2.0)
        self.assertAlmostEqual(g.CellSize.Value, 4.0)
        self.assertNotAlmostEqual(self.added(g), v, places=2)
        self.assertAlmostEqual(g.Shape.BoundBox.ZMax, T + 2.0, places=9)

    def test_visibility(self):
        g = self.pad()
        self.assertFalse(self.box.Visibility)
        self.assertFalse(self.sk.Visibility)
        self.assertTrue(g.Visibility)

    def test_editor_modes(self):
        g = self.pad()
        self.assertEqual(g.getEditorMode("Border"), [])
        self.assertIn("Hidden", g.getEditorMode("Lattice"))
        g.Mode = "Cells"
        self.assertIn("Hidden", g.getEditorMode("Border"))
        g.CellShape = "Circle"
        self.assertEqual(g.getEditorMode("Lattice"), [])

    # --- with a HexGrid ---

    def test_pad_and_pocket_are_complementary(self):
        """A pad and a HexGrid with the same lattice parameters and field cut and raise the
        same cells; the walls are what's left of the field."""
        params = dict(CellSize=4.5, Web=1.0, Angle=10.0, AnchorX=1.3, AnchorY=-0.4,
                      ClipMode="Free")
        pocket_body, _ = h.plate(self.doc, 50, 50, T, x=-8, y=-8, name="Pocket")
        psk = h.sketch(pocket_body, z=T, name="PocketField")
        h.add_rect(psk, *OFF)
        pocket = hx.make_hex_grid(pocket_body, psk, Depth=HT, **params)
        cells = self.pad(rect=OFF, Mode="Cells", **params)
        self.doc.recompute()
        self.assertGood(cells)
        self.assertNotIn("Invalid", pocket.State)
        self.assertEqual((cells.WholeCells, cells.PartialCells, round(cells.OpenArea.Value, 6)),
                         (pocket.WholeCells, pocket.PartialCells,
                          round(pocket.OpenArea.Value, 6)))
        cut = pocket.AddSubShape.copy()
        cut.translate(App.Vector(0, 0, HT))  # the cut went down from the sketch; raise it
        boss = cells.AddSubShape
        self.assertLess(cut.cut(boss).Volume, 1e-6)
        self.assertLess(boss.cut(cut).Volume, 1e-6)
        cells.Mode = "Walls"
        self.doc.recompute()
        self.assertGood(cells)
        walls = cells.AddSubShape
        self.assertLess(walls.common(cut).Volume, 1e-6)
        self.assertAlmostEqual(walls.Volume + cut.Volume, 26.0 * 26.0 * HT, places=3)

    def test_sandwich_core(self):
        """The README's pad sandwich: a bottom skin, a Walls pad for the core, a top skin."""
        App.closeDocument(self.doc.Name)
        self.doc = h.new_doc("padsandwich")
        body, bottom = h.plate(self.doc, 50, 50, 1.0, x=-8, y=-8, name="Skin")
        sk = h.sketch(body, z=1.0)
        h.add_rect(sk, *ALIGNED)
        g = hx.make_hex_grid_pad(body, sk, Height=3.0, Border=1.0)
        top = body.newObject("PartDesign::AdditiveBox", "TopSkin")
        top.Length, top.Width, top.Height = 50, 50, 1.0
        top.Placement = App.Placement(App.Vector(-8, -8, 4.0), App.Rotation())
        self.doc.recompute()
        self.assertNotIn("Invalid", g.State, g.State)
        self.assertNotIn("Invalid", top.State, top.State)
        sh = top.Shape
        self.assertEqual(len(sh.Solids), 1)
        self.assertTrue(sh.isValid())
        self.assertGreater(sh.Volume, 2 * 50 * 50 + (FIELD - ALIGNED_AREA) * 3.0 + 1.0)
        # the border seals every cell, edge cells included, as a void between the skins
        self.assertEqual(len(sh.slice(App.Vector(0, 0, 1), 2.5)),
                         1 + ALIGNED_WHOLE + ALIGNED_PARTIAL)
        for z in (0.5, 4.5):
            self.assertEqual(len(sh.slice(App.Vector(0, 0, 1), z)), 1)

    def test_a_hexgrid_cuts_a_pad(self):
        """A pad's raised cells are bosses a later HexGrid can pocket into."""
        g = self.pad(Mode="Cells", Height=3.0)
        sk = h.sketch(self.body, z=T + 3.0, name="Top")
        h.add_rect(sk, *ALIGNED)
        c = hx.make_hex_grid(self.body, sk, Depth=3.0)
        self.doc.recompute()
        self.assertNotIn("Invalid", c.State, c.State)
        self.assertAlmostEqual(c.Shape.Volume, self.box.Shape.Volume, places=3)
        self.assertEqual(len(c.Shape.Solids), 1)
        self.assertIs(self.body.Tip, c)
        self.assertIs(c.BaseFeature, g)


class PadMiscTest(unittest.TestCase):
    def test_icons_exist(self):
        from freecad.hexilator.viewprovider import ICONS, PAD_ICON
        self.assertTrue(os.path.isfile(PAD_ICON), PAD_ICON)
        # the command's Pixmap is a bare name resolved on the registered icon path
        self.assertTrue(os.path.isfile(os.path.join(ICONS, "Hexilator_HexGridPad.svg")))

    def test_performance(self):
        for mode in ("Walls", "Cells"):
            doc = h.new_doc("padperf")
            try:
                body, box = h.plate(doc, 140, 140, T)
                sk = h.sketch(body, z=T)
                h.add_rect(sk, 5, 5, 135, 135)
                g = hx.make_hex_grid_pad(body, sk, Mode=mode)
                t0 = time.time()
                doc.recompute()
                dt = time.time() - t0
                print("\n    pad performance (%s): %d cells in %.2f s"
                      % (mode, g.WholeCells + g.PartialCells, dt))
                self.assertNotIn("Invalid", g.State, g.State)
                self.assertGreater(g.WholeCells, 400)
                self.assertLess(dt, 60.0)
            finally:
                App.closeDocument(doc.Name)


class ReopenTest(unittest.TestCase):
    def test_save_reopen_recompute(self):
        tmp = os.environ["HEXILATOR_TMP"]
        path = os.path.join(tmp, "pad_reopen.FCStd")
        doc = h.new_doc("padreopen")
        body, box = h.plate(doc, 40, 40, T, x=-8, y=-8)
        sk = h.sketch(body, z=T)
        h.add_rect(sk, *ALIGNED)
        g = hx.make_hex_grid_pad(body, sk, Height=1.5, Border=0.4, Reversed=False)
        doc.recompute()
        vol = g.Shape.Volume
        doc.saveAs(path)
        App.closeDocument(doc.Name)
        out = h.run_freecad("""
            import FreeCAD as App
            d = App.openDocument(%r)
            g = d.getObject("HexGridPad")
            out["proxy"] = type(g.Proxy).__module__ + "." + type(g.Proxy).__name__
            out["props"] = [g.Mode, g.Height.Value, g.Border.Value, g.Reversed]
            out["vol0"] = g.Shape.Volume
            out["vis"] = [d.getObject(n).Visibility for n in ("BodyPlate", "Field", "HexGridPad")]
            out["tip"] = d.getObject("Body").Tip.Name
            g.Mode = "Cells"
            g.Height = 2
            d.recompute()
            out["state"] = list(g.State)
            out["vol1"] = g.Shape.Volume
            out["zmax"] = g.Shape.BoundBox.ZMax
            out["version"] = g.Version
        """ % path)
        self.assertNotIn("error", out, out.get("error"))
        self.assertEqual(out["proxy"], "freecad.hexilator.pad.HexGridPad")
        self.assertEqual(out["props"], ["Walls", 1.5, 0.4, False])
        self.assertAlmostEqual(out["vol0"], vol, places=6)
        self.assertEqual(out["vis"], [False, False, True])
        self.assertEqual(out["tip"], "HexGridPad")
        self.assertNotIn("Invalid", out["state"])
        self.assertAlmostEqual(out["vol1"], 40 * 40 * T + ALIGNED_AREA * 2.0, places=3)
        self.assertAlmostEqual(out["zmax"], T + 2.0, places=9)
        self.assertEqual(out["version"], hx.__version__)

    def test_file_without_pad_only_properties(self):
        """A pad saved before a property existed gains it, with its default, on restore."""
        tmp = os.environ["HEXILATOR_TMP"]
        path = os.path.join(tmp, "pad_old.FCStd")
        doc = h.new_doc("padold")
        body, box = h.plate(doc, 40, 40, T, x=-8, y=-8)
        sk = h.sketch(body, z=T)
        h.add_rect(sk, *ALIGNED)
        g = hx.make_hex_grid_pad(body, sk)
        doc.recompute()
        g.removeProperty("Border")
        doc.saveAs(path)
        App.closeDocument(doc.Name)
        out = h.run_freecad("""
            import FreeCAD as App
            d = App.openDocument(%r)
            g = d.getObject("HexGridPad")
            out["border"] = g.Border.Value
            g.touch()
            d.recompute()
            out["state"] = list(g.State)
        """ % path)
        self.assertNotIn("error", out, out.get("error"))
        self.assertEqual(out["border"], 0.0)
        self.assertNotIn("Invalid", out["state"])


if __name__ == "__main__":
    unittest.main()
