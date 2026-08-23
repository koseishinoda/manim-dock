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

from manim_dock.extract import propose_extract_method_files
from manim_dock.library_catalog import list_library_helpers
from manim_dock.outline import parse_file
from manim_dock.patch_timing import (
    propose_duration_file,
    propose_reorder_file,
    propose_section_reorder_file,
)
from manim_dock.render import render_scene
from manim_dock.snapshot import snapshot_at_line
from manim_dock.timeline import parse_file_timeline


def _handle(method: str, params: dict[str, Any]) -> Any:
    if method == "ping":
        return {"ok": True}
    if method == "outline":
        path = params.get("path")
        if not path:
            raise ValueError("params.path is required")
        return parse_file(path).to_dict()
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
    if method == "propose_section_reorder":
        path = params.get("path")
        line_a = params.get("line_a")
        line_b = params.get("line_b")
        if not path or line_a is None or line_b is None:
            raise ValueError("params.path, params.line_a, and params.line_b are required")
        source = params.get("source")
        if isinstance(source, str):
            from manim_dock.patch_timing import propose_section_reorder

            return propose_section_reorder(
                source,
                path=str(path),
                line_a=int(line_a),
                line_b=int(line_b),
            ).to_dict()
        return propose_section_reorder_file(
            str(path), int(line_a), int(line_b)
        ).to_dict()
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
    if method == "snapshot":
        path = params.get("path")
        scene = params.get("scene")
        active = params.get("active_until_line")
        if not path or not scene or active is None:
            raise ValueError(
                "params.path, params.scene, and params.active_until_line are required"
            )
        quality = params.get("quality") or "l"
        timeout = params.get("timeout")
        source = params.get("source")
        return snapshot_at_line(
            path,
            str(scene),
            int(active),
            source=source if isinstance(source, str) else None,
            quality=str(quality),
            timeout=int(timeout) if timeout is not None else None,
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
        method_name = params.get("method")
        render_method = str(method_name) if method_name else None
        return render_scene(
            path,
            scene,
            quality=str(quality),
            save_sections=save_sections,
            skip_until_section=skip_until_section,
            method=render_method,
        ).to_dict()
    if method == "library_catalog":
        library_path = params.get("path") or params.get("library_path")
        if not library_path:
            raise ValueError("params.path (library .py) is required")
        helpers = list_library_helpers(str(library_path))
        return {"ok": True, "helpers": helpers}
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
