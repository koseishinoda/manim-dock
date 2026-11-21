# Stage still index (design)

**Status:** P0 + P1 + section render + P2-lite landed (`v0.2.11`)  

**Problem:** Stage/`snapshot_at_line` is O(construct prefix). On long educational scenes this is the interactive bottleneck.  
**Fixture:** `Nyquist_Stability_Criteria` / `scene3_assemble.py` → `Scene3_Nyquist_ArgumentPos` (ManimCE 0.19.2).

### P0 landed (substrate)

- Prefix-digest cache keys (`SNAPSHOT_VERSION=v4-prefix`) — edits after the cursor / in other scene classes no longer invalidate earlier stills.
- In-process last-frame capture when Manim is importable; CLI `-s` fallback.
- Persistent `python -m manim_dock serve` worker for Stage snapshots (warm imports); one-shot `-c` fallback.

### P1 landed (still index)

- `manim_dock.still_index` — Timeline beats → shared prefix-keyed PNGs; `still_get` / `still_index` / `still_index_status` RPCs.
- Stage background fill (setting `manimDock.stage.refresh`: `onIdle` | `onSave` | `manual`); section-priority; pauses while interactive capture runs.
- Chrome shows `Indexed n/total` while the ladder builds.

## Evidence (2026-11-21)

| Workload | Wall |
|----------|------|
| Cold `import manim` | ~0.8 s |
| Import project helpers | ~1.7 s |
| Stage → first play (L1109) | ~3.5 s |
| Stage → mid section (L1378) | ~28 s |
| Stage → last play (L1699), warm `media/Tex`, PNG miss | ~19 s |
| Stage PNG cache hit | ~0.06 s |
| Render QL `skip_until` last section | ~26 s |
| Render QL ≈ whole ArgumentPos | ~218 s |

In-process `cProfile` of late Stage (`save_last_frame`, warm Tex):

- `construct` ≈ 30 s; `Scene.play` ≈ **20 s** even with last-frame mode.
- Dominant costs: `MathTex`/`Tex` / SVG init, and **`mobject.copy` / `deepcopy` inside `Transform.begin` / `begin_animations`**.
- Conclusion: `-s` skips *pixel encoding*, not play setup. Section `skip_animations` helps **render encode**, not Stage depth cost.

So the interactive fix is **stop re-paying the prefix on every Stage request**, not “skip animations harder.”

## Goals / non-goals

**Goals**

1. Scrub / reopen Stage on an unchanged scene → **O(1)** still (~cache hit).
2. Edit inside one section → recompute **dirty suffix only** (ideally current section first).
3. Stills remain **real Manim** frames (product law).
4. Cache is disposable; uninstall-safe; `.py` stays SoT.

**Non-goals**

- Parallel editable scene IR / approximate Stage overlay.
- Required `ManimDockScene` or render-time hooks in user projects.
- Replacing Sideview / Skill viewer for finished video.
- Scene-state pickle as phase-1 dependency (optional later).

## Architecture

```text
Editor / Timeline scrub / Outline jump
         │
         ▼
 Extension host
   ├─ request still(scene, beat|line)     → index lookup
   ├─ on save / idle                     → enqueue index job
   └─ render current section (default)   → warm worker
         │
         ▼
 Sidecar (stdio)  +  Manim worker (long-lived child)
   ├─ timeline beats (existing AST)
   ├─ still index (content-addressed PNGs)
   ├─ snapshot_at_line (fallback / single miss)
   └─ render_scene (section-/method-scoped)
```

Layering:

| Layer | Role |
|-------|------|
| **0 Warm worker** | One process: Manim + project imports already loaded; in-process `Scene.render()` (no fresh CLI each click). |
| **1 Still index** | Background ladder of PNGs at Timeline beats; Stage serves lookups. |
| **1b Section render** | Default QL path = current `next_section`; full scene explicit. Same worker. |
| **2 Checkpoints** (optional) | Resume construct from section boundary if dirty-section re-index still too slow. |

