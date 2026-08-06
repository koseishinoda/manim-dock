# Coexistence with Manim Sideview

Manim Dock and [Manim Sideview](https://marketplace.visualstudio.com/items?itemName=Rickaym.manim-sideview) solve different jobs. Install both if you want; they do not fight over project format or source of truth.

## Ownership split

| Concern | Manim Dock | Sideview |
|---------|------------|----------|
| Outline (scenes / sections / plays) | Owns | — |
| Stage (layout proxies, relative patches) | Owns | — |
| Timeline (pacing / `run_time` / `wait`) | Owns | — |
| Surgical Python patches (confirm-diff) | Owns | — |
| Educational snippets / templates / extract | Owns | Gallery insert (different) |
| Rich video preview / player UX | Thin built-in only | Owns |
| Scene render trigger | QL / section-aware via sidecar | Its own run pipeline |

**Dock does not rebuild Sideview.** Preview polish stays with Sideview; Dock invests in Stage + Timeline + structure.

## How to use both

1. Edit normal ManimCE `.py` in the editor (shared source of truth).
2. Use Dock Outline / Stage / Timeline for layout, pacing, and patches.
3. Use Dock **Render Scene (QL)** (or section-aware sidecar render) when you want a fast check from Dock.
4. Use Sideview when you want its richer preview, quality controls, or gallery insert workflow.

Outputs land under Manim’s usual `media/` tree. Either extension may invoke `manim`; neither requires the other.

## No conflict rules

- No Custom Editor lock on `.py` — both stay companions.
- No Dock-required base class or parallel scene IR.
- Uninstalling Dock (or Sideview) leaves a valid Manim project.
- Prefer one render trigger at a time to avoid racing the same scene’s `media/` outputs.

See also: [architecture.md](./architecture.md), [v1-architecture-plan.md](./v1-architecture-plan.md).
