# Changelog

## 0.2.0

V3 — Stage fidelity, Timeline insert, Sideview handoff, doctor matrix (see [docs/v3-roadmap.md](docs/v3-roadmap.md)):

- Stage layout: ctor-chain unwrap; approximate `next_to` / light `arrange` heuristics
- Timeline / commands: **Insert Wait**, **Insert Play Scaffold** (libcst confirm-diff)
- **Open in Sideview** handoff (`manim-sideview.run` or Marketplace hint)
- Doctor: `manim_support` probe (declared ManimCE range + detected version)

## 0.0.2

Phase 6–8 (trust, deeper layout/timing, facilitation) + validation hardening:

- `manimDock.patchMode`: `confirm` (default) or `auto` (Undo with Ctrl/Cmd+Z); status bar + **Set Patch Mode**
- Installable VSIX via `npm run package`
- Properties: `font_size`, `lag_ratio`; Align/Distribute (Stage multi-select)
- Stage: multi-select toolbar; frame-locked camera; shift coalesce; scrub override sync with Timeline
- Timeline: section-scoped beat reorder; whole-section group swap; scrub highlight sync
- Patterns P07–P10 + `lesson_lib` helpers + snippets
- Library browser; render from method
- See [docs/v2-roadmap.md](docs/v2-roadmap.md)

## 0.0.1

- V1: Outline, Doctor, Stage, Timeline, Properties, extract, templates, section-aware render
- See [docs/v1-architecture-plan.md](docs/v1-architecture-plan.md)
