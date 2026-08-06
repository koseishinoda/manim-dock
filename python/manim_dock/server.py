"""Minimal stdio JSON-RPC-ish server for the VS Code extension host.

Protocol (one JSON object per line):
  → {"id": 1, "method": "outline", "params": {"path": "..."}}
  ← {"id": 1, "result": {...}}
  ← {"id": 1, "error": {"message": "..."}}
"""

from __future__ import annotations

import json
import sys
from typing import Any

from manim_dock.doctor import run_doctor
from manim_dock.extract import propose_extract_method_files
from manim_dock.layout import parse_file_layout
from manim_dock.outline import parse_file
from manim_dock.patch_layout import (
    propose_buff_file,
    propose_scale_file,
    propose_shift_file,
)
from manim_dock.patch_timing import propose_duration_file, propose_reorder_file
from manim_dock.render import render_scene
from manim_dock.timeline import parse_file_timeline


def _handle(method: str, params: dict[str, Any]) -> Any:
    if method == "ping":
        return {"ok": True}
    if method == "outline":
        path = params.get("path")
        if not path:
            raise ValueError("params.path is required")
        return parse_file(path).to_dict()
    if method == "layout":
        path = params.get("path")
        scene = params.get("scene")
        if not path or not scene:
            raise ValueError("params.path and params.scene are required")
        source = params.get("source")
        if isinstance(source, str):
            from manim_dock.layout import parse_scene_layout

            return parse_scene_layout(source, str(path), str(scene)).to_dict()
        return parse_file_layout(path, str(scene)).to_dict()
    if method == "propose_shift":
        path = params.get("path")
        name = params.get("name")
        if not path or not name:
            raise ValueError("params.path and params.name are required")
        dx = float(params.get("dx") or 0)
        dy = float(params.get("dy") or 0)
        anchor = params.get("anchor_line")
        anchor_line = int(anchor) if anchor is not None else None
        source = params.get("source")
        if isinstance(source, str):
            from manim_dock.patch_layout import propose_shift

            return propose_shift(
                source,
                path=str(path),
                name=str(name),
                dx=dx,
                dy=dy,
                anchor_line=anchor_line,
            ).to_dict()
        return propose_shift_file(str(path), str(name), dx, dy, anchor_line).to_dict()
    if method == "timeline":
        path = params.get("path")
        scene = params.get("scene")
        if not path or not scene:
            raise ValueError("params.path and params.scene are required")
        source = params.get("source")
        if isinstance(source, str):
            from manim_dock.timeline import parse_scene_timeline

            return parse_scene_timeline(source, str(path), str(scene)).to_dict()
        return parse_file_timeline(path, str(scene)).to_dict()
    if method == "propose_duration":
        path = params.get("path")
        kind = params.get("kind")
        line = params.get("line")
        if not path or not kind or line is None:
            raise ValueError("params.path, params.kind, and params.line are required")
        duration = float(params.get("duration") or 0)
        source = params.get("source")
        if isinstance(source, str):
            from manim_dock.patch_timing import propose_duration

            return propose_duration(
                source,
                path=str(path),
                kind=str(kind),
                line=int(line),
                duration=duration,
            ).to_dict()
        return propose_duration_file(
            str(path), str(kind), int(line), duration
        ).to_dict()
    if method == "propose_buff":
        path = params.get("path")
        name = params.get("name")
        if not path or not name:
            raise ValueError("params.path and params.name are required")
        if params.get("buff") is None:
            raise ValueError("params.buff is required")
        buff = float(params.get("buff"))
        anchor = params.get("anchor_line")
        anchor_line = int(anchor) if anchor is not None else None
        source = params.get("source")
        if isinstance(source, str):
            from manim_dock.patch_layout import propose_buff

            return propose_buff(
                source,
                path=str(path),
                name=str(name),
                buff=buff,
                anchor_line=anchor_line,
            ).to_dict()
        return propose_buff_file(str(path), str(name), buff, anchor_line).to_dict()
    if method == "propose_scale":
        path = params.get("path")
        name = params.get("name")
        if not path or not name:
            raise ValueError("params.path and params.name are required")
        if params.get("factor") is None:
            raise ValueError("params.factor is required")
        factor = float(params.get("factor"))
        anchor = params.get("anchor_line")
        anchor_line = int(anchor) if anchor is not None else None
        source = params.get("source")
        if isinstance(source, str):
            from manim_dock.patch_layout import propose_scale

            return propose_scale(
                source,
                path=str(path),
                name=str(name),
                factor=factor,
                anchor_line=anchor_line,
            ).to_dict()
        return propose_scale_file(str(path), str(name), factor, anchor_line).to_dict()
    if method == "propose_reorder":
        path = params.get("path")
        line_a = params.get("line_a")
        line_b = params.get("line_b")
        if not path or line_a is None or line_b is None:
            raise ValueError("params.path, params.line_a, and params.line_b are required")
        source = params.get("source")
        if isinstance(source, str):
            from manim_dock.patch_timing import propose_reorder

            return propose_reorder(
                source,
                path=str(path),
                line_a=int(line_a),
                line_b=int(line_b),
            ).to_dict()
        return propose_reorder_file(str(path), int(line_a), int(line_b)).to_dict()
    if method == "extract_method":
        path = params.get("path")
        scene = params.get("scene")
        method_name = params.get("method")
        library_path = params.get("library_path")
        if not path or not scene or not method_name or not library_path:
            raise ValueError(
                "params.path, params.scene, params.method, and params.library_path are required"
            )
        source = params.get("source")
        library_source = params.get("library_source")
        if isinstance(source, str):
            from manim_dock.extract import propose_extract_method

            return propose_extract_method(
                source,
                scene_path=str(path),
                scene_name=str(scene),
                method_name=str(method_name),
                library_path=str(library_path),
                library_source=library_source
                if isinstance(library_source, str)
                else None,
            ).to_dict()
        return propose_extract_method_files(
            str(path), str(scene), str(method_name), str(library_path)
        ).to_dict()
    if method == "render":
        path = params.get("path")
        scene = params.get("scene")
        if not path or not scene:
            raise ValueError("params.path and params.scene are required")
        quality = params.get("quality") or "l"
        save_sections = bool(params.get("save_sections") or False)
        skip_until = params.get("skip_until_section")
        skip_until_section = str(skip_until) if skip_until else None
        return render_scene(
            path,
            scene,
            quality=str(quality),
            save_sections=save_sections,
            skip_until_section=skip_until_section,
        ).to_dict()
    if method == "doctor":
        return {"probes": [p.to_dict() for p in run_doctor()]}
    raise ValueError(f"unknown method: {method}")


def serve() -> None:
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        response: dict[str, Any]
        try:
            request = json.loads(line)
            req_id = request.get("id")
            method = request.get("method")
            params = request.get("params") or {}
            if not isinstance(method, str):
                raise ValueError("method must be a string")
            result = _handle(method, params)
            response = {"id": req_id, "result": result}
        except Exception as exc:  # noqa: BLE001 — boundary for RPC
            response = {
                "id": request.get("id") if "request" in locals() else None,
                "error": {"message": str(exc)},
            }
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    serve()
