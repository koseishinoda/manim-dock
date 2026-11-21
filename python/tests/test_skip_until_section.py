"""Unit tests for skip_until_section source transform (no manim invoke)."""

from __future__ import annotations

import pytest

from manim_dock.render import _apply_section_only, _apply_skip_until_section


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

MULTI = '''\
from manim import *


class SceneA(Scene):
    def construct(self):
        self.next_section("Intro")
        self.play(Write(Text("a-intro")))
        self.next_section("Body")
        self.play(Write(Text("a-body")))


class SceneB(Scene):
    def construct(self):
        self.next_section("Intro")
        self.play(Write(Text("b-intro")))
        self.next_section("Body")
        self.play(Write(Text("b-body")))
        self.next_section("Outro")
        self.play(Write(Text("b-outro")))
'''


def test_apply_skip_until_section_marks_prior_only() -> None:
    out = _apply_skip_until_section(SOURCE, "Body", "Demo")
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
    out = _apply_skip_until_section(src, "Body", "Demo")
    assert "skip_animations=True" in out
    assert 'self.next_section("Body")' in out


def test_apply_skip_until_section_strips_skip_on_target() -> None:
    src = '''\
class Demo(Scene):
    def construct(self):
        self.next_section("Title")
        self.next_section("Body", skip_animations=True)
'''
    out = _apply_skip_until_section(src, "Body", "Demo")
    assert 'self.next_section("Title", skip_animations=True)' in out
    assert 'self.next_section("Body")' in out
    assert "skip_animations=True)" not in out.split("Body")[1]


def test_apply_skip_until_section_missing_raises() -> None:
    with pytest.raises(ValueError, match="section not found"):
        _apply_skip_until_section(SOURCE, "Missing", "Demo")


def test_apply_section_only_skips_prior_and_early_exits() -> None:
    out = _apply_section_only(SOURCE, "Body", "Demo")
    assert 'self.next_section("Title", skip_animations=True)' in out
    assert 'self.next_section(name="Body"' in out
    assert "skip_animations" not in out.split('name="Body"')[1].split("\n")[0]
    assert "raise EndSceneEarlyException()" in out
    assert "from manim.utils.exceptions import EndSceneEarlyException" in out
    # Later section body is truncated away.
    assert "Cleanup" not in out
    assert "FadeOut" not in out


def test_section_only_scopes_to_requested_scene() -> None:
    """Duplicate section titles across scenes must not rewrite the sibling."""
    out = _apply_section_only(MULTI, "Body", "SceneB")
    # Module-level import is fine; SceneA body must stay intact.
    scene_a = out.split("class SceneA", 1)[1].split("class SceneB", 1)[0]
    scene_b = out.split("class SceneB", 1)[1]
    assert "skip_animations" not in scene_a
    assert "raise EndSceneEarlyException()" not in scene_a
    assert 'Write(Text("a-body"))' in scene_a
    assert 'self.next_section("Intro")' in scene_a
    assert 'self.next_section("Body")' in scene_a
    # SceneB: prior Intro skipped; Body kept; Outro truncated.
    assert 'self.next_section("Intro", skip_animations=True)' in scene_b
    assert 'self.next_section("Body")' in scene_b
    assert 'Write(Text("b-body"))' in scene_b
    assert "raise EndSceneEarlyException()" in scene_b
    assert "Outro" not in scene_b
    assert "b-outro" not in scene_b


def test_section_only_does_not_match_sibling_scene_section() -> None:
    with pytest.raises(ValueError, match="section not found in scene 'SceneA'"):
        _apply_section_only(MULTI, "Outro", "SceneA")