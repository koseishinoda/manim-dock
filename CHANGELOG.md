# Changelog

Versioning follows **git tags** (`v0.2.2`, …) and [GitHub Releases](https://github.com/koseishinoda/manim-dock/releases).

## 0.2.2

Public disclosure hygiene:

- Versioning by git tags only; drop V1/V2/V3 roadmap docs
- Untrack `.cursor/` (agents/rules/skills stay local)
- Remove personal validation checklist, assessment write-ups, cut-list, Nyquist plan/concat
- Trim README / contributor docs; keep Nyquist as a plain multi-scene example

## 0.2.1

Disclosure trim + Stage reliability:

- Drop obsolete Stage/layout/Doctor/Insert APIs (no dormant surfaces)
- Unified Stage & Timeline only; Manim stills; URI delivery; Konva removed
- Fix re-open Stage while panel already open (Outline section switch)
- Fix Render-from-Section to use bare `next_section` names

## 0.2.0

Stage stills, Timeline assist, Sideview handoff:

- **Stage:** Manim still at scrub (`snapshot_at_line`); plain `<img>`; keep last frame while capturing
- **Timeline:** duration / reorder patches; unified Stage & Timeline panel (`manimDock.openStageTimeline`)
- **Open in Sideview** handoff
- **Cuts (no dormant APIs):** Stage drag/align/Properties, Insert Wait/Play, Doctor, AST layout/scrub, Konva

## 0.0.2

- `manimDock.patchMode`; VSIX packaging; library browser; render-method; Timeline pacing depth

## 0.0.1

- Foundation: Outline, Stage, Timeline, extract, templates, section-aware render
