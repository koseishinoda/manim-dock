from manim_dock.layout import parse_scene_layout
from manim_dock.scrub import scrub_positions


SCRUB_SAMPLE = '''
from manim import *

class Demo(Scene):
    def construct(self):
        title = Text("Hello")
        title.to_edge(UP)
'''


def test_scrub_before_to_edge_is_origin():
    layout = parse_scene_layout(SCRUB_SAMPLE, "<mem>", "Demo")
    title = next(i for i in layout.items if i.name == "title")
    # Scrub before the to_edge line → no layout calls applied.
    before_line = title.layout_calls[0].range.start_line - 1
    positions = scrub_positions(layout, before_line, source=SCRUB_SAMPLE)
    assert positions["title"]["x"] == 0.0
    assert positions["title"]["y"] == 0.0
    assert positions["title"]["opacity"] == 1.0


def test_scrub_after_to_edge_moves_up():
    layout = parse_scene_layout(SCRUB_SAMPLE, "<mem>", "Demo")
    title = next(i for i in layout.items if i.name == "title")
    after_line = title.layout_calls[0].range.end_line
    positions = scrub_positions(layout, after_line, source=SCRUB_SAMPLE)
    assert positions["title"]["y"] > 2.0
    assert abs(positions["title"]["x"]) < 1e-9
