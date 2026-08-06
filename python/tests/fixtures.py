"""In-memory scene fixtures so tests do not depend on a mutable example file."""

# Minimal educational scene (stable copy of V1 lesson shapes).
LESSON_SOURCE = '''
from manim import *

PRIMARY = BLUE
ACCENT = YELLOW
DEFAULT_WAIT = 0.5


class MinimalLesson(Scene):
    def construct(self):
        self.next_section("Title")
        self.title_card()
        self.next_section("Definition")
        self.definition_block()
        self.next_section("Steps")
        self.step_list()
        self.next_section("Equation")
        self.equation_emphasis()
        self.next_section("Derivation")
        self.derivation_chain()
        self.next_section("TwoColumn")
        self.two_column()
        self.next_section("Cleanup")
        self.cleanup()

    def title_card(self):
        title = Text("Why does this formula work?", font_size=40)
        title.to_edge(UP)
        self.play(Write(title), run_time=1.2)
        self.wait(DEFAULT_WAIT)
        self.play(FadeOut(title))

    def definition_block(self):
        heading = Text("Definition", color=PRIMARY, font_size=36)
        body = Text("The derivative measures local rate of change.", font_size=28)
        card = VGroup(heading, body).arrange(DOWN, aligned_edge=LEFT, buff=0.25)
        card.to_edge(UP)
        box = SurroundingRectangle(card, color=PRIMARY, buff=0.2)
        group = VGroup(card, box)
        self.play(FadeIn(group, shift=DOWN * 0.2))
        self.wait(DEFAULT_WAIT)
        self.play(FadeOut(group))

    def step_list(self):
        steps = VGroup(
            Text("1. Start from a known identity"),
            Text("2. Transform matching parts"),
            Text("3. Box the result"),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.3)
        steps.to_edge(LEFT)
        self.play(LaggedStart(*[FadeIn(s, shift=RIGHT * 0.2) for s in steps], lag_ratio=0.35))
        self.wait(DEFAULT_WAIT)
        self.play(FadeOut(steps))

    def equation_emphasis(self):
        eq = MathTex("{{a}}^2", "+", "{{b}}^2", "=", "{{c}}^2")
        eq.move_to(ORIGIN)
        self.play(Write(eq))
        self.play(Indicate(eq[0], color=ACCENT))
        self.wait(DEFAULT_WAIT)
        self._eq = eq

    def derivation_chain(self):
        eq1 = getattr(self, "_eq", MathTex("{{a}}^2", "+", "{{b}}^2", "=", "{{c}}^2"))
        eq2 = MathTex("{{a}}^2", "=", "{{c}}^2", "-", "{{b}}^2")
        self.play(TransformMatchingTex(eq1, eq2), run_time=1.5)
        self.wait(DEFAULT_WAIT)
        self._eq = eq2

    def two_column(self):
        eq = getattr(self, "_eq", MathTex("a^2 = c^2 - b^2"))
        diagram = Circle(radius=0.8, color=PRIMARY)
        label = Text("intuition", font_size=24).next_to(diagram, DOWN, buff=0.2)
        left = VGroup(diagram, label).arrange(DOWN, buff=0.2)
        right = VGroup(
            Text("Rearranged form", font_size=28),
            eq.copy().scale(0.9),
        ).arrange(DOWN, buff=0.3)
        columns = VGroup(left, right).arrange(RIGHT, buff=1.2)
        columns.move_to(ORIGIN)
        self.play(FadeOut(eq))
        self.play(FadeIn(columns))
        self.wait(DEFAULT_WAIT)
        self._columns = columns

    def cleanup(self):
        leftovers = Group(*self.mobjects)
        if len(leftovers):
            self.play(FadeOut(leftovers))
        self.wait(0.2)
'''
