"""Standalone meeting API entry point.

Run with `python -m src.meeting`. Reads `MEETING_PORT` (default 8771) and
`REDIS_URL` (default redis://localhost:6379/0) from the environment.
"""

from __future__ import annotations

import os

from aiohttp import web

from .server import build_app


def main() -> None:
    port = int(os.environ.get("MEETING_PORT", "8771"))
    web.run_app(build_app(), host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