## Beat model

Reuse Timeline events (`play` / `wait` / `add` / `next_section`) from `manim_dock.timeline`.

Each **index beat** is a capture point after an event completes (same semantics as today’s “still after cursor statement”).

```text
BeatId = {
  scene,                 # class name
  kind,                  # play | wait | add | next_section | construct_end
  ordinal,               # 0-based among beats in construct expansion
  source_line,           # 1-based end line of the anchoring statement
  section,               # enclosing next_section label ("" before first)
}
```

Stage scrub maps cursor/scrub-line → **last beat with `source_line <= cursor`** (same rule as `inject_early_exit` anchoring).

## Cache key schema

Do **not** key on the whole file hash (today’s `snapshot_cache_key`). One late-file edit must not kill early stills.

### Prefix digest

For beat *k* in scene *S*:

```text
prefix_digest(S, k) = sha256(
  index_version || quality ||
  scene_name ||
  canonical_ast_bytes(construct_prefix_through_beat_k) ||
  import_fingerprint
)
```

- **`construct_prefix_through_beat_k`:** AST of `construct` (and any inlined method bodies Timeline already expands) sliced through the beat’s statement, `ast.dump`/`unparse` normalized — **not** raw file text (whitespace-only edits should not thrash).
- **`import_fingerprint`:** hash of mtimes + paths for the scene file and local imports it loads (`shared.py`, `*_helpers.py`, …), so helper edits invalidate. Start simple: scene file + same-directory non-`media` imports referenced by `ast`; refine later with modulegraph if needed.
- **`index_version`:** bump when capture semantics change (e.g. `v1`).

PNG path:

```text
{storage}/still-index/{prefix_digest}.png
```

Optional sidecar JSON: `{ beat, scene, source_line, quality, created_at }`.

Storage: extension `globalStorage` and/or project `.manim_dock/still-index/` (gitignored). Never required for plain `manim` CLI.

### Lookup

```text
hit  = exists(prefix_digest(S, beat_for(line)))
miss → show last-good dimmed; enqueue capture for that beat (and optionally backfill ladder)
```

## Invalidation

On document change (debounced):

1. Parse new timeline beats for the active scene.
2. Find smallest `k` such that `prefix_digest(S, k)` ≠ digest recorded for that ordinal (or beat identity changed).
3. Delete index entries for beats `>= k` in that scene.
4. Keep beats `< k` (early ladder survives late edits).
5. Schedule re-index from `k` (prefer **current section → rest of scene** so Stage near the cursor recovers first).

Cursor-only moves: **no** invalidation; lookup only.

## Index build algorithm

```text
build_index(scene, from_beat=k):
  ensure warm worker
  for beat in beats[k:]:
    if cached(prefix_digest(beat)): continue
    capture_still(until_line=beat.source_line)   # real Manim, -s / save_last_frame
    write PNG under prefix_digest
    report progress (beat i / n) to Stage
```

**Capture implementation (phase 1):** existing `inject_early_exit` + in-process render in the worker (same semantics as `snapshot_at_line`). Paying O(prefix) once per beat during idle is acceptable; interactive path must not.

**Capture optimization (phase 1.5, same worker session):** when building a contiguous ladder in one process, avoid restarting from line 0 for every beat if a safe fast-forward exists. Phase 1 may still restart per beat (correct, slower index build). Phase 2 checkpoints make ladder builds incremental.

## Warm worker

- Long-lived child of the sidecar (or sidecar itself if single-threaded work is OK).
- Protocol: JSON-RPC methods e.g. `still_get`, `still_index`, `render`.
- `cwd` = scene directory; `sys.path` includes project roots the user already uses.
- On helper/scene import fingerprint change: **restart worker** (stale modules).
- Crash isolation: worker dies → sidecar respawns; Stage falls back to one-shot snapshot.

## Stage / Timeline UX

