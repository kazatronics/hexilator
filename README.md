# Hexilator

A FreeCAD addon for parametric hex grids: honeycomb vents and fan covers that cut cleanly into a part.

**Status:** repository structure only. No code yet.

## Goals
- A PartDesign feature that cuts a hex grid into a body, like a Pocket.
- **Field:** a sketch. The outer loop is the area the grid fills; inner loops are keep-outs around openings (ports, holes, bosses).
- **Adjustable cell size** (across flats) and **spacing** (the web between cells).
- **Orientation, and a phase anchor** that pins the lattice, so grids on separate parts (e.g. a case's tray and lid, split across one grid) line up.
- **Depth or through-all.**
- **Clipping:**
  - The default is an unbroken lattice, with no missing columns or rows. Cells at the field's edge can be partial, but only where the edge cuts the cell along a line between two of its vertices.
  - Other modes: whole cells only, and free clipping.
- Every property takes expressions, so a grid can be driven from a spreadsheet.

## Requirements
- FreeCAD 1.1.
- [mise](https://mise.jdx.dev) for the tooling (see `mise.toml`).

## Licence
Apache License 2.0; see [LICENSE.md](LICENSE.md).
