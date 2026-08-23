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

## Versioning

Ship via **git tags** and GitHub Releases (`v0.2.4`, …). Product history lives in [CHANGELOG.md](../CHANGELOG.md), not phase roadmaps.

## Related docs

- [sideview.md](./sideview.md), [invasion-test.md](./invasion-test.md), [patterns.md](./patterns.md)
