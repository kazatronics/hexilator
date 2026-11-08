# Hexilator design

Agreed 2026-11-08 with the Trellis project (the first user), which directs this addon's work. This file records the decisions and the reasoning behind them. When a decision changes, update it here.

## Feature
`HexGrid` is a `PartDesign::FeatureSubtractivePython`. It cuts a hex lattice into the body, the way a Pocket does. Create it from Python:

```python
from freecad.hexilator import make_hex_grid
grid = make_hex_grid(body, sketch, CellSize=5, Web=1.2, Depth=3)
```

There's no toolbar command in v0.1. There is a ViewProvider (see GUI).

### Properties
Every input is a standard FreeCAD property type, so each one takes expressions (e.g. `grid.setExpression("CellSize", "Params.HexCell")`).

| Property | Type | Default | Meaning |
|---|---|---|---|
| `Profile` | LinkSub | | The field: a sketch or any planar face in the same body. Outer loops are fields; inner loops are keep-outs. Islands inside keep-outs are fields again. |
| `CellSize` | Length | 5 | Cell width across flats. |
| `Web` | Length | 1.2 | Wall between neighbouring cells. Must be > 0. |
| `Angle` | Angle | 0 | Lattice rotation about the anchor, in the sketch plane. See Lattice. |
| `AnchorX`, `AnchorY` | Distance | 0 | A cell centre sits at this point, in sketch coordinates. This pins the lattice's phase. |
| `ClipMode` | Enumeration | `Snap` | `Snap`, `Whole` or `Free`. See Clipping. |
| `Type` | Enumeration | `Dimension` | `Dimension` or `ThroughAll`, as for Pocket. |
| `Depth` | Length | 3 | Cut depth for `Dimension`. |
| `Reversed` | Bool | false | Cut along the sketch normal instead of against it. |
| `Refine` | Bool | false | Inherited from PartDesign. |

Read-only outputs, which Trellis `Check` cells can guard:

| Property | Meaning |
|---|---|
| `WholeCells` | Cells cut whole. |
| `PartialCells` | Cells cut partially. This includes fallback cells. |
| `FallbackCells` | Partial cells next to a boundary that couldn't snap (arcs, splines, off-angle edges); see Fallback. Kept visible so a user can see where a round keep-out fell back. |
| `OpenArea` | Total area of the cell openings in the sketch plane (mm²). |
| `Version` | `__version__` of the addon that last recomputed this feature. |

Properties are added in `__init__` and again in `onDocumentRestored` (when missing), so files saved by an older version gain any new properties.

## Lattice
Definitions:
- `s` = `CellSize` (across flats)
- `w` = `Web`
- `p` = `s + w`, the distance between neighbouring cell centres
- `h` = `p·√3/2`, the distance between columns
- `R` = `s/√3`, the circumradius

In the lattice frame (sketch frame, rotated by `Angle` about the anchor):
- **`Angle` 0 is flat-top.** Two flats of each cell are parallel to the sketch X axis, with vertices at 0°, 60°, … 300°.
- **Cells stack in columns** along Y at pitch `p`.
- **Columns are `h` apart** along X, and each column is offset by `p/2` from its neighbour.
- `Angle` 30 is pointy-top. The lattice repeats every 60°.

Cell `(i, j)` has its centre at `anchor + rot(Angle)·(i·h, i·p/2 + j·p)`. Centres always come from the integer indices, never from adding steps together. Two features with the same parameters and the same anchor in the same frame therefore get identical lattices. That is how a grid split across two printed parts lines up.

### Lattice lines
A *lattice line* cuts every cell it crosses along a chord between two of that cell's vertices, and passes through the web of every other cell. For `w > 0` there are two families, in lattice-frame directions:
- **Long-diagonal lines** at 0°, 60° and 120°. Each passes through the centres of alternate columns (for 0°) and halves those cells. It passes through the web of the other columns, `w/2` from their nearest cells. They lie at offsets `m·p/2` along the line's normal, where m is any integer.
- **Short-diagonal lines** at 30°, 90° and 150°. For 90°, these are the lines `±R/2` from a column's centre line. Each cuts every cell of that column, leaving a 5/6 pentagon on one side and a 1/6 triangle on the other. It clears the next column by `h − 3R/2 = w·√3/2`. They lie at offsets `i·h ± R/2`.

