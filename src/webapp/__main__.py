"""Standalone webapp entry point.

Run with `python -m src.webapp`. Reads `WEBAPP_PORT` (default 8765) and
`REDIS_URL` (default redis://localhost:6379/0) from the environment.
"""

from __future__ import annotations

import os

from aiohttp import web

from .server import build_app


def main() -> None:
    port = int(os.environ.get("WEBAPP_PORT", "8765"))
    web.run_app(build_app(), host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
