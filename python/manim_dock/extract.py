"""Extract a Scene method into a plain library module (P15) — propose only."""

from __future__ import annotations

import ast
import difflib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import libcst as cst


@dataclass
class ExtractProposal:
    ok: bool
    scene_path: str
    library_path: str
    method: str
    scene_original: str
    scene_proposed: str
    scene_diff: str
    library_original: str
    library_proposed: str
    library_diff: str
    import_name: str
    error: str | None = None
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "scene_path": self.scene_path,
            "library_path": self.library_path,
            "method": self.method,
            "scene_original": self.scene_original,
            "scene_proposed": self.scene_proposed,
            "scene_diff": self.scene_diff,
            "library_original": self.library_original,
            "library_proposed": self.library_proposed,
            "library_diff": self.library_diff,
            "import_name": self.import_name,
            "error": self.error,
            "summary": self.summary,
        }


def _fail(
    *,
    scene_path: str,
    library_path: str,
    method: str,
    scene_original: str,
    library_original: str,
    error: str,
) -> ExtractProposal:
    return ExtractProposal(
        ok=False,
        scene_path=scene_path,
        library_path=library_path,
        method=method,
        scene_original=scene_original,
        scene_proposed=scene_original,
        scene_diff="",
        library_original=library_original,
        library_proposed=library_original,
        library_diff="",
        import_name="",
        error=error,
    )


def _module_import_name(library_path: Path, scene_path: Path) -> str:
    """Best-effort import module path relative to scene parent / package roots."""
    stem = library_path.stem
    parent = library_path.parent
    # Prefer package import: lesson_lib.patterns
    if (parent / "__init__.py").exists():
        return f"{parent.name}.{stem}"
    return stem


class _SelfToScene(cst.CSTTransformer):
    def leave_Name(self, original_node: cst.Name, updated_node: cst.Name) -> cst.Name:
        if updated_node.value == "self":
            return updated_node.with_changes(value="scene")
        return updated_node


def _method_to_library_function(method_src: str, method_name: str) -> str:
    """Turn ``def foo(self): ...`` into ``def foo(scene): ...`` with self→scene."""
    wrapper = cst.parse_module(method_src)
    # Expect a single FunctionDef at module level (dedented method).
    transformed = wrapper.visit(_SelfToScene())
    return transformed.code.strip() + "\n"


def _is_already_extracted_stub(method_node: ast.FunctionDef, method_name: str) -> bool:
    """True when the method body is only ``name(self)`` / ``mod.name(self)``."""
    stmts = list(method_node.body)
    if (
        stmts
        and isinstance(stmts[0], ast.Expr)
        and isinstance(stmts[0].value, ast.Constant)
        and isinstance(stmts[0].value.value, str)
    ):
        stmts = stmts[1:]
    if len(stmts) != 1:
        return False
    stmt = stmts[0]
    if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
        return False
    func = stmt.value.func
    if isinstance(func, ast.Name) and func.id == method_name:
        return True
    if isinstance(func, ast.Attribute) and func.attr == method_name:
        return True
    return False


def _dedent_method(source: str, start: int, end: int) -> str:
    lines = source.splitlines(keepends=True)
    chunk = lines[start - 1 : end]
    # Strip common indent from the def line.
    first = chunk[0]
    match = re.match(r"^(\s*)", first)
    indent = match.group(1) if match else ""
    if not indent:
        return "".join(chunk)
    out: list[str] = []
    for line in chunk:
        if line.startswith(indent):
            out.append(line[len(indent) :])
        else:
            out.append(line.lstrip("\t") if line.strip() else line)
    return "".join(out)


