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


def _estimate_from_calls(
    name: str, calls: list[LayoutCall], source_tree: ast.AST
) -> tuple[float, float]:
    """Walk layout call ASTs for ``name`` in source order; return estimated (x, y)."""
    call_lines = {c.range.start_line for c in calls}

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.x = 0.0
            self.y = 0.0

        def visit_Call(self, node: ast.Call) -> None:
            if not isinstance(node.func, ast.Attribute):
                self.generic_visit(node)
                return
            if not isinstance(node.func.value, ast.Name) or node.func.value.id != name:
                self.generic_visit(node)
                return
            kind = node.func.attr
            line = getattr(node, "lineno", None)
            if line not in call_lines:
                self.generic_visit(node)
                return
            if kind == "to_edge" and node.args:
                vec = _eval_dir_expr(node.args[0])
                if vec is not None:
                    self.x = vec[0] * (FRAME_WIDTH / 2.0 - EDGE_INSET)
                    self.y = vec[1] * (FRAME_HEIGHT / 2.0 - EDGE_INSET)
            elif kind == "to_corner" and node.args:
                vec = _eval_dir_expr(node.args[0])
                if vec is not None:
                    self.x = vec[0] * (FRAME_WIDTH / 2.0 - EDGE_INSET)
                    self.y = vec[1] * (FRAME_HEIGHT / 2.0 - EDGE_INSET)
            elif kind == "move_to" and node.args:
                vec = _eval_dir_expr(node.args[0])
                if vec is not None:
                    self.x, self.y = vec
            elif kind == "center":
                self.x, self.y = 0.0, 0.0
            elif kind == "shift" and node.args:
                vec = _eval_dir_expr(node.args[0])
                if vec is not None:
                    self.x += vec[0]
                    self.y += vec[1]
            elif kind == "set_x" and node.args and isinstance(node.args[0], ast.Constant):
                if isinstance(node.args[0].value, (int, float)):
                    self.x = float(node.args[0].value)
            elif kind == "set_y" and node.args and isinstance(node.args[0], ast.Constant):
                if isinstance(node.args[0].value, (int, float)):
                    self.y = float(node.args[0].value)
            self.generic_visit(node)

    visitor = Visitor()
    visitor.visit(source_tree)
    return visitor.x, visitor.y


def _collect_in_function(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    tree: ast.AST,
) -> dict[str, LayoutItem]:
    items: dict[str, LayoutItem] = {}

    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            name = _simple_assign_target(node.targets[0])
            ctor = _ctor_name(node.value)
            if name and ctor and (ctor in MOBJECT_CTORS or ctor.endswith("Mobject")):
                items[name] = LayoutItem(
                    name=name,
                    mobject_kind=ctor,
                    range=_line_range(node),
                    note="heuristic position — not a live Manim snapshot",
                )
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            name = _simple_assign_target(node.target)
            ctor = _ctor_name(node.value)
            if name and ctor and (ctor in MOBJECT_CTORS or ctor.endswith("Mobject")):
                items[name] = LayoutItem(
                    name=name,
                    mobject_kind=ctor,
                    range=_line_range(node),
                    note="heuristic position — not a live Manim snapshot",
                )

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
        try:
            code = ast.unparse(node)
        except Exception:
            code = f"{name}.{node.func.attr}(...)"
        items[name].layout_calls.append(
            LayoutCall(kind=node.func.attr, code=code, range=_line_range(node))
        )

    for item in items.values():
        item.x, item.y = _estimate_from_calls(item.name, item.layout_calls, tree)
        if not item.layout_calls and item.mobject_kind == "unknown":
            item.editable = False
    return items


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
    for node in scene_cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_") and node.name != "__init__":
                continue
            for name, item in _collect_in_function(node, tree).items():
                if name in merged:
                    # Prefer richer assignment metadata; append layout calls.
                    existing = merged[name]
                    if existing.mobject_kind == "unknown" and item.mobject_kind != "unknown":
                        existing.mobject_kind = item.mobject_kind
                        existing.range = item.range
                    existing.layout_calls.extend(item.layout_calls)
                    existing.x, existing.y = _estimate_from_calls(
                        existing.name, existing.layout_calls, tree
                    )
                else:
                    merged[name] = item

    # Stable order: by first appearance line.
    result.items = sorted(merged.values(), key=lambda i: (i.range.start_line, i.name))
    return result


def parse_file_layout(path: str | Path, scene_name: str) -> SceneLayout:
    file_path = Path(path)
    source = file_path.read_text(encoding="utf-8")
    return parse_scene_layout(source, path=str(file_path), scene_name=scene_name)
