"""Reusable educational patterns (P01–P03, P06) as plain ManimCE helpers.

These are normal Python functions — uninstall-safe, no Dock APIs.
"""

from __future__ import annotations

from manim import *


PRIMARY = BLUE
ACCENT = YELLOW
DEFAULT_WAIT = 0.5


def title_card(
    scene: Scene,
    text: str = "Why does this formula work?",
    *,
    font_size: int = 40,
    run_time: float = 1.2,
    wait: float = DEFAULT_WAIT,
    fade_out: bool = True,
) -> Mobject:
    """P01 — title / hook card."""
    title = Text(text, font_size=font_size)
    title.to_edge(UP)
    scene.play(Write(title), run_time=run_time)
    scene.wait(wait)
    if fade_out:
        scene.play(FadeOut(title))
    return title


def definition_card(
    scene: Scene,
    heading: str = "Definition",
    body: str = "…",
    *,
    color=PRIMARY,
    buff: float = 0.25,
    box_buff: float = 0.2,
    wait: float = DEFAULT_WAIT,
    fade_out: bool = True,
) -> VGroup:
    """P02 — definition heading + body + surrounding rectangle."""
    head = Text(heading, color=color, font_size=36)
    body_m = Text(body, font_size=28)
    card = VGroup(head, body_m).arrange(DOWN, aligned_edge=LEFT, buff=buff)
    card.to_edge(UP)
    box = SurroundingRectangle(card, color=color, buff=box_buff)
    group = VGroup(card, box)
    scene.play(FadeIn(group, shift=DOWN * 0.2))
    scene.wait(wait)
    if fade_out:
        scene.play(FadeOut(group))
    return group


def step_list(
    scene: Scene,
    lines: list[str] | None = None,
    *,
    buff: float = 0.3,
    lag_ratio: float = 0.35,
    wait: float = DEFAULT_WAIT,
    fade_out: bool = True,
) -> VGroup:
    """P03 — lagged step list reveal."""
    if lines is None:
        lines = [
            "1. Start from a known identity",
            "2. Transform matching parts",
            "3. Box the result",
        ]
    steps = VGroup(*[Text(line) for line in lines]).arrange(
        DOWN, aligned_edge=LEFT, buff=buff
    )
    steps.to_edge(LEFT)
    scene.play(
        LaggedStart(
            *[FadeIn(s, shift=RIGHT * 0.2) for s in steps],
            lag_ratio=lag_ratio,
        )
    )
    scene.wait(wait)
    if fade_out:
        scene.play(FadeOut(steps))
    return steps


def two_column(
    scene: Scene,
    left: Mobject,
    right: Mobject,
    *,
    buff: float = 1.2,
    wait: float = DEFAULT_WAIT,
) -> VGroup:
    """P06 — place left | right columns and fade in."""
    columns = VGroup(left, right).arrange(RIGHT, buff=buff)
    columns.move_to(ORIGIN)
    scene.play(FadeIn(columns))
    scene.wait(wait)
    return columns
