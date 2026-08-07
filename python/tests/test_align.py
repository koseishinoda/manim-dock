from manim_dock.align import compute_align_deltas


def test_align_left():
    items = [
        {"name": "a", "x": 1.0, "y": 0.0},
        {"name": "b", "x": 3.0, "y": 1.0},
        {"name": "c", "x": 2.0, "y": -1.0},
    ]
    deltas = compute_align_deltas(items, "left")
    by_name = {d["name"]: d for d in deltas}
    assert by_name["a"]["dx"] == 0.0
    assert by_name["b"]["dx"] == -2.0
    assert by_name["c"]["dx"] == -1.0
    assert all(d["dy"] == 0.0 for d in deltas)


def test_distribute_x():
    items = [
        {"name": "a", "x": 0.0, "y": 0.0},
        {"name": "b", "x": 1.0, "y": 0.0},
        {"name": "c", "x": 4.0, "y": 0.0},
    ]
    deltas = compute_align_deltas(items, "distribute_x")
    by_name = {d["name"]: d for d in deltas}
    # Even spacing on [0, 4]: targets 0, 2, 4 → b moves +1.
    assert abs(by_name["a"]["dx"]) < 1e-9
    assert abs(by_name["b"]["dx"] - 1.0) < 1e-9
    assert abs(by_name["c"]["dx"]) < 1e-9
    assert all(abs(d["dy"]) < 1e-9 for d in deltas)
