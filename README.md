# Hexilator

A FreeCAD addon for parametric hex grids: honeycomb vents and fan covers that cut cleanly into a part.

**Status:** released on GitHub. Each release is tagged `vX.Y.Z`, and the `release` branch holds the latest. Not yet in FreeCAD's Addon Manager. The design and its decisions are in [DESIGN.md](DESIGN.md).

## Goals
- A PartDesign feature that cuts a hex grid into a body, like a Pocket.
- **Hex Grid Pad**, its additive counterpart: it pads a grid onto a body, like a Pad. Either the walls between the cells (ribs, for stiffening or a honeycomb core) or the cells themselves (bosses, raised decoration), with an optional border rib along the field's edge. It takes the same field, lattice and clipping as Hex Grid, so a pad and a pocket can share a lattice.
- **Field:** a sketch. The outer loop is the area the grid fills; inner loops are keep-outs around openings (ports, holes, bosses).
- **Cell shapes:** hexagons by default. Also squares and triangles, which tile and snap like hexagons, and circles or regular polygons on a hexagonal or square grid.
- **Adjustable cell size** (inscribed diameter: across flats for a hexagon) and **spacing** (the web between cells).
- **Orientation, and a phase anchor** that pins the lattice, so grids on separate parts (e.g. a case's tray and lid, split across one grid) line up.
- **Depth or through-all.**
- **Clipping:**
  - The default is an unbroken lattice, with no missing columns or rows. Cells at the field's edge can be partial, but only where the edge cuts the cell along a line between two of its vertices.
  - Other modes: whole cells only, and free clipping.
- Every property takes expressions, so a grid can be driven from a spreadsheet.

## Use
In PartDesign, select the field sketch and click **Hex Grid** (to cut) or **Hex Grid Pad** (to pad), on the Hexilator toolbar or at the end of the Part Design menu. The task panel previews the grid as you edit it. Double-click a grid to edit it again.

From Python:

```python
from freecad.hexilator import make_hex_grid, make_hex_grid_pad, __version__

grid = make_hex_grid(body, sketch, CellSize=5, Web=1.2, Depth=3, AnchorX=0, AnchorY=0)
grid.setExpression("CellSize", "Params.HexCell")  # any property can be driven by a sheet
square = make_hex_grid(body, sketch2, CellShape="Square", CellSize=4, Web=1)
holes = make_hex_grid(body, sketch3, CellShape="Circle", Lattice="Hexagonal", CellSize=3)
ribs = make_hex_grid_pad(body, sketch4, Mode="Walls", Height=2, Border=1)   # raised ribs
bosses = make_hex_grid_pad(body, sketch5, Mode="Cells", Height=1, Reversed=False)
```

**Hex Grid Pad** has `Mode` `Walls` (the field minus the cells: ribs of thickness `Web`) or `Cells` (the cells: bosses), a `Height` (along the sketch normal, as Pad does; `Reversed` pads against it), and a `Border`: in `Walls` mode, a rib of that width along the inside of the field's outline and around each keep-out. With `Border` 0 the walls simply stop where the cells are cut. The result must fuse into one solid, so `Cells` bosses need something to stand on.

**Honeycomb sandwich** (two solid skins with a honeycomb core), two ways:
- **Pocket:** pad the full sheet, put the field sketch inside it at the top of the core layer, and give the Hex Grid a `Depth` equal to the core's thickness. The cells become sealed voids between the skins.
- **Pad:** pad the bottom skin, then a Hex Grid Pad in `Walls` mode (with a `Border` for a sealed edge) at the core's height, then the top skin on top. The walls are the honeycomb.

The sketch's outer loops are the fields and its inner loops are keep-outs. `ClipMode` is `Snap` (the default), `Whole` or `Free`. The read-only properties `WholeCells`, `PartialCells`, `FallbackCells`, `OpenArea` and `Version` report the result. See [DESIGN.md](DESIGN.md) for every property.

## Install
An install is a git checkout at `<FreeCAD user data>/Mod/Hexilator`, which is `~/.local/share/FreeCAD/v1-1/Mod/Hexilator` for FreeCAD 1.1 on Linux. FreeCAD only restores the feature's code from a Mod folder, so a copy that is merely on `sys.path` doesn't work. From a clone of this repo:

```sh
HEXILATOR_REF=v0.3.0 mise run install    # a release tag (pinned)
HEXILATOR_REF=release mise run install   # the latest release
# a local branch, before a release:
HEXILATOR_SOURCE=~/Work/Parts/addons/hexilator/.repo HEXILATOR_REF=master mise run install
# or pin one commit (a full 40-character SHA):
HEXILATOR_SOURCE=~/Work/Parts/addons/hexilator/.repo HEXILATOR_REF=<sha> mise run install
```

A file opened without the addon keeps its last shape and recomputes silently, so a missing addon is invisible. Projects that depend on it should check `freecad.hexilator.__version__`.

## Limitations
- FreeCAD 1.1 or later.
- Only straight edges in lattice directions snap. A loop with an arc, a spline or an off-angle edge (e.g. a round keep-out, or a rounded rectangle) keeps its drawn shape. Its boundary cells get the largest single-chord piece that fits, and are counted in `FallbackCells`.
- Triangles: a field edge can snap inward by nearly a whole row, and a rectangular field doesn't snap at all (its vertical edges aren't triangle-lattice directions). Circles and polygons have no lattice lines, so `Snap` acts as `Whole`.
- Large grids are slow: one cut of all the cells takes about 5 s for 500 hexagons and 18 s for 1000, growing roughly quadratically. A pad takes about 4 s for 500. The task panel previews after a short pause.
- No sketch output yet, and no translations shipped (the strings are marked for translation).

## Compared with HexFill
[HexFill](https://github.com/Clientik/FreeCAD-HexFill) writes a one-shot, unconstrained sketch of hexagons for you to Pocket. Hexilator is a parametric PartDesign feature: it also pads (Hex Grid Pad), recomputes when the field sketch, its properties or a spreadsheet change, snaps the field's edges to the lattice so the edge cells are cut cleanly, pins the lattice with an anchor so grids on separate parts line up, and offers square, triangle, circle and polygon cells.

## Development
- `mise run test`: the test suite, headless under `freecadcmd`.
- `mise run test-gui`: the GUI test, in full FreeCAD under Xvfb.
- `mise run lint`: the workflows (actionlint), the task scripts (shellcheck) and the Python (Bandit).
- `mise run shot -- file.FCStd out.png`: a screenshot, off-screen.

Commits follow [Conventional Commits](https://www.conventionalcommits.org). Releases are tagged automatically from them; see DESIGN.md, Development process.

## Requirements
- FreeCAD 1.1.
- [mise](https://mise.jdx.dev) for the tooling (see `mise.toml`).

## Licence
Apache License 2.0; see [LICENSE.md](LICENSE.md).
