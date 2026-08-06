"""Multi-section ManimCE scene — title / body / cleanup beats (P12)."""

from manim import *


class MultiSectionLesson(Scene):
    def construct(self):
        self.next_section("Title")
        title = Text("What are we learning?", font_size=40)
        title.to_edge(UP)
        self.play(Write(title))
        self.wait(0.5)

        self.next_section("Body")
        body = Text("State the idea, then show it.", font_size=32)
        body.next_to(title, DOWN, buff=0.6)
        self.play(FadeIn(body, shift=UP * 0.2))
        self.wait(0.5)

        self.next_section("Cleanup")
        leftovers = Group(*self.mobjects)
        if len(leftovers):
            self.play(FadeOut(leftovers))
        self.wait(0.2)