def _ensure_import(module: cst.Module, import_mod: str, name: str) -> cst.Module:
    """Insert ``from import_mod import name`` if missing."""
    already = False
    for stmt in module.body:
        if isinstance(stmt, cst.SimpleStatementLine):
            for small in stmt.body:
                if isinstance(small, cst.ImportFrom):
                    mod = small.module
                    mod_name = ""
                    if isinstance(mod, cst.Name):
                        mod_name = mod.value
                    elif isinstance(mod, cst.Attribute):
                        parts: list[str] = []
                        cur: cst.BaseExpression = mod
                        while isinstance(cur, cst.Attribute):
                            parts.append(cur.attr.value)
                            cur = cur.value
                        if isinstance(cur, cst.Name):
                            parts.append(cur.value)
                        mod_name = ".".join(reversed(parts))
                    if mod_name == import_mod and small.names and not isinstance(
                        small.names, cst.ImportStar
                    ):
                        for alias in small.names:
                            if isinstance(alias, cst.ImportAlias) and isinstance(
                                alias.name, cst.Name
                            ):
                                if alias.name.value == name:
                                    already = True
    if already:
        return module

    import_stmt = cst.parse_statement(f"from {import_mod} import {name}\n")
    body = list(module.body)
    insert_at = 0
    # After module docstring / future imports / existing imports.
    for i, stmt in enumerate(body):
        if isinstance(stmt, cst.SimpleStatementLine):
            if any(isinstance(x, (cst.Import, cst.ImportFrom)) for x in stmt.body):
                insert_at = i + 1
                continue
        if isinstance(stmt, cst.EmptyLine):
            continue
        # Docstring Expr at start
        if (
            i == 0
            and isinstance(stmt, cst.SimpleStatementLine)
            and len(stmt.body) == 1
            and isinstance(stmt.body[0], cst.Expr)
        ):
            insert_at = 1
            continue
        break
    body[insert_at:insert_at] = [import_stmt, cst.EmptyLine()]
    return module.with_changes(body=body)


