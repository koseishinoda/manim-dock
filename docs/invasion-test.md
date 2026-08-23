# Invasion test

Manim Dock must **assist** ManimCE workflows, never cage them.

## Must pass

- [x] No required `ManimDockScene` (or similar) base class
- [x] No hidden runtime hooks for final `manim` render
- [x] No parallel scene IR as source of truth
- [x] Project still renders if the extension is uninstalled
- [x] UI is never mandatory to edit or run scenes

`examples/lesson_lib` and extract output are **plain ManimCE** — no Dock imports required at render time.

## Principles

1. Declare ManimCE support; degrade gracefully when tools are missing
2. Prefer `buff` / `shift` / relative layout in timing patches — no absolute-coord explosion
3. Audience: Manim writers, not “no Python needed”
4. Incomplete parse never blocks coding
5. Cut features are deleted (no dormant APIs)

## Patch red flags

- Regenerating whole `construct()` from the GUI
- Rewriting `MathTex` / `{{part}}` topology
- Extension-specific APIs in generated snippets