The other directions are the same lines rotated by multiples of 60°. Each family has a period (`p/2`, or `h` with two phases) along its normal.

## Clipping
The sketch is the limit: no mode ever cuts outside the field as drawn, or inside a keep-out as drawn. Fields are drawn where the cut may reach, e.g. inside a part's solid frame.

### `Snap` (default)
This is the user's rule (Trellis `CLAUDE.md`): one unbroken lattice with no missing columns or rows; gaps only around openings; a partial cell is allowed only where the edge cuts it along a line between two of its vertices.
1. **Snap the loops.** Take each loop made only of straight edges that run along a lattice-line direction (within an angle tolerance). Merge collinear neighbouring edges. Move each edge onto the nearest lattice line of its direction on the solid side: fields shrink and keep-outs grow, never the other way. The edges then get new vertices where neighbouring snapped edges meet. An edge already on a lattice line stays put.
   - With cell 5 and web 1.2, an edge moves at most 3.1 across the columns and 2.89 along them.
   - A loop that isn't snappable (it has an arc, a spline or an off-angle edge) is kept as drawn.
   - A loop that collapses or self-intersects when snapped is also kept as drawn, with a warning.
2. **Clip.** Call the snapped region S:
   - A cell entirely inside S is cut whole.
   - A cell crossed only by snapped edges is cut exactly to `cell ∩ S`. Every cut runs along one of the cell's vertex-to-vertex lines, because snapped edges lie on lattice lines. A corner of S inside a cell gives a two-cut piece, e.g. the 5/12 quadrilateral where a 0° edge and a 90° edge meet.
3. **Fallback.** A cell crossed by an unsnapped boundary is cut to the largest single-chord piece that lies inside S. The candidates are the whole cell, a 5/6 pentagon, a 1/2 trapezoid and a 1/6 triangle, in each of their 6 orientations, 19 in all. If none fits, the cell is left solid. Fallback cells are counted in `FallbackCells`.

