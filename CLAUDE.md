# Hexilator

A FreeCAD addon for parametric hex grids. See `README.md` for the goals.

## Rules for Claude
- **Everything about the addon lives in this repo:** design decisions, status and open questions. When something is learned or decided, update the relevant file here. Environment and tooling details belong in Claude's memory, not here.
- **Never commit tooling dependencies or binaries** (vendor dirs, virtualenvs, build output). Tool versions are pinned in `mise.toml`.
- **Mise tasks are file tasks:** executable shell scripts in `mise-tasks/`, with `#MISE` header comments for description and dependencies. Never put inline `[tasks]` in `mise.toml`.
- **Repo layout:** a bare repo at `../.repo` with one worktree per branch beside it. `master` is the main worktree and the default branch; it tracks `origin` (github.com/kazatronics/hexilator, public).
- **Issues and pull requests:** every problem or piece of work is a GitHub issue (`gh issue create`). Every change lands on master through a pull request from its branch, merged with a merge commit (squash and rebase are off). Never push to master directly: a ruleset blocks direct pushes, force pushes and deletion, and requires the CI `test` check. After a merge, update the local master with `git pull --ff-only`.
- **Conventional commits** for every commit, and for PR titles, which become the merge commits' subjects (`feat:`, `fix:`, `docs:`, `test:`, `ci:`, `build:`, `chore:`; `!` or a `BREAKING CHANGE:` footer for breaking changes, but only from 1.0 on: before 1.0, never use either, since the release workflow would bump to v1.0.0). The release workflow computes versions and tags from them. CI and the release flow are described in `DESIGN.md`, under Development process.
- **Tests run headless** under `freecadcmd`. Run them before reporting work, and report what fails. Nothing merges into master without tests for the change and a passing `mise run test`.
- **The user's FreeCAD window belongs to the user.** Never drive it (no freecad MCP GUI tools). For screenshots, run FreeCAD off-screen under Xvfb with its own `FREECAD_USER_HOME`.
- **Licence:** Apache 2.0 (`LICENSE.md`).

## First user
The Trellis project (`~/Work/Parts/Trellis`) installs this addon at a pinned version through a mise task. Its hex grid rule is in Trellis's `CLAUDE.md`, under Design principles.
