# Invasion test

Manim Dock must **assist** ManimCE workflows, never cage them.

## Must pass

- [ ] No required `ManimDockScene` (or similar) base class
- [ ] No hidden runtime hooks for final `manim` render
- [ ] No parallel scene IR as source of truth
- [ ] Project still renders if the extension is uninstalled
- [ ] UI is never mandatory to edit or run scenes

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
