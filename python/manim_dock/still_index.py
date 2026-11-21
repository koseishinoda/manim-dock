"""Background Stage still index over Timeline beats (P1).

Derived cache only — never project truth. Keys reuse ``snapshot_cache_key``
(prefix digest) so interactive ``snapshot_at_line`` and the indexer share PNGs.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from manim_dock.snapshot import (
    SnapshotResult,
    _capture_inprocess,
    _png_size,
    inject_still_saves_and_early_exit,
    local_import_fingerprint,
    snapshot_at_line,
    snapshot_cache_key,
)
from manim_dock.stage_transform import (
    construct_prefix_canonical_many,
    elide_unfocused_section_bodies,
    resolve_stage_elide_section,
    strip_other_scene_classes,
    strip_prior_section_animations,
)
from manim_dock.timeline import SceneTimeline, parse_file_timeline, parse_scene_timeline

INDEXABLE_KINDS = frozenset({"play", "wait", "add", "next_section"})

# Interactive ``still_get`` rebuilds beats on every cursor move; cache by
# (path, scene, quality, source digest) so PNG hits stay cheap on long files.
_BEATS_CACHE: OrderedDict[tuple[str, str, str, str], list["IndexBeat"]] = (
    OrderedDict()
)
_BEATS_CACHE_MAX = 12


@dataclass
class IndexBeat:
    ordinal: int
    kind: str
    label: str
    source_line: int  # 1-based end line (capture / cache anchor)
    section: str
    cache_key: str
    start_line: int = 0  # 1-based start line of the statement (multi-line plays)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StillGetResult:
    ok: bool
    path: str = ""
    scene: str = ""
    line: int = 0
    beat: IndexBeat | None = None
    png_path: str | None = None
    width: int | None = None
    height: int | None = None
    cached: bool = False
    captured: bool = False
    engine: str = ""
    error: str | None = None
    index_cached: int = 0
    index_total: int = 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.beat is not None:
            d["beat"] = self.beat.to_dict()
        return d


@dataclass
class StillIndexResult:
    ok: bool
    path: str = ""
    scene: str = ""
    built: int = 0
    skipped: int = 0
    cached: int = 0
    total: int = 0
    complete: bool = False
    next_ordinal: int | None = None
    section: str = ""
    error: str | None = None
    last_engine: str = ""
    beats: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StillIndexStatus:
    ok: bool
    path: str = ""
    scene: str = ""
    cached: int = 0
    total: int = 0
    complete: bool = False
    next_ordinal: int | None = None
    section: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _timeline(
    file_path: str | Path,
    scene_name: str,
    source: str | None,
) -> SceneTimeline:
    path = Path(file_path)
    if isinstance(source, str):
        return parse_scene_timeline(source, str(path), scene_name)
    return parse_file_timeline(path, scene_name)


def _read_source(file_path: str | Path, source: str | None) -> str:
    if isinstance(source, str):
        return source
    return Path(file_path).read_text(encoding="utf-8")


def _source_digest(src: str) -> str:
    return hashlib.sha256(src.encode("utf-8")).hexdigest()


def clear_beats_cache() -> None:
    """Drop memoized index beats (tests / source reload)."""
    _BEATS_CACHE.clear()


def build_index_beats(
    file_path: str | Path,
    scene_name: str,
    *,
    source: str | None = None,
    quality: str = "l",
) -> list[IndexBeat]:
    """Timeline events → index beats with prefix cache keys."""
    path = Path(file_path).resolve()
    src = _read_source(path, source)
    q = (quality or "l").strip().lower()
    cache_key = (str(path), scene_name, q, _source_digest(src))
    cached = _BEATS_CACHE.get(cache_key)
    if cached is not None:
        _BEATS_CACHE.move_to_end(cache_key)
        return cached

    tl = _timeline(path, scene_name, src)
    events: list[tuple[Any, int, int, str]] = []
    lines: list[int] = []
    for ev in tl.events:
        if ev.kind not in INDEXABLE_KINDS:
            continue
        start = int(ev.range.start_line or 0)
        end = int(ev.range.end_line or start or 0)
        if end < 1 and ev.kind != "next_section":
            continue
        if start < 1:
            start = end
        section = ev.section or ""
        events.append((ev, start, end, section))
        lines.append(end)

    prefixes = construct_prefix_canonical_many(src, scene_name, lines)
    imports = local_import_fingerprint(path, src)

    beats: list[IndexBeat] = []
    for ev, start, end, section in events:
        # Same gate as snapshot_at_line: body-elide only for focus() sections.
        elide = resolve_stage_elide_section(
            src, scene_name, end, section_hint=section or None
        )
        key = snapshot_cache_key(
            src,
            scene_name,
            end,
            quality=quality,
            file_path=path,
            stage_elide_section=elide,
            prefix=prefixes.get(end),
            imports=imports,
        )
        beats.append(
            IndexBeat(
                ordinal=len(beats),
                kind=ev.kind,
                label=ev.label,
                source_line=end,
                section=section,
                cache_key=key,
                start_line=start,
            )
        )

    _BEATS_CACHE[cache_key] = beats
    _BEATS_CACHE.move_to_end(cache_key)
    while len(_BEATS_CACHE) > _BEATS_CACHE_MAX:
        _BEATS_CACHE.popitem(last=False)
    return beats


def _png_cached(cache_dir: Path, key: str) -> Path | None:
    png = cache_dir / f"{key}.png"
    if png.is_file() and png.stat().st_size > 0:
        return png
    return None


def prune_orphan_stills(cache_dir: Path, beats: list[IndexBeat]) -> int:
    """Delete content-addressed PNGs not referenced by the current beat ladder."""
    keep = {b.cache_key for b in beats}
    removed = 0
    if not cache_dir.is_dir():
        return 0
    for png in cache_dir.glob("*.png"):
        stem = png.stem
        if len(stem) != 64:
            continue
        if any(c not in "0123456789abcdef" for c in stem):
            continue
        if stem in keep:
            continue
        try:
            png.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def _counts(beats: list[IndexBeat], cache_dir: Path) -> tuple[int, int, int | None, str]:
    cached = 0
    next_ord: int | None = None
    section = ""
    for b in beats:
        if _png_cached(cache_dir, b.cache_key):
            cached += 1
        elif next_ord is None:
            next_ord = b.ordinal
            section = b.section
    return cached, len(beats), next_ord, section


def beat_for_line(beats: list[IndexBeat], line: int) -> IndexBeat | None:
    """Map editor/scrub line → index beat (aligned with ``inject_early_exit``).

    Prefer the beat whose statement **contains** ``line`` (so a multi-line
    ``self.play`` under the cursor is not mapped to the previous beat).
    Otherwise use the last beat with ``source_line <= line``.
    """
    if line < 1:
        return beats[0] if beats else None
    containing: IndexBeat | None = None
    last_le: IndexBeat | None = None
    for b in beats:
        start = b.start_line if b.start_line > 0 else b.source_line
        end = b.source_line
        if start <= line <= end:
            containing = b
        if end <= line:
            last_le = b
        elif containing is None and last_le is not None and end > line:
            # Beats are ordered by end line; once past the cursor and we already
            # have a predecessor, further beats cannot be last_le.
            break
    return containing if containing is not None else last_le


def still_index_status(
    file_path: str | Path,
    scene_name: str,
    *,
    source: str | None = None,
    quality: str = "l",
    cache_dir: str | Path | None = None,
) -> StillIndexStatus:
    path = Path(file_path).resolve()
    try:
        beats = build_index_beats(
            path, scene_name, source=source, quality=quality
        )
    except Exception as exc:  # noqa: BLE001
        return StillIndexStatus(
            ok=False, path=str(path), scene=scene_name, error=str(exc)
        )
    if cache_dir is None:
        return StillIndexStatus(
            ok=False,
            path=str(path),
            scene=scene_name,
            error="cache_dir is required",
        )
    root = Path(cache_dir)
    root.mkdir(parents=True, exist_ok=True)
    cached, total, next_ord, section = _counts(beats, root)
    return StillIndexStatus(
        ok=True,
        path=str(path),
        scene=scene_name,
        cached=cached,
        total=total,
        complete=total > 0 and cached >= total,
        next_ordinal=next_ord,
        section=section,
    )


def still_get(
    file_path: str | Path,
    scene_name: str,
    line: int,
    *,
    source: str | None = None,
    quality: str = "l",
    cache_dir: str | Path | None = None,
    capture_on_miss: bool = True,
    timeout: int | None = None,
) -> StillGetResult:
    """Lookup still for cursor/scrub line; optionally capture that beat on miss."""
    path = Path(file_path).resolve()
    if cache_dir is None:
        return StillGetResult(
            ok=False,
            path=str(path),
            scene=scene_name,
            line=line,
            error="cache_dir is required",
        )
    root = Path(cache_dir)
    root.mkdir(parents=True, exist_ok=True)

    try:
        src = _read_source(path, source)
        beats = build_index_beats(
            path, scene_name, source=src, quality=quality
        )
    except Exception as exc:  # noqa: BLE001
        return StillGetResult(
            ok=False,
            path=str(path),
            scene=scene_name,
            line=line,
            error=str(exc),
        )

    cached_n, total, _, _ = _counts(beats, root)
    beat = beat_for_line(beats, line)
    until = beat.source_line if beat is not None else line

    hit = _png_cached(root, beat.cache_key) if beat is not None else None
    if hit is None and beat is None:
        # No timeline beats — fall through to raw line snapshot key.
        elide = resolve_stage_elide_section(
            src, scene_name, until, section_hint=None
        )
        key = snapshot_cache_key(
            src,
            scene_name,
            until,
            quality=quality,
            file_path=path,
            stage_elide_section=elide,
        )
        hit = _png_cached(root, key)

    if hit is not None:
        w, h = _png_size(hit)
        return StillGetResult(
            ok=True,
            path=str(path),
            scene=scene_name,
            line=line,
            beat=beat,
            png_path=str(hit.resolve()),
            width=w,
            height=h,
            cached=True,
            engine="cache",
            index_cached=cached_n,
            index_total=total,
        )

    if not capture_on_miss:
        return StillGetResult(
            ok=False,
            path=str(path),
            scene=scene_name,
            line=line,
            beat=beat,
            error="still not indexed",
            index_cached=cached_n,
            index_total=total,
        )

    snap = snapshot_at_line(
        path,
        scene_name,
        until,
        source=src,
        quality=quality,
        cache_dir=root,
        timeout=timeout,
        # Hint for focus-aware section body elision (ignored unless focus()).
        skip_until_section=beat.section if beat and beat.section else None,
    )
    cached_n2, total2, _, _ = _counts(beats, root)
    return StillGetResult(
        ok=snap.ok,
        path=str(path),
        scene=scene_name,
        line=line,
        beat=beat,
        png_path=snap.png_path,
        width=snap.width,
        height=snap.height,
        cached=False,
        captured=bool(snap.ok),
        engine=snap.engine or "",
        error=snap.error,
        index_cached=cached_n2,
        index_total=total2,
    )


def _prepare_ladder_source(
    source: str,
    scene_name: str,
    *,
    keep_section: str,
    until_line: int,
    line_to_key: dict[int, str],
    mode: str,
) -> str:
    """Build temp source for a one-pass ladder (``mode``: body|anims|full).

    Still-saves + early-exit share one AST pass so beat line numbers stay valid.
    Elision/strip run afterward (they key off section names, not lines).
    """
    code = inject_still_saves_and_early_exit(
        source, scene_name, line_to_key, until_line
    )
    if mode == "body" and keep_section:
        code = elide_unfocused_section_bodies(code, scene_name, keep_section)
    elif mode == "anims" and keep_section:
        code = strip_prior_section_animations(code, scene_name, keep_section)
    return strip_other_scene_classes(code, scene_name)


def capture_section_ladder(
    file_path: str | Path,
    scene_name: str,
    beats: list[IndexBeat],
    *,
    source: str,
    quality: str = "l",
    cache_dir: str | Path,
) -> tuple[int, str, str | None]:
    """Capture many beats in **one** construct (phase 1.5).

    Returns ``(built_count, engine, error)``. Interactive Stage must not pay
    O(prefix)×N; the idle/index path fills a section once.
    """
    if not beats:
        return 0, "", None
    path = Path(file_path).resolve()
    root = Path(cache_dir)
    root.mkdir(parents=True, exist_ok=True)
    ordered = sorted(beats, key=lambda b: (b.source_line, b.ordinal))
    keep = ordered[0].section or ""
    until = ordered[-1].source_line
    line_to_key = {b.source_line: b.cache_key for b in ordered}
    # Only body/anim strip when focus() marks this section — otherwise a
    # successful early still-save under body elision caches a preamble-only PNG.
    elide_ok = bool(
        keep
        and resolve_stage_elide_section(
            source, scene_name, until, section_hint=keep
        )
    )
    write_cwd = path.parent
    last_png = root / f"{ordered[-1].cache_key}.png"
    base = SnapshotResult(
        ok=False,
        path=str(path),
        scene=scene_name,
        active_until_line=until,
        quality=quality,
        cache_key=ordered[-1].cache_key,
    )

    for mode in ("body", "anims", "full"):
        if mode in ("body", "anims") and not elide_ok:
            continue
        try:
            transformed = _prepare_ladder_source(
                source,
                scene_name,
                keep_section=keep if elide_ok else "",
                until_line=until,
                line_to_key=line_to_key,
                mode=mode,
            )
        except (SyntaxError, ValueError) as exc:
            if mode == "full":
                return 0, "", str(exc)
            continue
        result = _capture_inprocess(
            write_cwd=write_cwd,
            write_path=path,
            transformed=transformed,
            scene_name=scene_name,
            quality=quality,
            cached_png=last_png,
            base=base,
            ladder_cache_dir=root,
        )
        if result is None:
            return 0, "", "manim not available in-process"
        built = sum(
            1 for b in ordered if _png_cached(root, b.cache_key) is not None
        )
        # Body elision often dies mid-section after a few saves — keep those
        # PNGs and continue with anim-strip / full to fill the rest.
        if built >= len(ordered):
            return built, result.engine or "inprocess", None
        if mode == "full":
            if built > 0:
                return built, result.engine or "inprocess", None
            return 0, result.engine or "", result.error or "ladder wrote no PNGs"
    return 0, "", "ladder failed"


def still_index(
    file_path: str | Path,
    scene_name: str,
    *,
    source: str | None = None,
    quality: str = "l",
    cache_dir: str | Path | None = None,
    max_beats: int = 1,
    prefer_section: str | None = None,
    timeout: int | None = None,
) -> StillIndexResult:
    """Capture missing stills (section-priority).

    ``max_beats < 1`` means: fill the preferred section (or first missing
    section) in **one ladder pass** — O(prefix) once, not once per beat.
    """
    path = Path(file_path).resolve()
    if cache_dir is None:
        return StillIndexResult(
            ok=False,
            path=str(path),
            scene=scene_name,
            error="cache_dir is required",
        )

    root = Path(cache_dir)
    root.mkdir(parents=True, exist_ok=True)

    try:
        src = _read_source(path, source)
        beats = build_index_beats(
            path, scene_name, source=src, quality=quality
        )
    except Exception as exc:  # noqa: BLE001
        return StillIndexResult(
            ok=False, path=str(path), scene=scene_name, error=str(exc)
        )

    missing = [b for b in beats if _png_cached(root, b.cache_key) is None]
    if prefer_section:
        first = [b for b in missing if b.section == prefer_section]
        rest = [b for b in missing if b.section != prefer_section]
        ordered = first + rest
    else:
        ordered = missing

    built = 0
    last_engine = ""
    last_section = prefer_section or ""

    # Section ladder: one construct → many beat PNGs (fundamental index path).
    if ordered and max_beats < 1:
        section = ordered[0].section
        batch = [b for b in ordered if b.section == section]
        last_section = section
        n, engine, err = capture_section_ladder(
            path,
            scene_name,
            batch,
            source=src,
            quality=quality,
            cache_dir=root,
        )
        if err and n == 0:
            cached, total, next_ord, sec = _counts(beats, root)
            return StillIndexResult(
                ok=False,
                path=str(path),
                scene=scene_name,
                built=0,
                skipped=len(beats) - len(missing),
                cached=cached,
                total=total,
                complete=False,
                next_ordinal=batch[0].ordinal,
                section=section,
                error=err,
                last_engine=engine,
            )
        built = n
        last_engine = engine
    elif ordered and max_beats > 1 and ordered[0].section == ordered[
        min(max_beats, len(ordered)) - 1
    ].section:
        batch = ordered[:max_beats]
        last_section = batch[0].section
        n, engine, err = capture_section_ladder(
            path,
            scene_name,
            batch,
            source=src,
            quality=quality,
            cache_dir=root,
        )
        if err and n == 0:
            cached, total, next_ord, sec = _counts(beats, root)
            return StillIndexResult(
                ok=False,
                path=str(path),
                scene=scene_name,
                built=0,
                skipped=len(beats) - len(missing),
                cached=cached,
                total=total,
                complete=False,
                next_ordinal=batch[0].ordinal,
                section=batch[0].section,
                error=err,
                last_engine=engine,
            )
        built = n
        last_engine = engine
    else:
        limit = max(1, max_beats)
        for b in ordered[:limit]:
            last_section = b.section
            snap = snapshot_at_line(
                path,
                scene_name,
                b.source_line,
                source=src,
                quality=quality,
                cache_dir=root,
                timeout=timeout,
                skip_until_section=b.section or None,
            )
            if not snap.ok:
                cached, total, next_ord, section = _counts(beats, root)
                return StillIndexResult(
                    ok=False,
                    path=str(path),
                    scene=scene_name,
                    built=built,
                    skipped=len(beats) - len(missing),
                    cached=cached,
                    total=total,
                    complete=False,
                    next_ordinal=b.ordinal,
                    section=b.section,
                    error=snap.error or "snapshot failed",
                    last_engine=snap.engine or "",
                )
            built += 1
            last_engine = snap.engine or last_engine

    cached, total, next_ord, section = _counts(beats, root)
    complete = total > 0 and cached >= total
    if complete:
        prune_orphan_stills(root, beats)
    return StillIndexResult(
        ok=True,
        path=str(path),
        scene=scene_name,
        built=built,
        skipped=len(beats) - len(missing),
        cached=cached,
        total=total,
        complete=complete,
        next_ordinal=next_ord,
        section=last_section or section,
        last_engine=last_engine,
        beats=[b.to_dict() for b in beats[:8]],  # small sample for debug
    )
