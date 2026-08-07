"""Surgical timing patches via libcst — propose only; host applies after confirm."""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Any

import libcst as cst


def _fmt_num(value: float) -> str:
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text if text not in {"", "-", "-0"} else "0"


@dataclass
class TimingPatchProposal:
    ok: bool
    path: str
    kind: str
    line: int
    duration: float
    original: str
    proposed: str
    diff: str
    error: str | None = None
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "path": self.path,
            "kind": self.kind,
            "line": self.line,
            "duration": self.duration,
            "original": self.original,
            "proposed": self.proposed,
            "diff": self.diff,
            "error": self.error,
            "summary": self.summary,
        }


def _is_self_attr_call(call: cst.Call, attr: str) -> bool:
    return (
        isinstance(call.func, cst.Attribute)
        and isinstance(call.func.value, cst.Name)
        and call.func.value.value == "self"
        and call.func.attr.value == attr
    )


class _TimingPatcher(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

    def __init__(self, kind: str, line: int, duration: float) -> None:
        self.kind = kind
        self.line = line
        self.duration = duration
        self.expr = _fmt_num(duration)
        self.patched = False

    def leave_Call(self, original_node: cst.Call, updated_node: cst.Call) -> cst.Call:
        if self.patched:
            return updated_node
        try:
            pos = self.get_metadata(cst.metadata.PositionProvider, original_node)
        except Exception:
            return updated_node
        if pos is None or pos.start.line != self.line:
            return updated_node

        if self.kind == "wait" and _is_self_attr_call(original_node, "wait"):
            self.patched = True
            return self._patch_wait(updated_node)
        if self.kind == "play" and _is_self_attr_call(original_node, "play"):
            self.patched = True
            return self._patch_play(updated_node)
        return updated_node

    def _patch_wait(self, node: cst.Call) -> cst.Call:
        new_arg = cst.parse_expression(self.expr)
        if node.args:
            first = node.args[0]
            if isinstance(first, cst.Arg) and first.keyword is None:
                args = list(node.args)
                args[0] = first.with_changes(value=new_arg)
                return node.with_changes(args=args)
        # No positional args — insert duration.
        return node.with_changes(
            args=[cst.Arg(value=new_arg), *list(node.args)]
        )

    def _patch_play(self, node: cst.Call) -> cst.Call:
        new_val = cst.parse_expression(self.expr)
        args = list(node.args)
        for i, arg in enumerate(args):
            if (
                isinstance(arg, cst.Arg)
                and arg.keyword is not None
                and arg.keyword.value == "run_time"
            ):
                args[i] = arg.with_changes(value=new_val)
                return node.with_changes(args=args)
        # Insert run_time= at end.
        runtime_arg = cst.Arg(
            keyword=cst.Name("run_time"),
            equal=cst.AssignEqual(
                whitespace_before=cst.SimpleWhitespace(""),
                whitespace_after=cst.SimpleWhitespace(""),
            ),
            value=new_val,
        )
        if args:
            # Ensure comma separation looks ok — libcst usually handles it.
            last = args[-1]
            if isinstance(last, cst.Arg) and last.comma is None:
                args[-1] = last.with_changes(
                    comma=cst.Comma(whitespace_after=cst.SimpleWhitespace(" "))
                )
        args.append(runtime_arg)
        return node.with_changes(args=args)


def propose_duration(
    source: str,
    *,
    path: str,
    kind: str,
    line: int,
    duration: float,
) -> TimingPatchProposal:
    if kind not in {"play", "wait"}:
        return TimingPatchProposal(
            ok=False,
            path=path,
            kind=kind,
            line=line,
            duration=duration,
            original=source,
            proposed=source,
            diff="",
            error=f"unsupported kind: {kind}",
        )
    if duration < 0:
        return TimingPatchProposal(
            ok=False,
            path=path,
            kind=kind,
            line=line,
            duration=duration,
            original=source,
            proposed=source,
            diff="",
            error="duration must be non-negative",
        )

    try:
        module = cst.parse_module(source)
    except Exception as exc:  # noqa: BLE001
        return TimingPatchProposal(
            ok=False,
            path=path,
            kind=kind,
            line=line,
            duration=duration,
            original=source,
            proposed=source,
            diff="",
            error=f"libcst parse failed: {exc}",
        )

    wrapper = cst.metadata.MetadataWrapper(module)
    patcher = _TimingPatcher(kind, line, duration)
    try:
        new_module = wrapper.visit(patcher)
    except Exception as exc:  # noqa: BLE001
        return TimingPatchProposal(
            ok=False,
            path=path,
            kind=kind,
            line=line,
            duration=duration,
            original=source,
            proposed=source,
            diff="",
            error=f"patch failed: {exc}",
        )

    if not patcher.patched:
        return TimingPatchProposal(
            ok=False,
            path=path,
            kind=kind,
            line=line,
            duration=duration,
            original=source,
            proposed=source,
            diff="",
            error=f"no self.{kind}(...) found on line {line}",
        )

    proposed = new_module.code
    if proposed == source:
        return TimingPatchProposal(
            ok=False,
            path=path,
            kind=kind,
            line=line,
            duration=duration,
            original=source,
            proposed=source,
            diff="",
            error="patch produced no textual change",
        )

    diff = "".join(
        difflib.unified_diff(
            source.splitlines(keepends=True),
            proposed.splitlines(keepends=True),
            fromfile=path,
            tofile=f"{path} (proposed)",
        )
    )
    if kind == "wait":
        summary = f"set wait → {_fmt_num(duration)}s (line {line})"
    else:
        summary = f"set run_time → {_fmt_num(duration)}s (line {line})"
    return TimingPatchProposal(
        ok=True,
        path=path,
        kind=kind,
        line=line,
        duration=duration,
        original=source,
        proposed=proposed,
        diff=diff,
        summary=summary,
    )


def propose_duration_file(
    path: str, kind: str, line: int, duration: float
) -> TimingPatchProposal:
    from pathlib import Path

    source = Path(path).read_text(encoding="utf-8")
    return propose_duration(
        source, path=path, kind=kind, line=line, duration=duration
    )


@dataclass
class ReorderPatchProposal:
    ok: bool
    path: str
    line_a: int
    line_b: int
    original: str
    proposed: str
    diff: str
    error: str | None = None
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "path": self.path,
            "line_a": self.line_a,
            "line_b": self.line_b,
            "original": self.original,
            "proposed": self.proposed,
            "diff": self.diff,
            "error": self.error,
            "summary": self.summary,
        }


