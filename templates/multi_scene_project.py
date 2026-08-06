"""Multi-scene project stub — two Scene classes in one file."""

from manim import *


class IntroScene(Scene):
    def construct(self):
        title = Text("Part 1 — Intro", font_size=40)
        self.play(Write(title))
        self.wait(0.5)


class MainScene(Scene):
    def construct(self):
        title = Text("Part 2 — Main idea", font_size=40)
        self.play(Write(title))
        self.wait(0.5)
