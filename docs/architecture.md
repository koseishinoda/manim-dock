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

## Phase map

| Phase | Deliverable |
|-------|-------------|
| 0–5 | V1 (`v0.0.1`) — Outline, Stage, Timeline, Properties, extract, templates |
| 6–8 | V2 (`v0.0.2`) — `patchMode`, VSIX, align/scrub/font/lag, P07–P10, library browser, render-method |
| 9+ | V3 (`v0.2.0`) — see [v3-roadmap.md](./v3-roadmap.md) |

See [v2-roadmap.md](./v2-roadmap.md), [v3-roadmap.md](./v3-roadmap.md).

## Subagents

Project agents in `.cursor/agents/`: `invasion-guardian`, `creator-ux`, `manim-affinity`, `sidecar-python`, `surface-validator`.

`surface-validator` owns fit-to-frame / overflow regressions and maintains [surface-validator-log.md](../.cursor/agents/surface-validator-log.md).

## V1 plan (in-repo)

Plans live in-repo (never plan-only in chat):

- [v1-architecture-plan.md](./v1-architecture-plan.md) — V1 (`v0.0.1`)
- [v2-roadmap.md](./v2-roadmap.md) — V2 (`v0.0.2`)
- [v3-roadmap.md](./v3-roadmap.md) — V3 (`v0.2.0`)

See also: [sideview.md](./sideview.md), [version-matrix.md](./version-matrix.md), [invasion-test.md](./invasion-test.md).
