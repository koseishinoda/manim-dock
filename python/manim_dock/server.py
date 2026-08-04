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
from manim_dock.outline import parse_file


def _handle(method: str, params: dict[str, Any]) -> Any:
    if method == "ping":
        return {"ok": True}
    if method == "outline":
        path = params.get("path")
        if not path:
            raise ValueError("params.path is required")
        return parse_file(path).to_dict()
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
