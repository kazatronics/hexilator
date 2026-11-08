# SPDX-License-Identifier: Apache-2.0
"""HexGrid feature tests, under freecadcmd."""

import math
import os
import re
import time
import unittest

import FreeCAD as App

import helpers as h
from helpers import ALIGNED, ALIGNED_AREA, ALIGNED_PARTIAL, ALIGNED_WHOLE

import freecad.hexilator as hx

T = 3.0  # plate thickness


class FeatureTest(unittest.TestCase):
    def setUp(self):
        self.doc = h.new_doc("feat")
        # plate around ALIGNED with room to spare
        self.body, self.box = h.plate(self.doc, 40, 40, T, x=-8, y=-8)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def grid(self, rect=ALIGNED, z=T, **props):
        self.sk = h.sketch(self.body, z=z)
        h.add_rect(self.sk, *rect)
        g = hx.make_hex_grid(self.body, self.sk, **props)
        self.doc.recompute()
        return g

    def assertGood(self, g):
        self.assertNotIn("Invalid", g.State, g.State)
        self.assertTrue(g.Shape.isValid())
        self.assertEqual(len(g.Shape.Solids), 1)
        self.assertIs(self.body.Tip, g)

    def removed(self, g):
        return self.box.Shape.Volume - g.Shape.Volume

    def test_aligned_field(self):
        g = self.grid()
        self.assertGood(g)
        self.assertEqual((g.WholeCells, g.PartialCells, g.FallbackCells),
                         (ALIGNED_WHOLE, ALIGNED_PARTIAL, 0))
        self.assertAlmostEqual(g.OpenArea.Value, ALIGNED_AREA, places=6)
        self.assertAlmostEqual(self.removed(g), ALIGNED_AREA * T, places=4)
        self.assertEqual(g.Version, hx.__version__)

    def test_off_lattice_field_snaps_inward(self):
        x0, y0, x1, y1 = ALIGNED
        g = self.grid(rect=(x0 - 0.45, y0 - 0.45, x1 + 0.45, y1 + 0.45))
        self.assertGood(g)
        self.assertEqual((g.WholeCells, g.PartialCells), (ALIGNED_WHOLE, ALIGNED_PARTIAL))
        self.assertAlmostEqual(self.removed(g), ALIGNED_AREA * T, places=4)

    def test_whole_and_free(self):
        g = self.grid(ClipMode="Whole")
        self.assertGood(g)
        self.assertEqual((g.WholeCells, g.PartialCells), (ALIGNED_WHOLE, 0))
        x0, y0, x1, y1 = ALIGNED
        g.ClipMode = "Free"
        self.sk.deleteAllGeometry()
        h.add_polygon(self.sk, [(x0, y0), (x1 + 1.0, y0), (x1, y1), (x0, y1)])  # off lattice
        self.doc.recompute()
        self.assertGood(g)
        self.assertGreater(g.PartialCells, 0)
        self.assertAlmostEqual(self.removed(g), g.OpenArea.Value * T, places=4)

    def test_keepouts(self):
        sk = h.sketch(self.body, z=T)
        h.add_rect(sk, -6, -6, 30, 30)
        h.add_rect(sk, 2, 2, 9, 7)      # rectangular keep-out: snaps outward
        h.add_circle(sk, 20, 18, 4)     # round keep-out: falls back
        g = hx.make_hex_grid(self.body, sk)
        self.doc.recompute()
        self.assertGood(g)
        self.assertGreater(g.FallbackCells, 0)
        self.assertAlmostEqual(self.removed(g), g.OpenArea.Value * T, places=4)
        # nothing is cut inside either keep-out as drawn
        self.assertTrue(g.Shape.isInside(App.Vector(5.5, 4.5, T / 2), 1e-6, True))
        self.assertTrue(g.Shape.isInside(App.Vector(20, 18, T / 2), 1e-6, True))
        self.assertTrue(g.Shape.isInside(App.Vector(23.9, 18, T / 2), 1e-6, True))

    def test_circle_field_anchor_noise(self):
        """Issue #5, Trellis's case: a circle field centred at y = -11.7 with the anchor at
        -11.700000000000003 (spreadsheet arithmetic) cuts the same cells as an exact anchor."""
        doc = h.new_doc("circ")
        try:
            body, box = h.plate(doc, 100, 100, T, x=-60, y=-60)
            sk = h.sketch(body, z=T)
            h.add_circle(sk, -9.0, -11.7, 26.4)
            g = hx.make_hex_grid(body, sk, AnchorX=-9.0, AnchorY=-11.7)
            doc.recompute()
            exact = (g.WholeCells, g.PartialCells, g.FallbackCells, round(g.OpenArea.Value, 6))
            g.AnchorY = -11.700000000000003
            doc.recompute()
            self.assertNotIn("Invalid", g.State)
            self.assertEqual((g.WholeCells, g.PartialCells, g.FallbackCells,
                              round(g.OpenArea.Value, 6)), exact)
            # the cell at the anchor is cut
            self.assertFalse(g.Shape.isInside(App.Vector(-9.0, -11.7, T / 2), 1e-6, True))
        finally:
            App.closeDocument(doc.Name)

    def test_angle_30(self):
        g = self.grid(Angle=30)
        self.assertGood(g)
        # the rectangle's edges run at -30° and 60° in the lattice frame: they still snap
        self.assertEqual(g.FallbackCells, 0)
        self.assertGreater(g.WholeCells, 0)
        self.assertAlmostEqual(self.removed(g), g.OpenArea.Value * T, places=4)

    def test_anchor(self):
        g = self.grid()
        ref = (g.WholeCells, g.PartialCells, round(g.Shape.Volume, 6))
        # one lattice step along a column: the same grid
        g.AnchorY = h.P
        self.doc.recompute()
        self.assertEqual((g.WholeCells, g.PartialCells, round(g.Shape.Volume, 6)), ref)
        # a column and a half step: the same lattice too
        g.AnchorX, g.AnchorY = h.H, h.P / 2
        self.doc.recompute()
        self.assertEqual((g.WholeCells, g.PartialCells, round(g.Shape.Volume, 6)), ref)
        g.AnchorX = 1.0
        self.doc.recompute()
        self.assertGood(g)
        self.assertNotEqual(round(g.Shape.Volume, 6), ref[2])

    def test_depth_type_reversed(self):
        g = self.grid(Depth=1.0)
        self.assertAlmostEqual(self.removed(g), ALIGNED_AREA * 1.0, places=4)
        g.Type = "ThroughAll"
        self.doc.recompute()
        self.assertAlmostEqual(self.removed(g), ALIGNED_AREA * T, places=4)
        # from the bottom face: against the normal cuts nothing, Reversed cuts through
        self.sk.Placement = App.Placement()
        g.Type = "Dimension"
        g.Depth = T
        self.doc.recompute()
        self.assertAlmostEqual(self.removed(g), 0.0, places=4)
        g.Reversed = True
        self.doc.recompute()
        self.assertAlmostEqual(self.removed(g), ALIGNED_AREA * T, places=4)

    def test_expressions(self):
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Params")
        sheet.set("A1", "5 mm")
        sheet.setAlias("A1", "Cell")
        sheet.set("A2", "1.2 mm")
        sheet.setAlias("A2", "Web")
        sheet.set("A3", "0 mm")
        sheet.setAlias("A3", "AX")
        self.doc.recompute()
        g = self.grid()
        g.setExpression("CellSize", "Params.Cell")
        g.setExpression("Web", "Params.Web")
        g.setExpression("AnchorX", "Params.AX")
        g.setExpression("Depth", "Params.Web * 2")
        self.doc.recompute()
        self.assertEqual(g.WholeCells, ALIGNED_WHOLE)
        self.assertAlmostEqual(g.Depth.Value, 2.4)
        sheet.set("A1", "4 mm")
        self.doc.recompute()
        self.assertGood(g)
        self.assertAlmostEqual(g.CellSize.Value, 4.0)
        self.assertNotEqual(g.WholeCells, ALIGNED_WHOLE)

    def test_visibility(self):
        g = self.grid()
        self.assertFalse(self.box.Visibility)
        self.assertFalse(self.sk.Visibility)
        self.assertTrue(g.Visibility)

    def test_errors(self):
        doc = h.new_doc("err")
        try:
            body = doc.addObject("PartDesign::Body", "Body")
            sk = h.sketch(body)
            h.add_rect(sk, 0, 0, 20, 20)
            g = hx.make_hex_grid(body, sk)
            doc.recompute()
            self.assertIn("Invalid", g.State)  # no base solid
        finally:
            App.closeDocument(doc.Name)
        g = self.grid(Web=0.0)
        self.assertIn("Invalid", g.State)

    def test_body_placement(self):
        self.body.Placement = App.Placement(App.Vector(100, 50, 20), App.Rotation(30, 10, 5))
        g = self.grid()
        self.assertGood(g)
        self.assertAlmostEqual(self.removed(g), ALIGNED_AREA * T, places=4)

    def test_sketch_on_other_plane(self):
        """A sketch whose plane isn't XY: a wall in the XZ plane, cut along +y into it."""
        doc = self.doc
        body, box = h.plate(doc, 40, 3, 40, x=-8, y=0, name="Wall")
        rot = App.Rotation(App.Vector(1, 0, 0), 90)  # sketch normal = -y
        sk = h.sketch(body, z=0, rot=rot, name="WallField")
        sk.Placement = App.Placement(App.Vector(0, 0, 8), rot)
        h.add_rect(sk, *ALIGNED)
        g = hx.make_hex_grid(body, sk, Reversed=False)
        doc.recompute()
        self.assertNotIn("Invalid", g.State)
        self.assertAlmostEqual(box.Shape.Volume - g.Shape.Volume, ALIGNED_AREA * 3, places=4)

    def test_performance(self):
        doc = h.new_doc("perf")
        try:
            body, box = h.plate(doc, 140, 140, T)
            sk = h.sketch(body, z=T)
            h.add_rect(sk, 5, 5, 135, 135)
            g = hx.make_hex_grid(body, sk)
            t0 = time.time()
            doc.recompute()
            dt = time.time() - t0
            print("\n    performance: %d cells in %.2f s" % (g.WholeCells + g.PartialCells, dt))
            self.assertGreater(g.WholeCells, 400)
            self.assertLess(dt, 60.0)
        finally:
            App.closeDocument(doc.Name)