The 1/6 triangle is allowed (at cell 5 it's 5 × 1.44). There is no minimum piece size and no `Margin` property.

Snap was chosen over per-cell clipping alone, which would skip step 1 and give every boundary cell its largest single-chord piece. Per-cell is sometimes more open, but its edges come out ragged: when an edge lies just short of a lattice line, alternate columns end half a step short. Its corners also get a triangle where Snap gives the quadrilateral.

### `Whole`
Only cells entirely inside the field as drawn are cut.

### `Free`
Boundary cells are clipped to the field as drawn, exactly: `cell ∩ field`, with no snapping.

### Two-part grids
The feature knows only its field, not the body. A field drawn past the body's edge (e.g. past the split between a tray and a lid) is cut there by the body, freely. Putting the split on a lattice line is the user's job, through the anchor. One lattice spread over two parts' features must produce, between them, the same cells as a single feature on one body; the tests check this.

## Geometry build
- **Core** (`freecad/hexilator/core/`, pure Python, no FreeCAD import): the lattice, the lattice lines, snapping, classification and piece selection. Boundaries are exact segments and circular arcs. Other curves (ellipses, B-splines) are discretised in the FreeCAD layer before they reach the core, which makes their loops unsnappable.
- **FreeCAD layer:**
  - read the profile's wires and turn them into loops;
  - build one hex prism template and place whole cells as translated copies of it, so they share geometry;
  - build partial cells as polygon prisms;
  - make one compound and do one `cut` of `BaseFeature.Shape`;
  - set `AddSubShape` to the compound.
- **Prism:** the tool is built in the sketch's local frame and placed with the sketch's `Placement`. It runs from the sketch plane against the sketch normal by `Depth` (`Reversed` flips it). `ThroughAll` uses a length beyond the base shape's bounding box. The result must be one valid solid, or the feature raises a clear error. It also raises if there is no `BaseFeature`.
- **Performance** (research, FreeCAD 1.1.4): one compound cut takes about 0.4 s for 100 cells, 5 s for 484 and 18 s for 1024, roughly quadratic. Fusing the prisms first, tiled cuts and sequential cuts were all no faster. Building the 2D face without booleans and extruding once was only about 20% faster. `Refine` adds 0–40%, so it's off by default.

## GUI
- **ViewProvider:** it gives the icon and the tree display. Properties are editable in the property editor. A file containing a HexGrid has to open and display cleanly in the user's own FreeCAD.
- **Headless-created files:** a file made headless has no GUI view data, so the view provider proxy is attached when the document is restored in the GUI.
- **Visibility:** `make_hex_grid` leaves the new feature visible, and hides the profile sketch and the previous feature. Headless saves get no GUI view data, so it does this the way the GUI would. After a save, the body and its Tip must be visible, with sketches and earlier features hidden.

## Packaging, install and detection
- **Layout:** `package.xml` and `freecad/hexilator/` (a namespace package) at the repo root. The repo root is the addon folder.
- **Restore check:** FreeCAD 1.1.4 imports a proxy's module during document restore only if it comes from an installed addon (a `Mod` folder); being on `sys.path` is not enough. A proxy in `freecad.<name>.<module>` passes, verified 2026-11-08.
- **Version:** `freecad.hexilator.__version__` (SemVer), the same as `package.xml`'s `<version>`; a test checks that they match. Releases are git tags `vX.Y.Z` on GitHub. Pushing master and tags is the user's call.
- **Install:** an install is a git checkout of a ref at `<user data>/Mod/Hexilator`.
  - The user data dir is `FreeCAD.getUserAppDataDir()`: `~/.local/share/FreeCAD/v1-1/` here, or `$FREECAD_USER_DATA` when that's set.
  - `mise-tasks/install` does it. It clones, or fetches and checks out, and skips the work when the checkout is already at the ref.
  - Source overrides: `HEXILATOR_SOURCE` (default `https://github.com/kazatronics/hexilator.git`; may be a local path such as `~/Work/Parts/addons/hexilator/.repo`) and `HEXILATOR_REF` (a tag or branch). These let Trellis test an untagged branch before a release.
- **Detection:** a file opened without the addon keeps its last shape, with `Proxy = None`, and recomputes silently with no error. A missing addon is therefore invisible. A user's tests should check `freecad.hexilator.__version__` against their pin; Trellis's do. Each feature also records `Version`.

## Tests
Tests run headless under `freecadcmd` with `mise run test`. The task points `FREECAD_USER_DATA` at a temporary folder with `Mod/Hexilator` linked to the worktree. Tests use `unittest`. `freecadcmd` exits 0 even when a script raises, so the runner sets its own exit code.
- **Core:**
  - lattice-line offsets and periods;
  - snapping of fields and keep-outs;
  - loop collapse;
  - fallback piece choice;
  - arc handling.
- **Feature, on a plate:**
  - a field on lattice lines: exact counts, and a volume against the analytic open area;
  - a field off the lattice, which snaps inward;
  - corners;
  - rectangular keep-outs (snapped) and round keep-outs (fallback);
  - `Whole` and `Free`;
  - `Angle` 30;
  - moving the anchor;
  - `Type`, `Depth`, `Reversed`;
  - expressions driven from a spreadsheet;
  - one valid solid;
  - save, then reopen and recompute in a new process;
  - `__version__` matching `package.xml`;
  - a performance smoke test.
- **Two-part:** tray and lid bodies split through one field, against a single-body grid.
- **GUI** (`mise run test-gui`, Xvfb, its own `FREECAD_USER_HOME`): open a file saved headless that contains a HexGrid in the full GUI, and check:
  - the view provider proxy and icon are present;
  - the body and Tip are visible, and the sketch and base feature are hidden;
  - there are no errors in the report view.

  Saves that must keep GUI view data also go through Xvfb.
- **Screenshots:** `mise run shot` (Xvfb) for visual review. Never use the user's FreeCAD window.

## Prior art
- SimpleHex (LGPL-2.1) is the closest existing tool: a sketch field with keep-outs, Whole/Clip modes, and no lattice snapping. Hexilator is Apache 2.0, so it can be read for ideas but no code may be copied.
- HexFill, the Honeycomb macro, Draft and PartDesign patterns and Lattice2 lack outlines, parametric output or clipping.
- The survey is Trellis's `tmp/hexgrid-research/REPORT.md` (2026-11-07). The facts used from it are recorded above.

## Open questions
- Snap loops that mix straight edges with arcs, e.g. a rounded-rectangle keep-out. In v0.1 the whole loop falls back.
- A toolbar command and a task panel, after v0.1.
