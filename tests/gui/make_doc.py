# SPDX-License-Identifier: Apache-2.0
"""Headless part of the GUI test: build a document with a HexGrid and save it without GUI data.
Run by freecadcmd from mise-tasks/test-gui; saves to $HEXILATOR_DOC."""

import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.environ["HEXILATOR_ROOT"], "tests"))
try:
    import FreeCAD as App

    import helpers as h

    import freecad.hexilator as hx

    doc = h.new_doc("gui")
    body, box = h.plate(doc, 40, 40, 3.0, x=-8, y=-8)
    sk = h.sketch(body, z=3.0)
    h.add_rect(sk, *h.ALIGNED)
    h.add_circle(sk, 10.7, 12.4, 2.0)  # a round keep-out: fallback cells
    g = hx.make_hex_grid(body, sk)
    doc.recompute()
    assert "Invalid" not in g.State, g.State
    doc.saveAs(os.environ["HEXILATOR_DOC"])
except Exception:
    traceback.print_exc()
