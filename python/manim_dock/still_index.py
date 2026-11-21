"""Background Stage still index over Timeline beats (P1).

Derived cache only — never project truth. Keys reuse ``snapshot_cache_key``
(prefix digest) so interactive ``snapshot_at_line`` and the indexer share PNGs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from manim_dock.snapshot import _png_size, snapshot_at_line, snapshot_cache_key
from manim_dock.timeline import SceneTimeline, parse_file_timeline, parse_scene_timeline

INDEXABLE_KINDS = frozenset({"play", "wait", "add", "next_section"})


@dataclass
class IndexBeat:
    ordinal: int
    kind: str
    label: str
    source_line: int
    section: str
    cache_key: str

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


def build_index_beats(
    file_path: str | Path,
    scene_name: str,
    *,
    source: str | None = None,
    quality: str = "l",
) -> list[IndexBeat]:
    """Timeline events → index beats with prefix cache keys."""
    src = _read_source(file_path, source)
    tl = _timeline(file_path, scene_name, src)
    path = Path(file_path)
    beats: list[IndexBeat] = []
    for ev in tl.events:
        if ev.kind not in INDEXABLE_KINDS:
            continue
        line = int(ev.range.end_line or ev.range.start_line or 0)
        if line < 1 and ev.kind != "next_section":
            continue
        key = snapshot_cache_key(
            src,
            scene_name,
            line,
            quality=quality,
            file_path=path,
        )
        beats.append(
            IndexBeat(
                ordinal=len(beats),
                kind=ev.kind,
                label=ev.label,
                source_line=line,
                section=ev.section or "",
                cache_key=key,
            )
        )
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
    """Last index beat with ``source_line <= line`` (Stage cursor semantics)."""
    if line < 1:
        return beats[0] if beats else None
    best: IndexBeat | None = None
    for b in beats:
        if b.source_line <= line:
            best = b
        else:
            break
    return best


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
        key = snapshot_cache_key(
            src, scene_name, until, quality=quality, file_path=path
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
    """Capture up to ``max_beats`` missing stills (section-priority when set)."""
    path = Path(file_path).resolve()
    if cache_dir is None:
        return StillIndexResult(
            ok=False,
            path=str(path),
            scene=scene_name,
            error="cache_dir is required",
        )
    if max_beats < 1:
        max_beats = 1

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
    for b in ordered[:max_beats]:
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
