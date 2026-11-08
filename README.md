# Hexilator

A FreeCAD addon for parametric hex grids: honeycomb vents and fan covers that cut cleanly into a part.

**Status:** v0.1 in development. The design and its decisions are in [DESIGN.md](DESIGN.md).

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

## Use
There's no toolbar command yet. Create a grid from Python:

```python
from freecad.hexilator import make_hex_grid, __version__

grid = make_hex_grid(body, sketch, CellSize=5, Web=1.2, Depth=3, AnchorX=0, AnchorY=0)
grid.setExpression("CellSize", "Params.HexCell")  # any property can be driven by a sheet
```

The sketch's outer loops are the fields and its inner loops are keep-outs. `ClipMode` is `Snap` (the default), `Whole` or `Free`. The read-only properties `WholeCells`, `PartialCells`, `FallbackCells`, `OpenArea` and `Version` report the result. See [DESIGN.md](DESIGN.md) for every property.

## Install
An install is a git checkout at `<FreeCAD user data>/Mod/Hexilator`, which is `~/.local/share/FreeCAD/v1-1/Mod/Hexilator` for FreeCAD 1.1 on Linux. FreeCAD only restores the feature's code from a Mod folder, so a copy that is merely on `sys.path` doesn't work. From a clone of this repo:

```sh
HEXILATOR_REF=v0.1.0 mise run install
# a local branch, before a release:
HEXILATOR_SOURCE=~/Work/Parts/addons/hexilator/.repo HEXILATOR_REF=master mise run install
# or pin one commit (a full 40-character SHA):
HEXILATOR_SOURCE=~/Work/Parts/addons/hexilator/.repo HEXILATOR_REF=<sha> mise run install
```

A file opened without the addon keeps its last shape and recomputes silently, so a missing addon is invisible. Projects that depend on it should check `freecad.hexilator.__version__`.

## Development
- `mise run test`: the test suite, headless under `freecadcmd`.
- `mise run test-gui`: the GUI test, in full FreeCAD under Xvfb.
- `mise run lint`: the workflows (actionlint) and task scripts (shellcheck).
- `mise run shot -- file.FCStd out.png`: a screenshot, off-screen.

Commits follow [Conventional Commits](https://www.conventionalcommits.org). Releases are tagged automatically from them; see DESIGN.md, Development process.

## Requirements
- FreeCAD 1.1.
- [mise](https://mise.jdx.dev) for the tooling (see `mise.toml`).

## Licence
Apache License 2.0; see [LICENSE.md](LICENSE.md).
