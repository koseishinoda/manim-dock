# Changelog

## 0.2.1

Disclosure trim + Stage reliability:

- Drop obsolete Stage/layout/Doctor/Insert APIs (no dormant surfaces)
- Unified Stage & Timeline only; Manim stills; URI delivery; Konva removed
- Fix re-open Stage while panel already open (Outline section switch)
- Fix Render-from-Section to use bare `next_section` names
- Nyquist assessment fixture + cut-list docs

## 0.2.0

V3 — Stage stills, Timeline assist, Sideview handoff (see [docs/v3-roadmap.md](docs/v3-roadmap.md)):

- **Stage:** Manim still at scrub (`snapshot_at_line`); plain `<img>`; keep last frame while capturing
- **Timeline:** duration / reorder patches; unified Stage & Timeline panel (`manimDock.openStageTimeline`)
- **Open in Sideview** handoff
- **Cuts (no dormant APIs):** Stage drag/align/Properties, Insert Wait/Play, Doctor, AST layout/scrub, Konva

## 0.0.2

Phase 6–8 (historical; many Stage-edit surfaces later cut):

- `manimDock.patchMode`; VSIX; align/scrub/font/lag; library browser; render-method
- See [docs/v2-roadmap.md](docs/v2-roadmap.md)

## 0.0.1

- V1 foundation: Outline, Stage, Timeline, extract, templates, section-aware render
- See [docs/v1-architecture-plan.md](docs/v1-architecture-plan.md)
