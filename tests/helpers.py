# SPDX-License-Identifier: Apache-2.0
"""Shared test helpers. FreeCAD imports are local, so core tests can import this file too."""

import json
import math
import os
import subprocess
import textwrap

S, W = 5.0, 1.2
P = S + W
H = P * math.sqrt(3) / 2
R = S / math.sqrt(3)
CELL_AREA = math.sqrt(3) / 2 * S * S

# A field whose edges all lie on lattice lines (anchor at the origin, Angle 0):
# columns 0 and 4 are cut to 5/6 by their outer short chords, y = 0 and y = 4p pass through
# the centres of the even columns.
ALIGNED = (-R / 2, 0.0, 4 * H + R / 2, 4 * P)
# Snap result for ALIGNED (see test_feature): 11 whole cells; 12 partial: 6 pentagons,
# 4 corner quads (5/12) and 2 halves.
ALIGNED_WHOLE = 11
ALIGNED_PARTIAL = 12
ALIGNED_AREA = CELL_AREA * (11 + 6 * 5 / 6 + 4 * 5 / 12 + 2 * 0.5)


def new_doc(name="t"):
    import FreeCAD as App
    return App.newDocument(name)


def plate(doc, length=60.0, width=50.0, thick=3.0, x=0.0, y=0.0, name="Body"):
    """A body holding one box plate from (x, y, 0) to (x+length, y+width, thick)."""
    import FreeCAD as App
    body = doc.addObject("PartDesign::Body", name)
    box = body.newObject("PartDesign::AdditiveBox", name + "Plate")
    box.Length, box.Width, box.Height = length, width, thick
    # unattached, so Placement is free (AttachmentOffset only applies when attached)
    box.Placement = App.Placement(App.Vector(x, y, 0), App.Rotation())
    return body, box


def sketch(body, z=3.0, name="Field", rot=None):
    """An unattached sketch in body, in the plane z (normal +z unless rot is given)."""
    import FreeCAD as App
    sk = body.newObject("Sketcher::SketchObject", name)
    sk.Placement = App.Placement(App.Vector(0, 0, z), rot or App.Rotation())
    return sk


def add_rect(sk, x0, y0, x1, y1):
    import FreeCAD as App
    import Part
    pts = [App.Vector(x0, y0, 0), App.Vector(x1, y0, 0), App.Vector(x1, y1, 0),
           App.Vector(x0, y1, 0)]
    for k in range(4):
        sk.addGeometry(Part.LineSegment(pts[k], pts[(k + 1) % 4]))


def add_polygon(sk, pts):
    import FreeCAD as App
    import Part
    vs = [App.Vector(x, y, 0) for x, y in pts]
    for k in range(len(vs)):
        sk.addGeometry(Part.LineSegment(vs[k], vs[(k + 1) % len(vs)]))


def add_circle(sk, cx, cy, r):
    import FreeCAD as App
    import Part
    sk.addGeometry(Part.Circle(App.Vector(cx, cy, 0), App.Vector(0, 0, 1), r))


def run_freecad(script, timeout=300):
    """Run a script in a new freecadcmd process (same addon install). Returns its `out` dict.

    The script assigns a dict to `out`; it's passed back as JSON.
    """
    tmp = os.environ["HEXILATOR_TMP"]
    path = os.path.join(tmp, "sub_%d.py" % os.getpid())
    res = os.path.join(tmp, "sub_%d.json" % os.getpid())
    if os.path.exists(res):
        os.remove(res)
    body = textwrap.dedent(script)
    wrapper = ("import json, traceback\nout = {}\ntry:\n%s\nexcept Exception:\n"
               "    out['error'] = traceback.format_exc()\n"
               "with open(%r, 'w') as _f:\n    json.dump(out, _f)\n"
               % (textwrap.indent(body, "    "), res))
    with open(path, "w") as f:
        f.write(wrapper)
    subprocess.run([os.environ.get("FREECADCMD", "freecadcmd"), path], timeout=timeout,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    with open(res) as f:
        return json.load(f)
