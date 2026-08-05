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
