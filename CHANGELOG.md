# Changelog

Versioning follows **git tags** (`v0.2.11`, …) and [GitHub Releases](https://github.com/koseishinoda/manim-dock/releases).

## 0.2.11

Stage speed + section-scoped render:

- **Stage still index:** prefix-digest PNG cache, warm `manim_dock serve` worker, in-process last-frame capture, background beat ladder (`manimDock.stage.refresh`)
- **Render Section (QL)** as primary play (current `next_section`); **Render Full Scene** explicit; Timeline section **▶** button
- Section-only transform skips prior chapters and **early-exits** before the next section
- Warm-worker render; still-index pauses/aborts on scrub; orphan still prune when index completes
- Design note: [docs/stage-still-index.md](docs/stage-still-index.md)

## 0.2.10

- Timeline / Stage / Outline treat `self.add(...)` as static beats (scrub spacing only; not duration-editable or reorderable)

## 0.2.9

- Outline scene checkboxes + **Render Concatenated Video**: re-render checked scenes (file order) at chosen quality, write `concat.txt` + `final.mp4` (requires `ffmpeg` on PATH)

## 0.2.8

- Stage still captures **after** the statement under the cursor (incl. multi-line `self.play` / `MathTex`), not the previous command

## 0.2.7

- Fix Stage/Timeline `spawn E2BIG` on large scene buffers: pass source via stdin (not argv) and drop oversized env vars from the sidecar child

## 0.2.6

- Fix Stage snapshot injecting `raise EndSceneEarlyException()` at module scope when the cursor is on the last line of a scene class (or on class-body attributes) — raise only inside `construct()`

## 0.2.5

- Fix render preview picking the wrong media: parse rich-wrapped `File ready at` paths, accept stills (PNG), never fall back to an unrelated scene's mp4

## 0.2.4

- Fix `manimDock.pythonPath` precedence: workspace / project `.venv` before user-level path (stops leftover global paths from other repos winning)
- Marketplace icon (`media/icon.png`)

## 0.2.3

- README Stage & Timeline screenshot (Nyquist shift still)

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
