# Hexilator

A FreeCAD addon for parametric hex grids. See `README.md` for the goals.

## Rules for Claude
- **Everything about the addon lives in this repo:** design decisions, status and open questions. When something is learned or decided, update the relevant file here. Environment and tooling details belong in Claude's memory, not here.
- **Never commit tooling dependencies or binaries** (vendor dirs, virtualenvs, build output). Tool versions are pinned in `mise.toml`.
- **Mise tasks are file tasks:** executable shell scripts in `mise-tasks/`, with `#MISE` header comments for description and dependencies. Never put inline `[tasks]` in `mise.toml`.
- **Repo layout:** a bare repo at `../.repo` with one worktree per branch beside it. `master` is the main worktree and the default branch; it's pushed to `origin` (github.com/kazatronics/hexilator, public).
- **Merges into master are never fast-forwards** (`--no-ff`; set on the bare repo for master), so each branch lands as one merge commit.
- **Tests run headless** under `freecadcmd`. Run them before reporting work, and report what fails.
- **The user's FreeCAD window belongs to the user.** Never drive it (no freecad MCP GUI tools). For screenshots, run FreeCAD off-screen under Xvfb with its own `FREECAD_USER_HOME`.
- **Licence:** Apache 2.0 (`LICENSE.md`).

## First user
The Trellis project (`~/Work/Parts/Trellis`) installs this addon at a pinned version through a mise task. Its hex grid rule is in Trellis's `CLAUDE.md`, under Design principles.
