"""Approximate Stage scrub: positions from layout calls up to a source line."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from manim_dock.layout import (
    LayoutCall,
    LayoutItem,
    SceneLayout,
    SourceRange,
    _estimate_from_calls,
    parse_file_layout,
    parse_scene_layout,
)


def _item_start_line(item: LayoutItem | dict[str, Any]) -> int:
    if isinstance(item, LayoutItem):
        return item.range.start_line
    rng = item.get("range") or {}
    return int(rng.get("start_line") or 0)


def _call_end_line(call: LayoutCall | dict[str, Any]) -> int:
    if isinstance(call, LayoutCall):
        return call.range.end_line
    rng = call.get("range") or {}
    return int(rng.get("end_line") or call.get("end_line") or 0)


def _normalize_call(call: LayoutCall | dict[str, Any]) -> LayoutCall:
    if isinstance(call, LayoutCall):
        return call
    rng = call.get("range") or {}
    return LayoutCall(
        kind=str(call.get("kind") or ""),
        code=str(call.get("code") or ""),
        range=SourceRange(
            start_line=int(rng.get("start_line") or 0),
            end_line=int(rng.get("end_line") or 0),
        ),
    )


def _iter_items(
    layout: SceneLayout | dict[str, Any],
) -> list[tuple[str, int, list[LayoutCall]]]:
    if isinstance(layout, SceneLayout):
        return [
            (item.name, item.range.start_line, list(item.layout_calls))
            for item in layout.items
        ]
    out: list[tuple[str, int, list[LayoutCall]]] = []
    for raw in layout.get("items") or []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "")
        if not name:
            continue
        start = _item_start_line(raw)
        calls = [_normalize_call(c) for c in (raw.get("layout_calls") or [])]
        out.append((name, start, calls))
    return out


def scrub_positions(
    layout: SceneLayout | dict[str, Any],
    active_until_line: int,
    *,
    source: str | None = None,
) -> dict[str, dict[str, float]]:
    """Return ``{name: {x, y, opacity}}`` using layout calls ending at/before line.

    Opacity is 1.0 once the item's binding line is reached, else 0.35.
    Positions re-estimate from filtered ``layout_calls`` (fallback 0,0).
    """
    path = layout.path if isinstance(layout, SceneLayout) else str(layout.get("path") or "")
    tree: ast.AST | None = None
    src = source
    if src is None and path and path not in {"", "<mem>", "<fixture>"}:
        try:
            src = Path(path).read_text(encoding="utf-8")
        except OSError:
            src = None
    if src is not None:
        try:
            tree = ast.parse(src, filename=path or "<scrub>")
        except SyntaxError:
            tree = None

    result: dict[str, dict[str, float]] = {}
    known: dict[str, tuple[float, float]] = {}
    ordered = sorted(_iter_items(layout), key=lambda e: (e[1], e[0]))
    for name, start_line, calls in ordered:
        active_calls = [c for c in calls if _call_end_line(c) <= active_until_line]
        if tree is not None:
            x, y = _estimate_from_calls(
                name, active_calls, tree, known_positions=known
            )
        else:
            x, y = 0.0, 0.0
        known[name] = (x, y)
        opacity = 1.0 if start_line <= active_until_line else 0.35
        result[name] = {"x": float(x), "y": float(y), "opacity": opacity}
    return result


def scrub_layout(
    path: str,
    scene: str,
    active_until_line: int,
    *,
    source: str | None = None,
) -> dict[str, Any]:
    """Parse layout then scrub — convenience for the host / CLI."""
    if isinstance(source, str):
        layout = parse_scene_layout(source, path, scene)
        src = source
    else:
        layout = parse_file_layout(path, scene)
        src = Path(path).read_text(encoding="utf-8")
    positions = scrub_positions(layout, active_until_line, source=src)
    return {
        "path": path,
        "scene": scene,
        "active_until_line": active_until_line,
        "positions": positions,
        "errors": list(layout.errors),
    }