class _ReplaceMethodBody(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

    def __init__(self, scene_name: str, method_name: str) -> None:
        self.scene_name = scene_name
        self.method_name = method_name
        self.replaced = False
        self._in_scene = False

    def visit_ClassDef(self, node: cst.ClassDef) -> bool:
        self._in_scene = node.name.value == self.scene_name
        return True

    def leave_ClassDef(
        self, original_node: cst.ClassDef, updated_node: cst.ClassDef
    ) -> cst.ClassDef:
        self._in_scene = False
        return updated_node

    def leave_FunctionDef(
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.FunctionDef:
        if not self._in_scene or original_node.name.value != self.method_name:
            return updated_node
        call = cst.parse_statement(f"{self.method_name}(self)\n")
        self.replaced = True
        return updated_node.with_changes(body=cst.IndentedBlock(body=[call]))


def propose_extract_method(
    scene_source: str,
    *,
    scene_path: str,
    scene_name: str,
    method_name: str,
    library_path: str,
    library_source: str | None = None,
) -> ExtractProposal:
    if method_name in {"construct", "__init__"}:
        return _fail(
            scene_path=scene_path,
            library_path=library_path,
            method=method_name,
            scene_original=scene_source,
            library_original=library_source or "",
            error=f"refusing to extract {method_name!r}",
        )

    try:
        tree = ast.parse(scene_source, filename=scene_path)
    except SyntaxError as exc:
        return _fail(
            scene_path=scene_path,
            library_path=library_path,
            method=method_name,
            scene_original=scene_source,
            library_original=library_source or "",
            error=f"SyntaxError: {exc.msg}",
        )

    method_node: ast.FunctionDef | None = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == scene_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    method_node = item
                    break
    if method_node is None:
        return _fail(
            scene_path=scene_path,
            library_path=library_path,
            method=method_name,
            scene_original=scene_source,
            library_original=library_source or "",
            error=f"method {scene_name}.{method_name} not found",
        )

    if _is_already_extracted_stub(method_node, method_name):
        return _fail(
            scene_path=scene_path,
            library_path=library_path,
            method=method_name,
            scene_original=scene_source,
            library_original=library_source or "",
            error=(
                f"{method_name!r} already delegates to a library call — "
                "nothing left to extract"
            ),
        )

    start = method_node.lineno
    end = method_node.end_lineno or start
    method_src = _dedent_method(scene_source, start, end)
    try:
        lib_fn = _method_to_library_function(method_src, method_name)
    except Exception as exc:  # noqa: BLE001
        return _fail(
            scene_path=scene_path,
            library_path=library_path,
            method=method_name,
            scene_original=scene_source,
            library_original=library_source or "",
            error=f"failed to rewrite method: {exc}",
        )

    # Ensure def uses scene param even if transformer missed annotation edge cases.
    lib_fn = re.sub(
        rf"def\s+{re.escape(method_name)}\s*\(\s*scene\s*",
        f"def {method_name}(scene",
        lib_fn,
        count=1,
    )

    lib_path = Path(library_path)
    existing = library_source
    if existing is None and lib_path.is_file():
        existing = lib_path.read_text(encoding="utf-8")
    if existing is None:
        existing = ""

    if existing.strip() == "":
        library_proposed = (
            '"""Extracted Manim helpers — plain ManimCE, no Dock dependency."""\n'
            "\n"
            "from manim import *\n"
            "\n"
            "\n"
            f"{lib_fn}"
        )
    else:
        if re.search(rf"def\s+{re.escape(method_name)}\s*\(", existing):
            return _fail(
                scene_path=scene_path,
                library_path=library_path,
                method=method_name,
                scene_original=scene_source,
                library_original=existing,
                error=f"{method_name!r} already exists in {library_path}",
            )
        sep = "" if existing.endswith("\n\n") else "\n" if existing.endswith("\n") else "\n\n"
        library_proposed = existing + sep + lib_fn

    import_mod = _module_import_name(lib_path, Path(scene_path))

    try:
        scene_module = cst.parse_module(scene_source)
        scene_module = _ensure_import(scene_module, import_mod, method_name)
        wrapper = cst.metadata.MetadataWrapper(scene_module)
        replacer = _ReplaceMethodBody(scene_name, method_name)
        scene_module = wrapper.visit(replacer)
    except Exception as exc:  # noqa: BLE001
        return _fail(
            scene_path=scene_path,
            library_path=library_path,
            method=method_name,
            scene_original=scene_source,
            library_original=existing,
            error=f"scene patch failed: {exc}",
        )

    if not replacer.replaced:
        return _fail(
            scene_path=scene_path,
            library_path=library_path,
            method=method_name,
            scene_original=scene_source,
            library_original=existing,
            error="could not replace scene method body",
        )

    scene_proposed = scene_module.code
    scene_diff = "".join(
        difflib.unified_diff(
            scene_source.splitlines(keepends=True),
            scene_proposed.splitlines(keepends=True),
            fromfile=scene_path,
            tofile=f"{scene_path} (proposed)",
        )
    )
    library_diff = "".join(
        difflib.unified_diff(
            existing.splitlines(keepends=True),
            library_proposed.splitlines(keepends=True),
            fromfile=library_path,
            tofile=f"{library_path} (proposed)",
        )
    )

    return ExtractProposal(
        ok=True,
        scene_path=scene_path,
        library_path=library_path,
        method=method_name,
        scene_original=scene_source,
        scene_proposed=scene_proposed,
        scene_diff=scene_diff,
        library_original=existing,
        library_proposed=library_proposed,
        library_diff=library_diff,
        import_name=import_mod,
        summary=f"extract {scene_name}.{method_name} → {import_mod}.{method_name}",
    )


def propose_extract_method_files(
    scene_path: str,
    scene_name: str,
    method_name: str,
    library_path: str,
) -> ExtractProposal:
    scene_source = Path(scene_path).read_text(encoding="utf-8")
    lib = Path(library_path)
    library_source = lib.read_text(encoding="utf-8") if lib.is_file() else None
    return propose_extract_method(
        scene_source,
        scene_path=scene_path,
        scene_name=scene_name,
        method_name=method_name,
        library_path=library_path,
        library_source=library_source,
    )
