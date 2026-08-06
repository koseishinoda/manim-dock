"""Tests for scaffold_example."""

from __future__ import annotations

from pathlib import Path

from manim_dock.scaffold import scaffold_example


def test_scaffold_example_copies_lesson(tmp_path: Path) -> None:
    dest = tmp_path / "out"
    result = scaffold_example(dest)
    assert result["ok"] is True
    assert (dest / "lesson.py").is_file()
    assert "lesson.py" in result["copied"]
    # Second call should skip existing files.
    again = scaffold_example(dest)
    assert again["ok"] is True
    assert again["copied"] == []
    assert "lesson.py" in again["skipped"]
