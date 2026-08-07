"""Tests for library_catalog against examples/lesson_lib/patterns.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from manim_dock.library_catalog import list_library_helpers, _module_import_name

ROOT = Path(__file__).resolve().parents[2]
PATTERNS = ROOT / "examples" / "lesson_lib" / "patterns.py"


def test_module_import_name_prefers_lesson_lib() -> None:
    assert _module_import_name(PATTERNS) == "lesson_lib"
    assert _module_import_name("/tmp/my_helpers.py") == "my_helpers"


def test_list_library_helpers_patterns() -> None:
    helpers = list_library_helpers(PATTERNS)
    names = [h["name"] for h in helpers]
    assert "title_card" in names
    assert "brace_callout" in names
    assert "axes_intro" in names
    assert "compare_cards" in names
    assert "succession_beat" in names
    # Constants are not functions.
    assert "PRIMARY" not in names

    by_name = {h["name"]: h for h in helpers}
    brace = by_name["brace_callout"]
    assert brace["signature"].startswith("brace_callout(")
    assert "scene" in brace["signature"]
    assert "P07" in brace["doc"]
    assert brace["insert"] == (
        "from lesson_lib import brace_callout\nbrace_callout(self, $0)"
    )


def test_list_library_helpers_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        list_library_helpers("/no/such/library.py")
