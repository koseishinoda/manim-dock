# Locked decisions

| Topic | Choice |
|-------|--------|
| Name | Manim Dock (`manim-dock`) |
| License | MIT |
| Preview | Thin built-in video + coexist with Manim Sideview / Skill viewer |
| Patches | `manimDock.patchMode`: `confirm` (default) or `auto` (WorkspaceEdit + editor Undo) — **duration / reorder only** |
| Stage | Manim still (`snapshot_at_line`) in unified Stage & Timeline webview; one command `manimDock.openStageTimeline` |
| Python edits | libcst for patches; `ast` OK for outline/timeline read |
| Runtime | ManimCE (not ManimGL) |
| Jupyter | Out of scope |
| Cut surfaces | Deleted (no dormant APIs): Stage drag/align/Properties, Insert Wait/Play, Doctor, AST Stage layout/scrub |

See also: [invasion-test.md](./invasion-test.md), [architecture.md](./architecture.md), [cut-list-stage-edit.md](./cut-list-stage-edit.md).