def _is_play_or_wait_stmt(stmt: cst.CSTNode) -> bool:
    if not isinstance(stmt, cst.SimpleStatementLine):
        return False
    if len(stmt.body) != 1 or not isinstance(stmt.body[0], cst.Expr):
        return False
    call = stmt.body[0].value
    if not isinstance(call, cst.Call):
        return False
    return _is_self_attr_call(call, "play") or _is_self_attr_call(call, "wait")


def _play_wait_label(stmt: cst.SimpleStatementLine) -> str:
    call = stmt.body[0].value
    assert isinstance(call, cst.Call)
    assert isinstance(call.func, cst.Attribute)
    return call.func.attr.value


class _ReorderPatcher(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

    def __init__(self, line_a: int, line_b: int) -> None:
        self.line_a = line_a
        self.line_b = line_b
        self.patched = False
        self.error: str | None = None

    def _maybe_patch(
        self,
        original_node: cst.FunctionDef | cst.AsyncFunctionDef,
        updated_node: cst.FunctionDef | cst.AsyncFunctionDef,
    ) -> cst.FunctionDef | cst.AsyncFunctionDef:
        if self.patched or self.error is not None:
            return updated_node

        orig_block = original_node.body
        if not isinstance(orig_block, cst.IndentedBlock):
            return updated_node

        idx_a: int | None = None
        idx_b: int | None = None
        for i, stmt in enumerate(orig_block.body):
            try:
                pos = self.get_metadata(cst.metadata.PositionProvider, stmt)
            except Exception:
                continue
            if pos is None:
                continue
            if pos.start.line == self.line_a:
                idx_a = i
            if pos.start.line == self.line_b:
                idx_b = i

        if idx_a is None or idx_b is None:
            return updated_node

        if idx_a == idx_b:
            self.error = "line_a and line_b refer to the same statement"
            return updated_node

        upd_block = updated_node.body
        if not isinstance(upd_block, cst.IndentedBlock):
            return updated_node

        statements = list(upd_block.body)
        stmt_a = statements[idx_a]
        stmt_b = statements[idx_b]
        if not _is_play_or_wait_stmt(stmt_a) or not _is_play_or_wait_stmt(stmt_b):
            self.error = (
                "both lines must be SimpleStatementLine self.play(...) or self.wait(...)"
            )
            return updated_node

        lo, hi = (idx_a, idx_b) if idx_a < idx_b else (idx_b, idx_a)
        for i in range(lo, hi + 1):
            if not _is_play_or_wait_stmt(statements[i]):
                self.error = (
                    "play/wait statements are not in a contiguous block "
                    "(intervening logic or non-play/wait between them)"
                )
                return updated_node

        # Move statement at idx_a into the slot currently occupied by idx_b.
        moving = statements.pop(idx_a)
        insert_at = idx_b if idx_a > idx_b else idx_b
        # After pop when idx_a < idx_b, indices after idx_a shift down by 1;
        # inserting at original idx_b places the item at that final index.
        statements.insert(insert_at, moving)
        self.patched = True
        assert isinstance(stmt_a, cst.SimpleStatementLine)
        assert isinstance(stmt_b, cst.SimpleStatementLine)
        self._label_a = _play_wait_label(stmt_a)
        self._label_b = _play_wait_label(stmt_b)
        return updated_node.with_changes(
            body=upd_block.with_changes(body=statements)
        )

    def leave_FunctionDef(
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.FunctionDef:
        return self._maybe_patch(original_node, updated_node)  # type: ignore[return-value]

    def leave_AsyncFunctionDef(
        self, original_node: cst.AsyncFunctionDef, updated_node: cst.AsyncFunctionDef
    ) -> cst.AsyncFunctionDef:
        return self._maybe_patch(original_node, updated_node)  # type: ignore[return-value]


def propose_reorder(
    source: str,
    *,
    path: str,
    line_a: int,
    line_b: int,
) -> ReorderPatchProposal:
    """Move ``self.play`` / ``self.wait`` at line_a into line_b's slot.

    Requires a contiguous play/wait block between the two lines (adjacent swap
    is the common case).
    """

    def _fail(error: str) -> ReorderPatchProposal:
        return ReorderPatchProposal(
            ok=False,
            path=path,
            line_a=line_a,
            line_b=line_b,
            original=source,
            proposed=source,
            diff="",
            error=error,
        )

    if line_a == line_b:
        return _fail("line_a and line_b must differ")

    try:
        module = cst.parse_module(source)
    except Exception as exc:  # noqa: BLE001
        return _fail(f"libcst parse failed: {exc}")

    wrapper = cst.metadata.MetadataWrapper(module)
    patcher = _ReorderPatcher(line_a, line_b)
    try:
        new_module = wrapper.visit(patcher)
    except Exception as exc:  # noqa: BLE001
        return _fail(f"patch failed: {exc}")

    if patcher.error is not None:
        return _fail(patcher.error)

    if not patcher.patched:
        return _fail(
            f"could not find self.play/wait statements on lines {line_a} and {line_b}"
        )

    proposed = new_module.code
    if proposed == source:
        return _fail("patch produced no textual change")

    diff = "".join(
        difflib.unified_diff(
            source.splitlines(keepends=True),
            proposed.splitlines(keepends=True),
            fromfile=path,
            tofile=f"{path} (proposed)",
        )
    )
    label_a = getattr(patcher, "_label_a", "play/wait")
    label_b = getattr(patcher, "_label_b", "play/wait")
    summary = f"move self.{label_a} (L{line_a}) → L{line_b} (was self.{label_b})"
    return ReorderPatchProposal(
        ok=True,
        path=path,
        line_a=line_a,
        line_b=line_b,
        original=source,
        proposed=proposed,
        diff=diff,
        summary=summary,
    )


def propose_reorder_file(path: str, line_a: int, line_b: int) -> ReorderPatchProposal:
    from pathlib import Path

    source = Path(path).read_text(encoding="utf-8")
    return propose_reorder(source, path=path, line_a=line_a, line_b=line_b)


def _is_next_section_stmt(stmt: cst.CSTNode) -> bool:
    if not isinstance(stmt, cst.SimpleStatementLine):
        return False
    if len(stmt.body) != 1 or not isinstance(stmt.body[0], cst.Expr):
        return False
    call = stmt.body[0].value
    if not isinstance(call, cst.Call):
        return False
    return _is_self_attr_call(call, "next_section")


def _section_label_from_stmt(stmt: cst.SimpleStatementLine) -> str:
    call = stmt.body[0].value
    assert isinstance(call, cst.Call)
    for arg in call.args:
        if arg.keyword is None:
            if isinstance(arg.value, cst.SimpleString):
                try:
                    val = arg.value.evaluated_value
                    if isinstance(val, str):
                        return val
                except Exception:
                    raw = arg.value.value
                    if len(raw) >= 2 and raw[0] in {"'", '"'} and raw[-1] == raw[0]:
                        return raw[1:-1]
            try:
                return cst.Module([]).code_for_node(arg.value).strip("\"'")
            except Exception:
                return "section"
    for arg in call.args:
        if arg.keyword is not None and arg.keyword.value == "name":
            if isinstance(arg.value, cst.SimpleString):
                try:
                    val = arg.value.evaluated_value
                    if isinstance(val, str):
                        return val
                except Exception:
                    pass
            return "section"
    return "section"


def _section_block_end(statements: list[cst.BaseStatement], start: int) -> int:
    """Exclusive end index of the section block starting at ``start``."""
    end = start + 1
    while end < len(statements):
        if _is_next_section_stmt(statements[end]):
            break
        end += 1
    return end


class _SectionReorderPatcher(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

    def __init__(self, line_a: int, line_b: int) -> None:
        self.line_a = line_a
        self.line_b = line_b
        self.patched = False
        self.error: str | None = None
        self._label_a = "section"
        self._label_b = "section"

    def _maybe_patch(
        self,
        original_node: cst.FunctionDef | cst.AsyncFunctionDef,
        updated_node: cst.FunctionDef | cst.AsyncFunctionDef,
    ) -> cst.FunctionDef | cst.AsyncFunctionDef:
        if self.patched or self.error is not None:
            return updated_node

        orig_block = original_node.body
        if not isinstance(orig_block, cst.IndentedBlock):
            return updated_node

        idx_a: int | None = None
        idx_b: int | None = None
        for i, stmt in enumerate(orig_block.body):
            try:
                pos = self.get_metadata(cst.metadata.PositionProvider, stmt)
            except Exception:
                continue
            if pos is None:
                continue
            if pos.start.line == self.line_a:
                idx_a = i
            if pos.start.line == self.line_b:
                idx_b = i

        if idx_a is None or idx_b is None:
            return updated_node

        if idx_a == idx_b:
            self.error = "line_a and line_b refer to the same statement"
            return updated_node

        statements_orig = list(orig_block.body)
        if not _is_next_section_stmt(statements_orig[idx_a]) or not _is_next_section_stmt(
            statements_orig[idx_b]
        ):
            self.error = (
                "both lines must be SimpleStatementLine self.next_section(...)"
            )
            return updated_node

        # Adjacent among next_section markers in this function body.
        section_indices = [
            i for i, stmt in enumerate(statements_orig) if _is_next_section_stmt(stmt)
        ]
        try:
            pos_a = section_indices.index(idx_a)
            pos_b = section_indices.index(idx_b)
        except ValueError:
            self.error = "could not locate next_section statements in function body"
            return updated_node

        if abs(pos_a - pos_b) != 1:
            self.error = (
                "next_section markers are not adjacent section blocks "
                "(another section lies between them)"
            )
            return updated_node

        # Normalize so first < second in source order.
        if idx_a < idx_b:
            first_idx, second_idx = idx_a, idx_b
            first_line, second_line = self.line_a, self.line_b
        else:
            first_idx, second_idx = idx_b, idx_a
            first_line, second_line = self.line_b, self.line_a

        # Block A must end exactly where block B's next_section begins.
        end_first = _section_block_end(statements_orig, first_idx)
        if end_first != second_idx:
            self.error = (
                "section blocks are not neighbors in the function body "
                "(intervening statements outside either block)"
            )
            return updated_node

        end_second = _section_block_end(statements_orig, second_idx)

        upd_block = updated_node.body
        if not isinstance(upd_block, cst.IndentedBlock):
            return updated_node

        statements = list(upd_block.body)
        block_first = statements[first_idx:end_first]
        block_second = statements[second_idx:end_second]
        if not block_first or not block_second:
            self.error = "empty section block — refusing swap"
            return updated_node

        # Safety: each block must start with its next_section.
        if not _is_next_section_stmt(block_first[0]) or not _is_next_section_stmt(
            block_second[0]
        ):
            self.error = "section block does not start with next_section"
            return updated_node

        assert isinstance(block_first[0], cst.SimpleStatementLine)
        assert isinstance(block_second[0], cst.SimpleStatementLine)
        # Labels follow the caller's line_a / line_b order for the summary.
        if first_line == self.line_a:
            self._label_a = _section_label_from_stmt(block_first[0])
            self._label_b = _section_label_from_stmt(block_second[0])
        else:
            self._label_a = _section_label_from_stmt(block_second[0])
            self._label_b = _section_label_from_stmt(block_first[0])

        new_statements = (
            statements[:first_idx]
            + block_second
            + block_first
            + statements[end_second:]
        )
        self.patched = True
        return updated_node.with_changes(
            body=upd_block.with_changes(body=new_statements)
        )

    def leave_FunctionDef(
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.FunctionDef:
        return self._maybe_patch(original_node, updated_node)  # type: ignore[return-value]

    def leave_AsyncFunctionDef(
        self, original_node: cst.AsyncFunctionDef, updated_node: cst.AsyncFunctionDef
    ) -> cst.AsyncFunctionDef:
        return self._maybe_patch(original_node, updated_node)  # type: ignore[return-value]


def propose_section_reorder(
    source: str,
    *,
    path: str,
    line_a: int,
    line_b: int,
) -> ReorderPatchProposal:
    """Swap two adjacent ``next_section`` blocks in the same function body.

    A section block is the ``self.next_section(...)`` call plus following
    statements until the next ``next_section`` (or end of the function).
    """

    def _fail(error: str) -> ReorderPatchProposal:
        return ReorderPatchProposal(
            ok=False,
            path=path,
            line_a=line_a,
            line_b=line_b,
            original=source,
            proposed=source,
            diff="",
            error=error,
        )

    if line_a == line_b:
        return _fail("line_a and line_b must differ")

    try:
        module = cst.parse_module(source)
    except Exception as exc:  # noqa: BLE001
        return _fail(f"libcst parse failed: {exc}")

    wrapper = cst.metadata.MetadataWrapper(module)
    patcher = _SectionReorderPatcher(line_a, line_b)
    try:
        new_module = wrapper.visit(patcher)
    except Exception as exc:  # noqa: BLE001
        return _fail(f"patch failed: {exc}")

    if patcher.error is not None:
        return _fail(patcher.error)

    if not patcher.patched:
        return _fail(
            f"could not find self.next_section statements on lines {line_a} and {line_b}"
        )

    proposed = new_module.code
    if proposed == source:
        return _fail("patch produced no textual change")

    diff = "".join(
        difflib.unified_diff(
            source.splitlines(keepends=True),
            proposed.splitlines(keepends=True),
            fromfile=path,
            tofile=f"{path} (proposed)",
        )
    )
    summary = (
        f"swap section {patcher._label_a!r} (L{line_a}) "
        f"↔ {patcher._label_b!r} (L{line_b})"
    )
    return ReorderPatchProposal(
        ok=True,
        path=path,
        line_a=line_a,
        line_b=line_b,
        original=source,
        proposed=proposed,
        diff=diff,
        summary=summary,
    )


def propose_section_reorder_file(
    path: str, line_a: int, line_b: int
) -> ReorderPatchProposal:
    from pathlib import Path

    source = Path(path).read_text(encoding="utf-8")
    return propose_section_reorder(source, path=path, line_a=line_a, line_b=line_b)


def same_section(section_a: str | None, section_b: str | None) -> bool:
    """True when two timeline events share the same enclosing section label."""
    return (section_a or "") == (section_b or "")
