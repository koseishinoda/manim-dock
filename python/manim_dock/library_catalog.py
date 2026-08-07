"""Browse plain library helper functions for insert snippets (Phase 8)."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


def _module_import_name(library_path: str | Path) -> str:
    """MVP module name for insert snippets.

    Prefer ``lesson_lib`` when the path contains that package (re-exported via
    ``__init__``); otherwise use the file stem.
    """
    path = Path(library_path)
    if "lesson_lib" in path.parts:
        return "lesson_lib"
    return path.stem


def _format_signature(fn: ast.FunctionDef) -> str:
    """Rebuild ``name(args)`` from the AST (no return annotation)."""
    try:
        args_src = ast.unparse(fn.args)
    except Exception:
        args_src = "..."
    return f"{fn.name}({args_src})"


def _doc_first_line(fn: ast.FunctionDef) -> str:
    doc = ast.get_docstring(fn) or ""
    if not doc:
        return ""
    return doc.strip().splitlines()[0].strip()


def list_library_helpers(library_path: str | Path) -> list[dict[str, Any]]:
    """Parse top-level ``def`` functions from a ``.py`` library file.

    Returns a list of ``{name, signature, doc, insert}`` dicts suitable for a
    library browser. Private names (leading ``_``) are skipped.
    """
    path = Path(library_path)
    if not path.is_file():
        raise FileNotFoundError(f"library file not found: {path}")

    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        raise ValueError(f"failed to parse library: {exc}") from exc

    module = _module_import_name(path)
    helpers: list[dict[str, Any]] = []

    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name.startswith("_"):
            continue
        insert = f"from {module} import {node.name}\n{node.name}(self, $0)"
        helpers.append(
            {
                "name": node.name,
                "signature": _format_signature(node),
                "doc": _doc_first_line(node),
                "insert": insert,
            }
        )

    return helpers
