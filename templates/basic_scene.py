"""Minimal ManimCE scene template — plain Scene, no Dock imports."""

from manim import *


class BasicScene(Scene):
    def construct(self):
        title = Text("Hello, Manim", font_size=48)
        self.play(Write(title))
        self.wait(0.5)
