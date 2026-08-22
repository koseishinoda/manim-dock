"""Transient Stage view model: named mobjects + layout calls (read-only AST).

Does not import or execute Manim. Positions are heuristic estimates for the Stage
canvas — never project truth.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from manim_dock.outline import SourceRange, _line_range

# ManimCE default pixel frame geometry (config.frame_height = 8, 16:9).
FRAME_HEIGHT = 8.0
FRAME_WIDTH = FRAME_HEIGHT * 16.0 / 9.0
EDGE_INSET = 0.5

LAYOUT_ATTRS = frozenset(
    {
        "to_edge",
        "to_corner",
        "move_to",
        "shift",
        "next_to",
        "arrange",
        "align_to",
        "set_x",
        "set_y",
        "center",
    }
)

MOBJECT_CTORS = frozenset(
    {
        "Text",
        "MarkupText",
        "MathTex",
        "Tex",
        "VGroup",
        "Group",
        "Circle",
        "Square",
        "Rectangle",
        "SurroundingRectangle",
        "RoundedRectangle",
        "Line",
        "Arrow",
        "Dot",
        "NumberPlane",
        "Axes",
        "ImageMobject",
        "SVGMobject",
    }
)


@dataclass
class LayoutCall:
    kind: str
    code: str
    range: SourceRange

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "code": self.code,
            "range": self.range.to_dict(),
        }


@dataclass
class LayoutItem:
    name: str
    mobject_kind: str
    range: SourceRange
    layout_calls: list[LayoutCall] = field(default_factory=list)
    x: float = 0.0
    y: float = 0.0
    editable: bool = True
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "mobject_kind": self.mobject_kind,
            "range": self.range.to_dict(),
            "layout_calls": [c.to_dict() for c in self.layout_calls],
            "x": self.x,
            "y": self.y,
            "editable": self.editable,
            "note": self.note,
        }


@dataclass
class SceneLayout:
    path: str
    scene: str
    frame_width: float = FRAME_WIDTH
    frame_height: float = FRAME_HEIGHT
    items: list[LayoutItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "scene": self.scene,
            "frame_width": self.frame_width,
            "frame_height": self.frame_height,
            "items": [i.to_dict() for i in self.items],
            "errors": list(self.errors),
        }


def _ctor_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
    return None


def _simple_assign_target(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
        return node.id
    return None


def _layout_call_from_node(node: ast.Call) -> LayoutCall:
    kind = node.func.attr if isinstance(node.func, ast.Attribute) else "call"
    try:
        code = ast.unparse(node)
    except Exception:
        code = f"...{kind}(...)"
    return LayoutCall(kind=kind, code=code, range=_line_range(node))


def _unwrap_mobject_expr(
    node: ast.AST,
) -> tuple[str | None, list[ast.Call], ast.Call | None]:
    """Unwrap ``Ctor(...).to_edge(...).shift(...)`` chains.

    Returns ``(ctor_name, layout_calls_in_application_order, ctor_call)``.
    Layout attrs are peeled outer-to-inner then reversed so order matches Manim
    application (ctor first, then each chained layout call).
    """
    layout_calls: list[ast.Call] = []
    current: ast.AST = node
    while (
        isinstance(current, ast.Call)
        and isinstance(current.func, ast.Attribute)
        and current.func.attr in LAYOUT_ATTRS
    ):
        layout_calls.append(current)
        current = current.func.value
    layout_calls.reverse()
    ctor = _ctor_name(current)
    ctor_call = current if isinstance(current, ast.Call) else None
    return ctor, layout_calls, ctor_call


def _vgroup_child_names(ctor_call: ast.Call | None) -> list[str]:
    """Return Name args of a VGroup/Group ctor, or [] if any arg is non-Name."""
    if ctor_call is None:
        return []
    children: list[str] = []
    for arg in ctor_call.args:
        if not isinstance(arg, ast.Name):
            return []
        children.append(arg.id)
    return children


def _dir_vector(name: str) -> tuple[float, float] | None:
    mapping = {
        "UP": (0.0, 1.0),
        "DOWN": (0.0, -1.0),
        "LEFT": (-1.0, 0.0),
        "RIGHT": (1.0, 0.0),
        "ORIGIN": (0.0, 0.0),
        "UL": (-1.0, 1.0),
        "UR": (1.0, 1.0),
        "DL": (-1.0, -1.0),
        "DR": (1.0, -1.0),
    }
    return mapping.get(name)


def _eval_dir_expr(node: ast.AST) -> tuple[float, float] | None:
    """Best-effort constant fold for UP/DOWN/LEFT/RIGHT and simple * / +."""
    if isinstance(node, ast.Name):
        return _dir_vector(node.id)
    if isinstance(node, ast.Attribute):
        return _dir_vector(node.attr)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _eval_dir_expr(node.operand)
        if inner is None:
            return None
        return (-inner[0], -inner[1])
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
        left = _eval_dir_expr(node.left)
        right = _eval_dir_expr(node.right)
        if left is not None and isinstance(node.right, ast.Constant) and isinstance(
            node.right.value, (int, float)
        ):
            s = float(node.right.value)
            return (left[0] * s, left[1] * s)
        if right is not None and isinstance(node.left, ast.Constant) and isinstance(
            node.left.value, (int, float)
        ):
            s = float(node.left.value)
            return (right[0] * s, right[1] * s)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        a = _eval_dir_expr(node.left)
        b = _eval_dir_expr(node.right)
        if a is not None and b is not None:
            return (a[0] + b[0], a[1] + b[1])
    if isinstance(node, ast.Tuple) and len(node.elts) >= 2:
        if all(isinstance(e, ast.Constant) and isinstance(e.value, (int, float)) for e in node.elts[:2]):
            return (float(node.elts[0].value), float(node.elts[1].value))  # type: ignore[arg-type]
    return None


def _const_float(node: ast.AST) -> float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    return None


def _buff_from_call(node: ast.Call, positional_index: int, default: float = 0.25) -> float:
    if len(node.args) > positional_index:
        value = _const_float(node.args[positional_index])
        if value is not None:
            return value
    for kw in node.keywords:
        if kw.arg == "buff":
            value = _const_float(kw.value)
            if value is not None:
                return value
    return default


def _unit(vec: tuple[float, float]) -> tuple[float, float]:
    dx, dy = vec
    mag = (dx * dx + dy * dy) ** 0.5
    if mag <= 0.0:
        return (0.0, 0.0)
    return (dx / mag, dy / mag)


def _find_call_node(source_tree: ast.AST, call: LayoutCall, name: str) -> ast.Call | None:
    matches: list[ast.Call] = []
    for node in ast.walk(source_tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != call.kind:
            continue
        if getattr(node, "lineno", None) != call.range.start_line:
            continue
        matches.append(node)
    if not matches:
        return None
    for node in matches:
        if isinstance(node.func.value, ast.Name) and node.func.value.id == name:
            return node
    return matches[0]


def _estimate_from_calls(
    name: str,
    calls: list[LayoutCall],
    source_tree: ast.AST,
    *,
    known_positions: dict[str, tuple[float, float]] | None = None,
    vgroup_children: dict[str, list[str]] | None = None,
) -> tuple[float, float]:
    """Apply layout calls in application order; return estimated (x, y).

    Positions are Stage heuristics only — not live Manim geometry.
    ``next_to`` offsets by unit(direction) * (1.0 + buff) from a known other.
    ``arrange`` optionally spreads known Name children along the arrange axis.
    """
    x = 0.0
    y = 0.0
    positions = known_positions if known_positions is not None else {}
    children_map = vgroup_children if vgroup_children is not None else {}

    for call in calls:
        node = _find_call_node(source_tree, call, name)
        if node is None:
            continue
        kind = call.kind
        if kind == "to_edge" and node.args:
            vec = _eval_dir_expr(node.args[0])
            if vec is not None:
                x = vec[0] * (FRAME_WIDTH / 2.0 - EDGE_INSET)
                y = vec[1] * (FRAME_HEIGHT / 2.0 - EDGE_INSET)
        elif kind == "to_corner" and node.args:
            vec = _eval_dir_expr(node.args[0])
            if vec is not None:
                x = vec[0] * (FRAME_WIDTH / 2.0 - EDGE_INSET)
                y = vec[1] * (FRAME_HEIGHT / 2.0 - EDGE_INSET)
        elif kind == "move_to" and node.args:
            vec = _eval_dir_expr(node.args[0])
            if vec is not None:
                x, y = vec
        elif kind == "center":
            x, y = 0.0, 0.0
        elif kind == "shift" and node.args:
            vec = _eval_dir_expr(node.args[0])
            if vec is not None:
                x += vec[0]
                y += vec[1]
        elif kind == "set_x" and node.args:
            value = _const_float(node.args[0])
            if value is not None:
                x = value
        elif kind == "set_y" and node.args:
            value = _const_float(node.args[0])
            if value is not None:
                y = value
        elif kind == "next_to" and node.args:
            # Approximate: other + unit(dir) * (1 + buff). Skip if other unknown.
            other = node.args[0]
            if isinstance(other, ast.Name) and other.id in positions:
                ox, oy = positions[other.id]
                direction = (0.0, -1.0)
                if len(node.args) >= 2:
                    parsed = _eval_dir_expr(node.args[1])
                    if parsed is not None:
                        direction = parsed
                for kw in node.keywords:
                    if kw.arg == "direction":
                        parsed = _eval_dir_expr(kw.value)
                        if parsed is not None:
                            direction = parsed
                buff = _buff_from_call(node, 2, default=0.25)
                ux, uy = _unit(direction)
                offset = 1.0 + buff
                x = ox + ux * offset
                y = oy + uy * offset
        elif kind == "arrange":
            # Light heuristic: only when all VGroup children were simple Names.
            kids = children_map.get(name) or []
            if not kids:
                continue
            direction = (1.0, 0.0)  # Manim arrange default is RIGHT
            if node.args:
                parsed = _eval_dir_expr(node.args[0])
                if parsed is not None:
                    direction = parsed
            for kw in node.keywords:
                if kw.arg == "direction":
                    parsed = _eval_dir_expr(kw.value)
                    if parsed is not None:
                        direction = parsed
            buff = _buff_from_call(node, 1, default=0.25)
            ux, uy = _unit(direction)
            step = 1.0 + buff
            n = len(kids)
            for i, child in enumerate(kids):
                t = i - (n - 1) / 2.0
                positions[child] = (x + ux * t * step, y + uy * t * step)

    return x, y


def _register_assignment(
    items: dict[str, LayoutItem],
    vgroup_children: dict[str, list[str]],
    name: str,
    value: ast.AST,
    bind_node: ast.AST,
) -> None:
    ctor, chain_calls, ctor_call = _unwrap_mobject_expr(value)
    if not ctor or not (ctor in MOBJECT_CTORS or ctor.endswith("Mobject")):
        return
    items[name] = LayoutItem(
        name=name,
        mobject_kind=ctor,
        range=_line_range(bind_node),
        note="heuristic position — not a live Manim snapshot",
    )
    if ctor in {"VGroup", "Group"}:
        children = _vgroup_child_names(ctor_call)
        if children:
            vgroup_children[name] = children
    for call_node in chain_calls:
        items[name].layout_calls.append(_layout_call_from_node(call_node))


def _collect_in_function(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[dict[str, LayoutItem], dict[str, list[str]]]:
    items: dict[str, LayoutItem] = {}
    vgroup_children: dict[str, list[str]] = {}

    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            name = _simple_assign_target(node.targets[0])
            if name:
                _register_assignment(items, vgroup_children, name, node.value, node)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            name = _simple_assign_target(node.target)
            if name:
                _register_assignment(items, vgroup_children, name, node.value, node)

    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in LAYOUT_ATTRS:
            continue
        if not isinstance(node.func.value, ast.Name):
            continue
        name = node.func.value.id
        if name not in items:
            # Layout on an unknown name — opaque editable proxy if it looks like a local.
            items[name] = LayoutItem(
                name=name,
                mobject_kind="unknown",
                range=_line_range(node),
                editable=True,
                note="name seen in layout call only; jump-to-source via call range",
            )
        items[name].layout_calls.append(_layout_call_from_node(node))

    for item in items.values():
        if not item.layout_calls and item.mobject_kind == "unknown":
            item.editable = False
    return items, vgroup_children


def _apply_estimates(
    items: dict[str, LayoutItem],
    tree: ast.AST,
    vgroup_children: dict[str, list[str]],
) -> None:
    """Estimate positions in source order so ``next_to`` / ``arrange`` see priors."""
    positions: dict[str, tuple[float, float]] = {}
    ordered = sorted(items.values(), key=lambda i: (i.range.start_line, i.name))
    for item in ordered:
        item.x, item.y = _estimate_from_calls(
            item.name,
            item.layout_calls,
            tree,
            known_positions=positions,
            vgroup_children=vgroup_children,
        )
        positions[item.name] = (item.x, item.y)
    # Arrange may have rewritten child positions after the child was estimated.
    for name, (px, py) in positions.items():
        if name in items:
            items[name].x = px
            items[name].y = py


def parse_scene_layout(source: str, path: str, scene_name: str) -> SceneLayout:
    result = SceneLayout(path=path, scene=scene_name)
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        result.errors.append(f"SyntaxError: {exc.msg} (line {exc.lineno})")
        return result

    scene_cls: ast.ClassDef | None = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == scene_name:
            scene_cls = node
            break
    if scene_cls is None:
        result.errors.append(f"Scene class not found: {scene_name}")
        return result

    merged: dict[str, LayoutItem] = {}
    merged_children: dict[str, list[str]] = {}
    for node in scene_cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_") and node.name != "__init__":
                continue
            items, children = _collect_in_function(node)
            for name, child_names in children.items():
                if name not in merged_children:
                    merged_children[name] = child_names
            for name, item in items.items():
                if name in merged:
                    # Prefer richer assignment metadata; append layout calls.
                    existing = merged[name]
                    if existing.mobject_kind == "unknown" and item.mobject_kind != "unknown":
                        existing.mobject_kind = item.mobject_kind
                        existing.range = item.range
                    existing.layout_calls.extend(item.layout_calls)
                else:
                    merged[name] = item

    _apply_estimates(merged, tree, merged_children)

    # Stable order: by first appearance line.
    result.items = sorted(merged.values(), key=lambda i: (i.range.start_line, i.name))
    return result


def parse_file_layout(path: str | Path, scene_name: str) -> SceneLayout:
    file_path = Path(path)
    source = file_path.read_text(encoding="utf-8")
    return parse_scene_layout(source, path=str(file_path), scene_name=scene_name)
