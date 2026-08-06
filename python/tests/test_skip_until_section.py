"""Unit tests for skip_until_section source transform (no manim invoke)."""

from __future__ import annotations

import pytest

from manim_dock.render import _apply_skip_until_section


SOURCE = '''\
from manim import *


class Demo(Scene):
    def construct(self):
        self.next_section("Title")
        self.play(Write(Text("t")))
        self.next_section(name="Body")
        self.play(Write(Text("b")))
        self.next_section("Cleanup")
        self.play(FadeOut(Group(*self.mobjects)))
'''


def test_apply_skip_until_section_marks_prior_only() -> None:
    out = _apply_skip_until_section(SOURCE, "Body")
    assert 'self.next_section("Title", skip_animations=True)' in out
    assert 'self.next_section(name="Body"' in out
    assert "skip_animations" not in out.split('name="Body"')[1].split("\n")[0]
    assert 'self.next_section("Cleanup")' in out
    assert 'self.next_section("Cleanup", skip_animations=True)' not in out


def test_apply_skip_until_section_updates_existing_flag() -> None:
    src = '''\
class Demo(Scene):
    def construct(self):
        self.next_section("Title", skip_animations=False)
        self.next_section("Body")
'''
    out = _apply_skip_until_section(src, "Body")
    assert "skip_animations=True" in out
    assert 'self.next_section("Body")' in out


def test_apply_skip_until_section_strips_skip_on_target() -> None:
    src = '''\
class Demo(Scene):
    def construct(self):
        self.next_section("Title")
        self.next_section("Body", skip_animations=True)
'''
    out = _apply_skip_until_section(src, "Body")
    assert 'self.next_section("Title", skip_animations=True)' in out
    assert 'self.next_section("Body")' in out
    assert "skip_animations=True)" not in out.split("Body")[1]


def test_apply_skip_until_section_missing_raises() -> None:
    with pytest.raises(ValueError, match="section not found"):
        _apply_skip_until_section(SOURCE, "Missing")
