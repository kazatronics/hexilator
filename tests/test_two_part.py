# SPDX-License-Identifier: Apache-2.0
"""One lattice over two parts (a tray and a lid split through the grid) must give, between them,
the same openings as one feature on one body (DESIGN.md, Two-part grids)."""

import unittest

import FreeCAD as App

import helpers as h

import freecad.hexilator as hx

T = 3.0
L, WID = 60.0, 40.0
FIELD = (4.0, 4.0, 56.0, 36.0)  # off the lattice on every side: Snap moves all four edges


class TwoPartTest(unittest.TestCase):
    def setUp(self):
        self.doc = h.new_doc("split")

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def part(self, name, y0, y1, anchor, **props):
        """A body covering y0..y1 of the plate, with its own sketch of the full field."""
        body, box = h.plate(self.doc, L, y1 - y0, T, x=0.0, y=y0, name=name)
        sk = h.sketch(body, z=T, name=name + "Field")
        h.add_rect(sk, *FIELD)
        g = hx.make_hex_grid(body, sk, name=name + "Grid", AnchorX=anchor[0],
                             AnchorY=anchor[1], **props)
        return box, g

    def check_split(self, split, anchor, **props):
        _, single = self.part("Single", 0.0, WID, anchor, **props)
        _, tray = self.part("Tray", 0.0, split, anchor, **props)
        _, lid = self.part("Lid", split, WID, anchor, **props)
        self.doc.recompute()
        for g in (single, tray, lid):
            self.assertNotIn("Invalid", g.State, g.Label)
            self.assertTrue(g.Shape.isValid())
        both = tray.Shape.fuse(lid.Shape)
        self.assertAlmostEqual(both.Volume, single.Shape.Volume, places=4)
        self.assertAlmostEqual(single.Shape.cut(both).Volume, 0.0, places=4)
        self.assertAlmostEqual(both.cut(single.Shape).Volume, 0.0, places=4)
        # both parts carry openings, and the tools are the same lattice
        self.assertGreater(tray.WholeCells + tray.PartialCells, 0)
        self.assertEqual(tray.WholeCells, single.WholeCells)
        self.assertEqual(lid.PartialCells, single.PartialCells)
        return single, tray, lid

    def test_split_on_lattice_line(self):
        # anchor (3, 4): the line y = 4 + 3p/2 passes through the centres of odd columns
        self.check_split(4.0 + 3 * h.P / 2, (3.0, 4.0))

    def test_split_anywhere(self):
        self.check_split(17.3, (1.7, 2.9))

    def test_split_rotated(self):
        self.check_split(20.0, (30.0, 20.0), Angle=30)

    def test_split_whole_mode(self):
        self.check_split(19.0, (3.0, 4.0), ClipMode="Whole")


if __name__ == "__main__":
    unittest.main()
