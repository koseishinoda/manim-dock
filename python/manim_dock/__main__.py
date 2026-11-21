"""CLI entry: ``python -m manim_dock`` or ``python -m manim_dock serve``."""

from __future__ import annotations

import sys


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        # Persistent stdio JSON worker for the extension host (warm Manim).
        from manim_dock.server import serve

        serve()
        return
    from manim_dock.cli import main as cli_main

    raise SystemExit(cli_main())


if __name__ == "__main__":
    main()