- Unchanged: one command `manimDock.openStageTimeline`; Stage = `<img>`.
- Scrub / cursor → `still_get` (lookup). Miss → dim last-good + “Updating still…” (existing pattern).
- Status: `Indexed 12/36 · section “LHP conjugate pair”` while background build runs.
- Optional setting: `manimDock.stage.refresh` = `onIdle` (default) | `onSave` | `manual`.
- **Do not** spawn a full CLI snapshot on every debounced cursor tick once the index exists; only `still_get` + targeted miss fill.

## Render (paired, not identical)

| Today | Target |
|-------|--------|
| Full-scene QL easy; section via flag | **Done:** primary play = **Render Section (QL)** (`section_only`); full scene explicit |
| `skip_until_section` / `section_only` in sidecar | `section_only` skips before **and** after the chapter |
| Cold CLI each run | Same warm worker (Stage); render still one-shot CLI for now |
| Partial-movie reuse | Rely on Manim cache; later hash section bodies for “unchanged → skip encode” |

Section render still runs construct prefix with `skip_animations` (≈ Stage late cost + encode). That is why section default matters (~26 s vs ~218 s on ArgumentPos), and why worker + later checkpoints help both paths.

## Invasion test

- [ ] Index is **derived cache** only — not an authoring document.
- [ ] No Dock imports required in user scenes for render or Stage.
- [ ] No required Scene subclass / render hooks.
- [ ] Uninstall: delete extension storage; project still runs with plain ManimCE.
- [ ] Capture path uses ManimCE public entry (`Scene.render` / CLI-equivalent config), not monkeypatched user classes.
- [ ] One Stage surface / one command ID unchanged.

## Phased delivery

### P0 — Substrate (unblocks everything)

1. Prefix-digest keys for `snapshot_at_line` (keep early stills across late edits).
2. Warm Manim worker + in-process last-frame capture (cut ~2–3 s fixed + CLI overhead).
3. Stage: lookup-by-prefix before capture; keep dimmed last-good on miss.

### P1 — Still index

1. Build beat ladder from Timeline on idle/save.
2. `still_get(scene, line)` → beat → PNG.
3. Dirty-from-beat invalidation; section-priority rebuild.
4. Progress in Stage status.

**Success (Nyquist ArgumentPos):** scrub unchanged → &lt;100 ms; after edit in last section, Stage near cursor recovers after **one section re-index**, not 19–40 s full-prefix every scrub.

### P2 — Optional checkpoints

**P2-lite (landed):** Stage captures for a beat in section *N* apply `skip_animations` on prior `next_section`s before the early-exit still (same final frame, less prior play work). Full mobject-state pickle resume remains deferred (fragile across Manim versions).

### P3 — Play fast-forward research

cProfile shows `Transform.begin` deepcopy ≈ large fraction of Stage time under `-s`. Investigate a **worker-only** “apply animation end state without deepcopy” path for index capture. Upstream-friendly; never required in user projects. Do not block P0–P1 on this.

## API sketch (sidecar)

```text
still_get({ path, scene, line, quality }) ->
  { ok, png_path, beat, cached, index_state }

still_index({ path, scene, quality, from_line? }) ->
  { ok, built, skipped, invalidated_from }

still_index_status({ path, scene }) ->
  { complete, current, total, section }

render({ path, scene, quality, skip_until_section?, method? })
  # existing; prefer skip_until_section from Outline selection
```

## Open questions

1. Index storage: user-global vs per-workspace (lean per-workspace for import fingerprint clarity).
2. Method-expanded Timeline vs source lines: digests must use the same expansion Timeline uses for beat lists.
3. Multi-class files (`scene3_assemble.py`): index per scene class; switching scenes switches ladder.
4. Whether manual “Refresh Stage” should force rebuild from beat 0 or from current section only (default: current section).

## Related

- [architecture.md](./architecture.md)
- [invasion-test.md](./invasion-test.md)
- [decisions.md](./decisions.md) — Stage remains Manim stills in one Stage & Timeline webview
