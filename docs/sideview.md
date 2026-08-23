# Coexistence with Manim Sideview

Manim Dock and [Manim Sideview](https://marketplace.visualstudio.com/items?itemName=Rickaym.manim-sideview) solve different jobs. Install both if you want; they do not fight over project format or source of truth.

## Ownership split

| Concern | Manim Dock | Sideview |
|---------|------------|----------|
| Outline (scenes / sections / plays) | Owns | — |
| Stage (Manim still at scrub) | Owns | — |
| Timeline (pacing / `run_time` / `wait` patches) | Owns | — |
| Surgical Python patches (confirm-diff) | Owns | — |
| Educational snippets / templates / extract | Owns | Gallery insert (different) |
| Rich video preview / player UX | Thin built-in only | Owns |
| Scene render trigger | QL / section-/method-aware via sidecar | Its own run pipeline |

**Dock does not rebuild Sideview.** Finished-video polish stays with Sideview / Skill viewer; Dock invests in Outline + Stage stills + Timeline.

## How to use both

1. Edit normal ManimCE `.py` in the editor (shared source of truth).
2. Use Dock Outline / Stage & Timeline for stills, pacing, and patches.
3. Use Dock **Render Scene (QL)** (or section-/method-aware sidecar render) for a fast check from Dock.
4. Use Sideview when you want its richer preview, quality controls, or gallery insert workflow.
5. Or run **Manim Dock: Open in Sideview** — Dock activates Sideview’s `manim-sideview.run` when installed, otherwise offers the Marketplace link.

Outputs land under Manim’s usual `media/` tree. Either extension may invoke `manim`; neither requires the other.

## No conflict rules

- No Custom Editor lock on `.py` — both stay companions.
- No Dock-required base class or parallel scene IR.
- Uninstalling Dock (or Sideview) leaves a valid Manim project.
- Prefer one render trigger at a time to avoid racing the same scene’s `media/` outputs.

See also: [architecture.md](./architecture.md), [v3-roadmap.md](./v3-roadmap.md).
