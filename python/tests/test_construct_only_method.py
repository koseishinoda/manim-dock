"""Unit tests for construct-only method transform (no manim invoke)."""

from __future__ import annotations

import pytest

from manim_dock.render import _construct_only_method


SOURCE = '''\
from manim import *


class Demo(Scene):
    def construct(self):
        self.title_card()
        self.body()

    def title_card(self):
        self.play(Write(Text("t")))

    def body(self):
        self.play(Write(Text("b")))
'''


def test_construct_only_rewrites_body_keeps_methods() -> None:
    out = _construct_only_method(SOURCE, "Demo", "body")
    assert "def title_card(self):" in out
    assert "def body(self):" in out
    # construct should only call body
    construct_block = out.split("def construct(self):", 1)[1].split("def ", 1)[0]
    assert "self.body()" in construct_block
    assert "self.title_card()" not in construct_block
    assert 'Write(Text("t"))' in out  # other method preserved


def test_construct_only_missing_scene() -> None:
    with pytest.raises(ValueError, match="scene not found"):
        _construct_only_method(SOURCE, "Missing", "body")


def test_construct_only_missing_method() -> None:
    with pytest.raises(ValueError, match="method not found"):
        _construct_only_method(SOURCE, "Demo", "missing")


def test_construct_only_rejects_construct_name() -> None:
    with pytest.raises(ValueError, match="cannot be 'construct'"):
        _construct_only_method(SOURCE, "Demo", "construct")
