# Architecture (Phase 0+)

```text
VS Code text editor  +  Manim Dock views (Outline → Stage → Timeline)
         │
         ▼
 Extension host (TypeScript)
         │
         ▼
 Python sidecar (stdio JSON-RPC)
   ├─ outline / scene-view model (read)
   ├─ layout view model (AST heuristics)
   ├─ surgical patches (libcst propose → confirm-diff → apply)
   ├─ method extract → plain library module (P15)
   ├─ doctor probes
   └─ manim CLI orchestration (QL / section-aware render)
         │
         ▼
 User .py  +  manim  +  media/
```

## Principles

- Companion panels, not a Custom Editor that replaces `.py`
- Scene view model is a **transient view**, never project truth
- Stage uses Konva; Manim frame convention: height 8, 16:9, origin center, +y up
- Invest in Stage/Timeline; keep video preview thin

## Phase map (V1 = `v0.0.1`)

| Phase | Deliverable |
|-------|-------------|
| 0 | Scaffold, outline parse, Outline view, doctor stub |
| 1 | Educational snippets + templates + QL render + thin preview |
| 2 | Stage (Konva) + Properties + shift/buff/scale confirm-diff |
| 3 | Timeline pacing + reorder + approximate scrub |
| 4 | Library extract + harden |
| 5 | Cross-surface selection sync + extract guards |

## Subagents

Project agents in `.cursor/agents/`: `invasion-guardian`, `creator-ux`, `manim-affinity`, `sidecar-python`, `surface-validator`.

`surface-validator` owns fit-to-frame / overflow regressions and maintains [surface-validator-log.md](../.cursor/agents/surface-validator-log.md).

## V1 plan (in-repo)

The full V1 architecture plan lives in-repo at [v1-architecture-plan.md](./v1-architecture-plan.md) — never plan-only in chat. Delivery status and historical phase text are kept there.

See also: [sideview.md](./sideview.md), [version-matrix.md](./version-matrix.md), [invasion-test.md](./invasion-test.md).
