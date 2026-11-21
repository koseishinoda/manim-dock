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
   ├─ still index (proposed: beat PNGs + warm worker — see stage-still-index.md)
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

## Performance (Stage / render)

Long scenes re-executing `construct` from the top on every Stage miss are unacceptable (measured on Nyquist `ArgumentPos`: ~19–40 s late-cursor miss vs ~0.06 s cache hit). The proposed fix is a **background still index** over Timeline beats plus a warm Manim worker; section-scoped QL remains the default render iteration path. Design: [stage-still-index.md](./stage-still-index.md).

## Versioning

Ship via **git tags** and GitHub Releases (`v0.2.5`, …). Product history lives in [CHANGELOG.md](../CHANGELOG.md), not phase roadmaps.

## Related docs

- [stage-still-index.md](./stage-still-index.md), [sideview.md](./sideview.md), [invasion-test.md](./invasion-test.md), [patterns.md](./patterns.md)
