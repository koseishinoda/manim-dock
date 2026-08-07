"""Pure-math align/distribute deltas for Stage multi-select (no AST)."""

from __future__ import annotations

from typing import Any


_MODES = frozenset(
    {
        "left",
        "right",
        "center_x",
        "top",
        "bottom",
        "center_y",
        "distribute_x",
        "distribute_y",
    }
)


def compute_align_deltas(
    items: list[dict[str, Any]], mode: str
) -> list[dict[str, float | str]]:
    """Compute relative ``dx``/``dy`` so Stage can insert ``.shift(...)`` patches.

    ``items`` entries need ``name``, ``x``, ``y``. Modes: left, right, center_x,
    top, bottom, center_y, distribute_x, distribute_y.
    """
    if mode not in _MODES:
        raise ValueError(f"unknown align mode: {mode!r}")
    if not items:
        return []

    parsed: list[tuple[str, float, float]] = []
    for raw in items:
        name = str(raw.get("name") or "")
        if not name:
            continue
        parsed.append((name, float(raw.get("x") or 0.0), float(raw.get("y") or 0.0)))
    if not parsed:
        return []

    xs = [p[1] for p in parsed]
    ys = [p[2] for p in parsed]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)

    targets: dict[str, tuple[float, float]] = {}

    if mode == "left":
        for name, x, y in parsed:
            targets[name] = (min_x, y)
    elif mode == "right":
        for name, x, y in parsed:
            targets[name] = (max_x, y)
    elif mode == "center_x":
        for name, x, y in parsed:
            targets[name] = (mean_x, y)
    elif mode == "top":
        for name, x, y in parsed:
            targets[name] = (x, max_y)
    elif mode == "bottom":
        for name, x, y in parsed:
            targets[name] = (x, min_y)
    elif mode == "center_y":
        for name, x, y in parsed:
            targets[name] = (x, mean_y)
    elif mode == "distribute_x":
        ordered = sorted(parsed, key=lambda p: (p[1], p[0]))
        n = len(ordered)
        if n == 1:
            targets[ordered[0][0]] = (ordered[0][1], ordered[0][2])
        else:
            for i, (name, _x, y) in enumerate(ordered):
                tx = min_x + (max_x - min_x) * i / (n - 1)
                targets[name] = (tx, y)
    elif mode == "distribute_y":
        ordered = sorted(parsed, key=lambda p: (p[2], p[0]))
        n = len(ordered)
        if n == 1:
            targets[ordered[0][0]] = (ordered[0][1], ordered[0][2])
        else:
            for i, (name, x, _y) in enumerate(ordered):
                ty = min_y + (max_y - min_y) * i / (n - 1)
                targets[name] = (x, ty)

    out: list[dict[str, float | str]] = []
    for name, x, y in parsed:
        tx, ty = targets[name]
        out.append({"name": name, "dx": tx - x, "dy": ty - y})
    return out