class VersionTest(unittest.TestCase):
    def test_version_matches_package_xml(self):
        root = os.environ["HEXILATOR_ROOT"]
        with open(os.path.join(root, "package.xml")) as f:
            m = re.search(r"<version>([^<]+)</version>", f.read())
        self.assertEqual(hx.__version__, m.group(1))
        self.assertRegex(hx.__version__, r"^\d+\.\d+\.\d+$")


class ReopenTest(unittest.TestCase):
    def test_save_reopen_recompute(self):
        tmp = os.environ["HEXILATOR_TMP"]
        path = os.path.join(tmp, "reopen.FCStd")
        doc = h.new_doc("reopen")
        body, box = h.plate(doc, 40, 40, T, x=-8, y=-8)
        sk = h.sketch(body, z=T)
        h.add_rect(sk, *ALIGNED)
        g = hx.make_hex_grid(body, sk)
        doc.recompute()
        vol = g.Shape.Volume
        doc.saveAs(path)
        App.closeDocument(doc.Name)
        out = h.run_freecad("""
            import FreeCAD as App
            d = App.openDocument(%r)
            g = d.getObject("HexGrid")
            out["proxy"] = type(g.Proxy).__module__ + "." + type(g.Proxy).__name__
            out["vol0"] = g.Shape.Volume
            out["vis"] = [d.getObject(n).Visibility for n in ("BodyPlate", "Field", "HexGrid")]
            out["tip"] = d.getObject("Body").Tip.Name
            g.CellSize = 4
            d.recompute()
            out["state"] = list(g.State)
            out["vol1"] = g.Shape.Volume
            out["version"] = g.Version
        """ % path)
        self.assertNotIn("error", out, out.get("error"))
        self.assertEqual(out["proxy"], "freecad.hexilator.feature.HexGrid")
        self.assertAlmostEqual(out["vol0"], vol, places=6)
        self.assertEqual(out["vis"], [False, False, True])
        self.assertEqual(out["tip"], "HexGrid")
        self.assertNotIn("Invalid", out["state"])
        self.assertNotAlmostEqual(out["vol1"], vol, places=3)
        self.assertEqual(out["version"], hx.__version__)


if __name__ == "__main__":
    unittest.main()
