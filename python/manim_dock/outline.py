"""Extract a lightweight outline from ManimCE-style Python scene files.

Uses stdlib ``ast`` only — does not import or execute Manim.
"""

from __future__ import annotations

import ast
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SourceRange:
    start_line: int
    end_line: int

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass
class PlayOrWait:
    kind: str  # "play" | "wait" | "next_section" | "other"
    label: str
    range: SourceRange
    targets: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "label": self.label,
            "range": self.range.to_dict(),
            "targets": list(self.targets),
        }


@dataclass
class MethodOutline:
    name: str
    range: SourceRange
    events: list[PlayOrWait] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "range": self.range.to_dict(),
            "events": [e.to_dict() for e in self.events],
        }


@dataclass
class SceneOutline:
    name: str
    bases: list[str]
    range: SourceRange
    methods: list[MethodOutline] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "bases": self.bases,
            "range": self.range.to_dict(),
            "methods": [m.to_dict() for m in self.methods],
        }


@dataclass
class FileOutline:
    path: str
    scenes: list[SceneOutline] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "scenes": [s.to_dict() for s in self.scenes],
            "errors": list(self.errors),
        }


def _line_range(node: ast.AST) -> SourceRange:
    start = getattr(node, "lineno", 1) or 1
    end = getattr(node, "end_lineno", None) or start
    return SourceRange(start_line=start, end_line=end)


def _base_names(class_def: ast.ClassDef) -> list[str]:
    names: list[str] = []
    for base in class_def.bases:
        if isinstance(base, ast.Name):
            names.append(base.id)
        elif isinstance(base, ast.Attribute):
            names.append(base.attr)
        else:
            names.append(ast.unparse(base))
    return names


def _looks_like_scene(bases: list[str]) -> bool:
    return any("Scene" in base for base in bases)


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        if func.value.id == "self":
            return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _event_from_call(node: ast.Call) -> PlayOrWait | None:
    from manim_dock.timeline import play_call_label

    name = _call_name(node)
    if name is None:
        return None
    if name == "play":
        targets, label = play_call_label(node)
        return PlayOrWait("play", label, _line_range(node), targets=targets)
    if name == "wait":
        label = "self.wait(...)"
        if node.args:
            try:
                label = f"self.wait({ast.unparse(node.args[0])})"
            except Exception:
                pass
        return PlayOrWait("wait", label, _line_range(node))
    if name == "next_section":
        label = "self.next_section(...)"
        if node.args:
            try:
                label = f"self.next_section({ast.unparse(node.args[0])})"
            except Exception:
                pass
        elif node.keywords:
            for kw in node.keywords:
                if kw.arg == "name" and kw.value is not None:
                    try:
                        label = f"self.next_section({ast.unparse(kw.value)})"
                    except Exception:
                        pass
                    break
        return PlayOrWait("next_section", label, _line_range(node))
    return None


def _events_in_function(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[PlayOrWait]:
    events: list[PlayOrWait] = []

    class Visitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:
            event = _event_from_call(node)
            if event is not None:
                events.append(event)
            self.generic_visit(node)

    Visitor().visit(fn)
    return events


def _methods_for_scene(class_def: ast.ClassDef) -> list[MethodOutline]:
    methods: list[MethodOutline] = []
    for node in class_def.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):
                # Public beat methods + construct only; skip private/dunder helpers.
                continue
            methods.append(
                MethodOutline(
                    name=node.name,
                    range=_line_range(node),
                    events=_events_in_function(node),
                )
            )
    # Prefer construct first in UI order while keeping definition order otherwise.
    methods.sort(key=lambda m: (0 if m.name == "construct" else 1, m.range.start_line))
    return methods


def parse_source(source: str, path: str = "<memory>") -> FileOutline:
    outline = FileOutline(path=path)
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        outline.errors.append(f"SyntaxError: {exc.msg} (line {exc.lineno})")
        return outline

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        bases = _base_names(node)
        if not _looks_like_scene(bases):
            continue
        outline.scenes.append(
            SceneOutline(
                name=node.name,
                bases=bases,
                range=_line_range(node),
                methods=_methods_for_scene(node),
            )
        )
    return outline


def parse_file(path: str | Path) -> FileOutline:
    file_path = Path(path)
    source = file_path.read_text(encoding="utf-8")
    return parse_source(source, path=str(file_path))
