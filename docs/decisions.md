# Locked decisions

| Topic | Choice |
|-------|--------|
| Name | Manim Dock (`manim-dock`) |
| License | MIT |
| Preview | Thin built-in video + coexist with Manim Sideview |
| Patches | `manimDock.patchMode`: `confirm` (default) or `auto` (WorkspaceEdit + editor Undo) |
| Stage | Konva |
| Python edits | libcst for patches; `ast` OK for outline/read |
| Runtime | ManimCE (not ManimGL) for V1 — verified locally with Manim Community v0.20.1 |
| Jupyter | Out of V1 scope |

See also: [invasion-test.md](./invasion-test.md), [architecture.md](./architecture.md), [version-matrix.md](./version-matrix.md).
