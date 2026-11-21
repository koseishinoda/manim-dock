"""Tests for Stage still index (P1)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from manim_dock.still_index import (
    beat_for_line,
    build_index_beats,
    still_get,
    still_index,
    still_index_status,
)

SAMPLE = '''
from manim import *

class Demo(Scene):
    def construct(self):
        self.next_section("Intro")
        title = Text("Hello")
        self.play(Write(title))
        self.wait(0.5)
        self.next_section("Outro")
        self.play(FadeOut(title))
'''


def test_build_index_beats_ordered():
    beats = build_index_beats("demo.py", "Demo", source=SAMPLE, quality="l")
    kinds = [b.kind for b in beats]
    assert "next_section" in kinds
    assert "play" in kinds
    assert "wait" in kinds
    assert beats[0].ordinal == 0
    assert beats[-1].ordinal == len(beats) - 1
    # Keys are stable for the same prefix.
    again = build_index_beats("demo.py", "Demo", source=SAMPLE, quality="l")
    assert [b.cache_key for b in beats] == [b.cache_key for b in again]


def test_beat_for_line_picks_last_le():
    beats = build_index_beats("demo.py", "Demo", source=SAMPLE, quality="l")
    play = next(b for b in beats if b.kind == "play")
    assert beat_for_line(beats, play.source_line) is play
    later = beat_for_line(beats, play.source_line + 5)
    assert later is not None and later.source_line >= play.source_line
    # Cursor above the first beat → no beat yet (caller uses raw line).
    assert beat_for_line(beats, 1) is None


def test_still_get_cache_hit(tmp_path: Path):
    beats = build_index_beats(
        tmp_path / "demo.py", "Demo", source=SAMPLE, quality="l"
    )
    play = next(b for b in beats if b.kind == "play")
    png = tmp_path / f"{play.cache_key}.png"
    png.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
        )
    )
    with patch("manim_dock.still_index.snapshot_at_line") as snap:
        result = still_get(
            tmp_path / "demo.py",
            "Demo",
            play.source_line,
            source=SAMPLE,
            cache_dir=tmp_path,
            capture_on_miss=True,
        )
        snap.assert_not_called()
    assert result.ok and result.cached
    assert result.engine == "cache"
    assert result.index_total == len(beats)
    assert result.index_cached >= 1


def test_still_index_builds_one_missing(tmp_path: Path):
    scene = tmp_path / "demo.py"
    scene.write_text(SAMPLE, encoding="utf-8")

    def fake_snap(path, scene_name, until, **kwargs):
        from manim_dock.snapshot import SnapshotResult, snapshot_cache_key

        src = SAMPLE
        key = snapshot_cache_key(
            src, scene_name, until, quality="l", file_path=path
        )
        out = Path(kwargs["cache_dir"]) / f"{key}.png"
        out.write_bytes(
            bytes.fromhex(
                "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
                "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
            )
        )
        return SnapshotResult(
            ok=True,
            path=str(path),
            scene=scene_name,
            active_until_line=until,
            cache_key=key,
            png_path=str(out),
            width=1,
            height=1,
            engine="cli",
        )

    with patch("manim_dock.still_index.snapshot_at_line", side_effect=fake_snap):
        status0 = still_index_status(
            scene, "Demo", source=SAMPLE, cache_dir=tmp_path, quality="l"
        )
        assert status0.ok and not status0.complete and status0.total > 0
        r1 = still_index(
            scene,
            "Demo",
            source=SAMPLE,
            cache_dir=tmp_path,
            max_beats=1,
            prefer_section="Intro",
        )
        assert r1.ok and r1.built == 1
        assert r1.cached == 1
        r2 = still_index(
            scene,
            "Demo",
            source=SAMPLE,
            cache_dir=tmp_path,
            max_beats=50,
        )
        assert r2.ok and r2.complete
        assert r2.cached == r2.total
