"""Same beats as minimal_lesson, authored against plain lesson_lib helpers.

Demonstrates P15 facilitation — library reuse without Dock runtime hooks.

    PYTHONPATH=examples manim -pql examples/lesson_with_lib/lesson.py LibLesson
"""

from manim import *

from lesson_lib import (
    ACCENT,
    DEFAULT_WAIT,
    PRIMARY,
    definition_card,
    step_list,
    title_card,
    two_column,
)


class LibLesson(Scene):
    def construct(self):
        self.next_section("Title")
        title_card(self, "Why does this formula work?")

        self.next_section("Definition")
        definition_card(
            self,
            body="The derivative measures local rate of change.",
            color=PRIMARY,
        )

        self.next_section("Steps")
        step_list(self)

        self.next_section("Equation")
        eq = MathTex("{{a}}^2", "+", "{{b}}^2", "=", "{{c}}^2")
        eq.move_to(ORIGIN)
        self.play(Write(eq))
        self.play(Indicate(eq[0], color=ACCENT))
        self.wait(DEFAULT_WAIT)

        self.next_section("Derivation")
        eq2 = MathTex("{{a}}^2", "=", "{{c}}^2", "-", "{{b}}^2")
        self.play(TransformMatchingTex(eq, eq2), run_time=1.5)
        self.wait(DEFAULT_WAIT)

        self.next_section("TwoColumn")
        self.play(FadeOut(eq2))
        diagram = Circle(radius=0.8, color=PRIMARY)
        label = Text("intuition", font_size=24).next_to(diagram, DOWN, buff=0.2)
        left = VGroup(diagram, label).arrange(DOWN, buff=0.2)
        right = VGroup(
            Text("Rearranged form", font_size=28),
            eq2.copy().scale(0.9),
        ).arrange(DOWN, buff=0.3)
        two_column(self, left, right)

        self.next_section("Cleanup")
        leftovers = Group(*self.mobjects)
        if len(leftovers):
            self.play(FadeOut(leftovers))
        self.wait(0.2)
