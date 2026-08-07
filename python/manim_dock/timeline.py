"""Transient Timeline view model: play / wait / section beats with durations.

Uses stdlib ``ast`` only. Durations are read from literals (and simple module
constants); the timeline is a view, never project truth.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from manim_dock.outline import SourceRange, _call_name, _line_range

DEFAULT_PLAY_RUNTIME = 1.0


@dataclass
class TimelineEvent:
    id: str
    kind: str  # play | wait | next_section
    label: str
    method: str
    range: SourceRange
    start: float
    duration: float
    editable: bool
    duration_source: str  # literal | constant | default | unknown
    note: str = ""
    section: str = ""  # enclosing next_section label; "" before first section

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "method": self.method,
            "range": self.range.to_dict(),
            "start": self.start,
            "duration": self.duration,
            "editable": self.editable,
            "duration_source": self.duration_source,
            "note": self.note,
            "section": self.section,
        }


@dataclass
class SceneTimeline:
    path: str
    scene: str
    total_duration: float = 0.0
    events: list[TimelineEvent] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "scene": self.scene,
            "total_duration": self.total_duration,
            "events": [e.to_dict() for e in self.events],
            "errors": list(self.errors),
        }


def _literal_float(node: ast.AST | None) -> float | None:
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _literal_float(node.operand)
        return None if inner is None else -inner
    return None


def _module_constants(tree: ast.AST) -> dict[str, float]:
    consts: dict[str, float] = {}
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                value = _literal_float(node.value)
                if value is not None:
                    consts[target.id] = value
    return consts


def _resolve_duration(
    node: ast.AST | None, constants: dict[str, float]
) -> tuple[float | None, str, bool, str]:
    """Return (duration, source, editable, note)."""
    lit = _literal_float(node)
    if lit is not None:
        return lit, "literal", True, ""
    if isinstance(node, ast.Name) and node.id in constants:
        return (
            constants[node.id],
            "constant",
            False,
            f"bound to {node.id} — edit the constant or replace with a literal in code",
        )
    if node is None:
        return None, "unknown", False, "no duration argument"
    try:
        code = ast.unparse(node)
    except Exception:
        code = "…"
    return None, "unknown", False, f"unsupported duration expression: {code}"


def _play_runtime(
    node: ast.Call, constants: dict[str, float]
) -> tuple[float, str, bool, str]:
    for kw in node.keywords:
        if kw.arg == "run_time":
            dur, source, editable, note = _resolve_duration(kw.value, constants)
            if dur is not None:
                return dur, source, editable, note
            return DEFAULT_PLAY_RUNTIME, "unknown", False, note
    return (
        DEFAULT_PLAY_RUNTIME,
        "default",
        True,
        "implicit Manim default run_time=1 — editing will insert run_time=",
    )


def _wait_duration(
    node: ast.Call, constants: dict[str, float]
) -> tuple[float, str, bool, str]:
    if not node.args:
        return 1.0, "default", True, "implicit wait(1) — editing will insert an argument"
    dur, source, editable, note = _resolve_duration(node.args[0], constants)
    if dur is not None:
        return dur, source, editable, note
    return 0.0, "unknown", False, note


def _section_label(node: ast.Call) -> str:
    if node.args:
        try:
            return ast.unparse(node.args[0]).strip("\"'")
        except Exception:
            pass
    for kw in node.keywords:
        if kw.arg == "name" and kw.value is not None:
            try:
                return ast.unparse(kw.value).strip("\"'")
            except Exception:
                pass
    return "section"


def _methods_by_name(
    class_def: ast.ClassDef,
) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    out: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in class_def.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = node
    return out


def _collect_calls_in_order(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ast.Call]:
    calls: list[ast.Call] = []

    class Visitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:
            if _call_name(node) is not None:
                calls.append(node)
            # Still visit args (e.g. unlikely) but typically play/wait are statements.
            self.generic_visit(node)

    for stmt in fn.body:
        Visitor().visit(stmt)
    return calls


def _expand_method(
    method_name: str,
    methods: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    constants: dict[str, float],
    events: list[TimelineEvent],
    t: float,
    counter: list[int],
    stack: set[str],
    current_section: list[str],
) -> float:
    if method_name in stack:
        return t
    fn = methods.get(method_name)
    if fn is None:
        return t
    stack.add(method_name)
    try:
        for call in _collect_calls_in_order(fn):
            name = _call_name(call)
            if name is None:
                continue
            if name in {"play", "wait", "next_section"}:
                counter[0] += 1
                eid = f"e{counter[0]}"
                rng = _line_range(call)
                if name == "next_section":
                    label = _section_label(call)
                    current_section[0] = label
                    events.append(
                        TimelineEvent(
                            id=eid,
                            kind="next_section",
                            label=label,
                            method=method_name,
                            range=rng,
                            start=t,
                            duration=0.0,
                            editable=False,
                            duration_source="n/a",
                            note="section marker",
                            section=label,
                        )
                    )
                elif name == "wait":
                    dur, source, editable, note = _wait_duration(call, constants)
                    try:
                        arg = ast.unparse(call.args[0]) if call.args else ""
                        label = f"wait({arg})" if arg else "wait()"
                    except Exception:
                        label = "wait(...)"
                    events.append(
                        TimelineEvent(
                            id=eid,
                            kind="wait",
                            label=label,
                            method=method_name,
                            range=rng,
                            start=t,
                            duration=dur,
                            editable=editable,
                            duration_source=source,
                            note=note,
                            section=current_section[0],
                        )
                    )
                    t += dur
                else:  # play
                    dur, source, editable, note = _play_runtime(call, constants)
                    label = "play(...)"
                    if call.args:
                        first = call.args[0]
                        ctor: str | None = None
                        if isinstance(first, ast.Call):
                            if isinstance(first.func, ast.Name):
                                ctor = first.func.id
                            elif isinstance(first.func, ast.Attribute):
                                ctor = first.func.attr
                        if ctor:
                            label = f"play({ctor}…)"
                    events.append(
                        TimelineEvent(
                            id=eid,
                            kind="play",
                            label=label,
                            method=method_name,
                            range=rng,
                            start=t,
                            duration=dur,
                            editable=editable,
                            duration_source=source,
                            note=note,
                            section=current_section[0],
                        )
                    )
                    t += dur
            elif name in methods and name not in stack:
                # Helper beat: self.title_card()
                t = _expand_method(
                    name,
                    methods,
                    constants,
                    events,
                    t,
                    counter,
                    stack,
                    current_section,
                )
    finally:
        stack.discard(method_name)
    return t


def parse_scene_timeline(source: str, path: str, scene_name: str) -> SceneTimeline:
    result = SceneTimeline(path=path, scene=scene_name)
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

    constants = _module_constants(tree)
    methods = _methods_by_name(scene_cls)
    if "construct" not in methods:
        result.errors.append("Scene has no construct() method")
        return result

    events: list[TimelineEvent] = []
    total = _expand_method(
        "construct", methods, constants, events, 0.0, [0], set(), [""]
    )
    result.events = events
    result.total_duration = total
    return result


def parse_file_timeline(path: str | Path, scene_name: str) -> SceneTimeline:
    file_path = Path(path)
    source = file_path.read_text(encoding="utf-8")
    return parse_scene_timeline(source, path=str(file_path), scene_name=scene_name)
