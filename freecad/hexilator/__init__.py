# SPDX-License-Identifier: Apache-2.0
"""Hexilator: parametric hex grids for FreeCAD PartDesign."""

import os as _os
import re as _re


def _read_version():
    # package.xml is the single source of the version (see DESIGN.md, Releases).
    path = _os.path.join(_os.path.dirname(__file__), "..", "..", "package.xml")
    with open(path, encoding="utf-8") as f:
        m = _re.search(r"<version>\s*([^<\s]+)\s*</version>", f.read())
    if not m:
        raise RuntimeError("Hexilator: no <version> in %s" % path)
    return m.group(1)


__version__ = _read_version()


def make_hex_grid(body, profile, name="HexGrid", **props):
    """Add a HexGrid feature to body; see feature.make_hex_grid."""
    from .feature import make_hex_grid as _make
    return _make(body, profile, name, **props)
