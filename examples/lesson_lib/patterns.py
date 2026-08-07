"""Reusable educational patterns (P01–P03, P06–P10) as plain ManimCE helpers.

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


def brace_callout(
    scene: Scene,
    mobject: Mobject,
    text: str = "notice this",
    *,
    direction=DOWN,
    color=ACCENT,
    font_size: int = 28,
    wait: float = DEFAULT_WAIT,
    fade_out: bool = False,
) -> VGroup:
    """P07 — Brace + label callout under (or beside) a mobject."""
    brace = Brace(mobject, direction=direction, color=color)
    label = Text(text, font_size=font_size, color=color)
    label.next_to(brace, direction, buff=0.15)
    group = VGroup(brace, label)
    scene.play(GrowFromCenter(brace), FadeIn(label))
    scene.wait(wait)
    if fade_out:
        scene.play(FadeOut(group))
    return group


def axes_intro(
    scene: Scene,
    *,
    x_range: tuple[float, float, float] = (-3, 3, 1),
    y_range: tuple[float, float, float] = (-2, 2, 1),
    use_number_plane: bool = True,
    run_time: float = 1.2,
    wait: float = DEFAULT_WAIT,
) -> Mobject:
    """P08 — NumberPlane or Axes intro via Create."""
    if use_number_plane:
        axes = NumberPlane(x_range=x_range, y_range=y_range)
    else:
        axes = Axes(x_range=x_range, y_range=y_range)
    scene.play(Create(axes), run_time=run_time)
    scene.wait(wait)
    return axes


def compare_cards(
    scene: Scene,
    left_title: str,
    right_title: str,
    *,
    left_body: str = "…",
    right_body: str = "…",
    vs_text: str = "vs",
    buff: float = 0.8,
    wait: float = DEFAULT_WAIT,
    fade_out: bool = False,
) -> VGroup:
    """P09 — side-by-side compare cards with a vs marker."""
    left = VGroup(
        Text(left_title, font_size=32),
        Text(left_body, font_size=24),
    ).arrange(DOWN, buff=0.2)
    vs = Text(vs_text, font_size=28, color=ACCENT)
    right = VGroup(
        Text(right_title, font_size=32),
        Text(right_body, font_size=24),
    ).arrange(DOWN, buff=0.2)
    row = VGroup(left, vs, right).arrange(RIGHT, buff=buff)
    row.move_to(ORIGIN)
    scene.play(FadeIn(row))
    scene.wait(wait)
    if fade_out:
        scene.play(FadeOut(row))
    return row


def succession_beat(
    scene: Scene,
    *animations: Animation,
    run_time: float | None = None,
    wait: float = DEFAULT_WAIT,
) -> None:
    """P10 — play animations as a Succession beat."""
    if not animations:
        scene.wait(wait)
        return
    kwargs: dict = {}
    if run_time is not None:
        kwargs["run_time"] = run_time
    scene.play(Succession(*animations), **kwargs)
    scene.wait(wait)
