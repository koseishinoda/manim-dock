# Architecture

```text
VS Code text editor  +  Manim Dock (Outline → Stage & Timeline)
         │
         ▼
 Extension host (TypeScript)
         │
         ▼
 Python sidecar (stdio JSON / inline -c)
   ├─ outline (ast read)
   ├─ timeline (ast read + timing VM)
   ├─ snapshot_at_line (Manim still for Stage)
   ├─ surgical timing patches (libcst propose → confirm → apply)
   ├─ method extract → plain library module
   └─ manim CLI orchestration (QL / section-/method-scoped render)
         │
         ▼
 User .py  +  manim  +  media/
```

## Principles

- Companion panels, not a Custom Editor that replaces `.py`
- Python / ManimCE is the only source of truth; no parallel scene IR
- Stage shows **Manim stills** (plain `<img>` via webview URI); Timeline owns duration/reorder
- Cut surfaces are deleted (no dormant layout/scrub/doctor/align APIs)
- Invest in Outline / Stage stills / Timeline; keep video preview thin (Skill viewer / Sideview for finished video)

## Phase map

| Phase | Deliverable |
|-------|-------------|
| 0–5 | V1 (`v0.0.1`) — see [v1-architecture-plan.md](./v1-architecture-plan.md) (historical) |
| 6–8 | V2 (`v0.0.2`) — see [v2-roadmap.md](./v2-roadmap.md) (historical) |
| 9+ | V3 (`v0.2.0`) — still-only Stage + trims; [v3-roadmap.md](./v3-roadmap.md) |

## Subagents

Project agents in `.cursor/agents/`: `invasion-guardian`, `creator-ux`, `manim-affinity`, `sidecar-python`, `surface-validator`.

`surface-validator` owns Stage fit / progressive UI regressions — [surface-validator-log.md](../.cursor/agents/surface-validator-log.md).

## Related docs

- [sideview.md](./sideview.md), [invasion-test.md](./invasion-test.md)
- [cut-list-stage-edit.md](./cut-list-stage-edit.md) — Stage edit / Insert / Doctor cuts
- [assessments/nyquist-stability-usability.md](./assessments/nyquist-stability-usability.md)
