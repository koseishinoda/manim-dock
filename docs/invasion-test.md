# Invasion test

Manim Dock must **assist** ManimCE workflows, never cage them.

## Must pass

- [x] No required `ManimDockScene` (or similar) base class
- [x] No hidden runtime hooks for final `manim` render
- [x] No parallel scene IR as source of truth
- [x] Project still renders if the extension is uninstalled
- [x] UI is never mandatory to edit or run scenes

`examples/lesson_lib` and extract output are **plain ManimCE** — no Dock imports required at render time.

## G1–G6

1. **Version matrix** — declare ManimCE support; degrade gracefully; no private Manim fork
2. **Opaque mobjects** — unknown/plugin types → proxy + jump-to-source
3. **Doctor** — actionable Python / manim / LaTeX / ffmpeg errors
4. **Relative edits** — prefer `buff` / `shift` / relative layout; no absolute-coord explosion
5. **Audience honesty** — for Manim writers, not “no Python needed”
6. **Uninstall metric** — incomplete parse never blocks coding

## Patch red flags

- Regenerating whole `construct()` from the GUI
- Rewriting `MathTex` / `{{part}}` topology
- Extension-specific APIs in generated snippets
