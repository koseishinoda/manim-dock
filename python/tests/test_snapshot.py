"""Tests for Manim Stage snapshot transform + cache (Phase 12)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from manim_dock.snapshot import (
    inject_early_exit,
    snapshot_at_line,
    snapshot_cache_key,
)


SAMPLE = '''
from manim import *

class Demo(Scene):
    def construct(self):
        title = Text("Hello")
        self.play(Write(title))
        self.wait(0.5)
        self.play(FadeOut(title))
'''


def test_inject_after_write_line():
    lines = SAMPLE.splitlines()
    write_line = next(i for i, line in enumerate(lines, 1) if "Write(title)" in line)
    out = inject_early_exit(SAMPLE, write_line)
    assert "EndSceneEarlyException" in out
    assert "raise EndSceneEarlyException()" in out
    # Raise must appear after Write, before wait.
    raise_i = out.index("raise EndSceneEarlyException()")
    write_i = out.index("Write(title)")
    wait_i = out.index("self.wait")
    assert write_i < raise_i < wait_i


def test_inject_preserves_future_import_first():
    source = '''"""Doc."""
from __future__ import annotations
from manim import *

class Demo(Scene):
    def construct(self):
        self.play(Write(Text("x")))
'''
    out = inject_early_exit(source, 8)
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    # Docstring may be unparsed as a string expr first.
    future_i = next(i for i, ln in enumerate(lines) if ln.startswith("from __future__"))
    early_i = next(i for i, ln in enumerate(lines) if "EndSceneEarlyException" in ln and ln.startswith("from "))
    assert future_i < early_i
    compile(out, "<inject>", "exec")


def test_inject_at_construct_start_when_line_zero():
    out = inject_early_exit(SAMPLE, 0)
    construct = out.split("def construct")[1]
    body_start = construct.index(":") + 1
    head = construct[body_start : body_start + 120]
    assert "raise EndSceneEarlyException()" in head


def test_cache_key_stable_and_sensitive():
    a = snapshot_cache_key(SAMPLE, "Demo", 12, quality="l")
    b = snapshot_cache_key(SAMPLE, "Demo", 12, quality="l")
    assert a == b
    assert a != snapshot_cache_key(SAMPLE, "Demo", 13, quality="l")
    assert a != snapshot_cache_key(SAMPLE + "\n", "Demo", 12, quality="l")
    assert a != snapshot_cache_key(SAMPLE, "Other", 12, quality="l")


def test_snapshot_cache_hit_skips_manim(tmp_path: Path):
    key = snapshot_cache_key(SAMPLE, "Demo", 10, quality="l")
    png = tmp_path / f"{key}.png"
    # Minimal valid PNG (1x1)
    png.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
        )
    )
    with patch("manim_dock.snapshot.subprocess.run") as run:
        result = snapshot_at_line(
            tmp_path / "demo.py",
            "Demo",
            10,
            source=SAMPLE,
            cache_dir=tmp_path,
        )
        run.assert_not_called()
    assert result.ok
    assert result.cached
    assert result.png_path == str(png.resolve())
    assert result.width == 1
    assert result.height == 1


def test_snapshot_runs_manim_and_caches(tmp_path: Path):
    scene_file = tmp_path / "demo.py"
    scene_file.write_text(SAMPLE, encoding="utf-8")
    media_png = tmp_path / "media" / "images" / "Demo.png"
    media_png.parent.mkdir(parents=True)
    media_png.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d494844520000000200000002080600000072b60d"
            "240000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
        )
    )

    def fake_run(cmd, **kwargs):
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = f"File ready at '{media_png}'\n"
        proc.stderr = ""
        return proc

    with patch("manim_dock.snapshot.subprocess.run", side_effect=fake_run) as run:
        with patch(
            "manim_dock.snapshot.resolve_manim_cmd",
            return_value=["manim"],
        ):
            result = snapshot_at_line(
                scene_file,
                "Demo",
                10,
                source=SAMPLE,
                cache_dir=tmp_path / "cache",
            )
        assert run.called
        cmd = run.call_args.args[0]
        assert "-s" in cmd
        assert any(str(a).startswith("-q") for a in cmd)

    assert result.ok
    assert not result.cached
    assert result.png_path
    cached = Path(result.png_path)
    assert cached.is_file()
    assert cached.parent == tmp_path / "cache"

    # Second call hits cache.
    with patch("manim_dock.snapshot.subprocess.run") as run2:
        again = snapshot_at_line(
            scene_file,
            "Demo",
            10,
            source=SAMPLE,
            cache_dir=tmp_path / "cache",
        )
        run2.assert_not_called()
    assert again.ok and again.cached


def test_snapshot_timeout(tmp_path: Path):
    scene_file = tmp_path / "demo.py"
    scene_file.write_text(SAMPLE, encoding="utf-8")

    with patch(
        "manim_dock.snapshot.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=["manim"], timeout=1),
    ):
        with patch(
            "manim_dock.snapshot.resolve_manim_cmd",
            return_value=["manim"],
        ):
            result = snapshot_at_line(
                scene_file,
                "Demo",
                10,
                source=SAMPLE,
                cache_dir=tmp_path / "cache",
                timeout=1,
            )
    assert not result.ok
    assert "timed out" in (result.error or "")
