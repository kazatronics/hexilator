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
| `Profile` | LinkSub | | The field: a sketch (or another 2D object whose shape lies in its own XY plane) in the same body. Outer loops are fields; inner loops are keep-outs. Islands inside keep-outs are fields again. Sub-element names are ignored. |
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
   - Edges that snap onto the same line merge, and an edge that shrinks to nothing (a small step between two edges that snap to one line) is dropped, so its neighbours meet directly.
   - A loop that really collapses when snapped is also kept as drawn, with a warning. That means an edge reverses, two neighbouring edges end up parallel on different lines, or the loop self-intersects or loses its area.
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
  - Point containment counts ray crossings, half-open in y. That is only consistent if both sides of every joint agree on its coordinates exactly, so loops weld their joints to one shared point and arcs keep their end points as given (issue #5).
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
- **Visibility:** `make_hex_grid` leaves the new feature visible, and hides the profile sketch and the previous feature, as the GUI does. After a save, the body and its Tip must be visible, with sketches and earlier features hidden.
- **Headless saves lose visibility.** FreeCAD 1.1.4 opens a file saved by `freecadcmd` (no `GuiDocument.xml`) with every object hidden, the Body included. Verified 2026-11-08 with a control file holding only a Body and a box, so it isn't the addon's doing. Files meant for the user's GUI must be saved from the GUI (off-screen under Xvfb), which is what the GUI test checks.

## Packaging, install and detection
- **Layout:** `package.xml` and `freecad/hexilator/` (a namespace package) at the repo root. The repo root is the addon folder.
- **Restore check:** FreeCAD 1.1.4 imports a proxy's module during document restore only if it comes from an installed addon (a `Mod` folder); being on `sys.path` is not enough. A proxy in `freecad.<name>.<module>` passes, verified 2026-11-08.
- **Version:** `package.xml`'s `<version>` is the single source. `freecad.hexilator.__version__` reads it at import, so the two can't differ; a test checks the format. On master it stays `0.0.0`. Each release tag `vX.Y.Z` points at a release commit off master that sets it, so a checkout of the tag reports `__version__ == "X.Y.Z"` (see Development process).
- **Install:** an install is a git checkout of a ref (a tag, a branch or a full commit SHA) at `<user data>/Mod/Hexilator`.
  - The user data dir is `FreeCAD.getUserAppDataDir()`: `~/.local/share/FreeCAD/v1-1/` here, or `$FREECAD_USER_DATA` when that's set.
  - `mise-tasks/install` does it. It clones, or fetches and checks out, and skips the work when the checkout is already at the ref.
  - It clears git's repo-local environment (`GIT_DIR`, `GIT_INDEX_FILE`, …) first, so it works when run from another repo's git hook, without touching that repo (issue #3).
  - Source overrides: `HEXILATOR_SOURCE` (default `https://github.com/kazatronics/hexilator.git`; may be a local path such as `~/Work/Parts/addons/hexilator/.repo`) and `HEXILATOR_REF` (a tag, a branch, which is followed to its latest commit, or a full 40-character commit SHA, which pins one commit before tags exist). These let Trellis test an untagged branch before a release.
- **Detection:** a file opened without the addon keeps its last shape, with `Proxy = None`, and recomputes silently with no error. A missing addon is therefore invisible. A user's tests should check `freecad.hexilator.__version__` against their pin; Trellis's do. Each feature also records `Version`.

## Development process
Set by the user on 2026-11-08: conventional commits, CI and automated releases (via Trellis); then issues, pull requests and a protected master.
- **Issues:** every problem or piece of work is a GitHub issue, including problems Trellis reports (with its repro details).
- **Pull requests:** every change lands on master through a PR, from a branch in its own worktree. PRs are merged with a merge commit, never squashed or rebased.
  - The merge commit's subject is the PR title and its body is the PR description, so **PR titles are conventional commits**.
  - A PR that fixes an issue says `Fixes #N`.
  - Merged branches are deleted.
- **Master is protected** by a ruleset:
  - no direct pushes (changes come through PRs);
  - no force pushes;
  - no deletion;
  - the CI `test` check must pass.
- **Conventional commits** for every commit, merge commits included, since the release workflow reads them: `feat:`, `fix:`, `test:`, `docs:`, `ci:`, `build:`, `chore:`, `refactor:`, `perf:`. From 1.0 on, a breaking change takes `!` or a `BREAKING CHANGE:` footer. Before 1.0 (the user's rule, 2026-11-08) neither is used, because the tag action would turn it into a major bump to v1.0.0; 1.0 is released deliberately.
- **Tests:** written alongside the code. Nothing lands on master without tests for the change, and `mise run test` passes before a PR is merged.
- **CI** (`.github/workflows/ci.yml`): on pull requests, and called by the release workflow.
  - **Job `test`:** `mise run lint`, `mise run test` and `mise run test-gui` (under `xvfb-run`).
  - **FreeCAD:** the official 1.1.4 AppImage, extracted and checked against its SHA256 file by `mise run fetch-freecad`. CI uses the same mise tasks as local runs.
- **Releases** (`.github/workflows/release.yml`, on pushes to master, i.e. merged PRs), after CI passes:
  1. `mathieudutour/github-tag-action@v7` in dry-run mode computes the next version and its changelog from the conventional commits since the last tag. It uses `default_bump: false`, so `chore:`, `docs:`, `test:` and `ci:` alone don't release. With no tags yet, the first `feat:` gives v0.1.0.
  2. A **release commit** `chore(release): vX.Y.Z` sets `<version>` and `<date>` in `package.xml`. Its parent is the master commit being released. It is made with the GitHub git-data API and is **not on any branch**: master stays protected and untouched, and the commit is reachable only through its tag. The API makes it as the workflow's own identity, so no address is written into the repo.
  3. The tag action tags the release commit `vX.Y.Z` (`custom_tag`, `commit_sha`).
  4. `gh release create` publishes the GitHub release with the changelog.

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
- **GUI** (`mise run test-gui`): full FreeCAD under Xvfb with its own `FREECAD_USER_HOME`, in two stages.
  - **headless:** open a file saved by `freecadcmd`. The HexGrid must get its view provider, icon and tree children, recompute after an edit, and leave no errors in the report view. Then build a HexGrid in the GUI and save the file from the GUI.
  - **reopen:** open the GUI-saved file. The body and its Tip must be visible and the sketch and base feature hidden, with no errors.
- **Screenshots:** `mise run shot` (Xvfb) for visual review. Never use the user's FreeCAD window.

## Prior art
- SimpleHex (LGPL-2.1) is the closest existing tool: a sketch field with keep-outs, Whole/Clip modes, and no lattice snapping. Hexilator is Apache 2.0, so it can be read for ideas but no code may be copied.
- HexFill, the Honeycomb macro, Draft and PartDesign patterns and Lattice2 lack outlines, parametric output or clipping.
- The survey is Trellis's `tmp/hexgrid-research/REPORT.md` (2026-11-07). The facts used from it are recorded above.

## Open questions
- The CI recipe was checked locally on 2026-11-08: the 1.1.4 AppImage passes the headless suite, and passes the GUI test in an `ubuntu:24.04` container with `ci.yml`'s apt packages. `xvfb-run` needs a 24-bit screen there, so `test-gui` sets `-screen 0 1600x1200x24`.
- Snap loops that mix straight edges with arcs, e.g. a rounded-rectangle keep-out. In v0.1 the whole loop falls back.
- A toolbar command and a task panel, after v0.1.
