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
   └─ manim CLI orchestration (QL render)
         │
         ▼
 User .py  +  manim  +  media/
```

## Principles

- Companion panels, not a Custom Editor that replaces `.py`
- Scene view model is a **transient view**, never project truth
- Stage uses Konva; Manim frame convention: height 8, 16:9, origin center, +y up
- Invest in Stage/Timeline; keep video preview thin

## Phase map

| Phase | Deliverable |
|-------|-------------|
| 0 | Scaffold, outline parse, Outline view, doctor stub |
| 1 | Educational snippets + QL render command + thin preview |
| 2 | Stage (Konva) + confirm-diff relative `shift` patches |
| 3 | Timeline pacing edits (`run_time` / `wait`) |
| 4 | Library extract + harden |
| 5 | Cross-surface selection sync + extract guards *(landed)* |

## Subagents

Project agents in `.cursor/agents/`: `invasion-guardian`, `creator-ux`, `manim-affinity`, `sidecar-python`, `surface-validator`.

`surface-validator` owns fit-to-frame / overflow regressions and maintains [surface-validator-log.md](../.cursor/agents/surface-validator-log.md).

See also: [version-matrix.md](./version-matrix.md), [invasion-test.md](./invasion-test.md).
