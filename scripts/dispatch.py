"""Thin CLI wrapper that POSTs to the local dispatch service.

The actual dispatch (room creation, token minting, agent dispatch) runs in
the dispatch container at $DISPATCH_URL. This script just relays a single
request and prints the URLs from the response.

Usage:
    python scripts/dispatch.py --briefing briefings/01_dwh_requirements.md --target-minutes 30
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--briefing", type=Path, required=True)
    parser.add_argument("--target-minutes", type=int, required=True)
    parser.add_argument(
        "--dispatch-url",
        default=os.environ.get("DISPATCH_URL", "http://localhost:8766"),
        help="Base URL of the dispatch service (default: $DISPATCH_URL or http://localhost:8766)",
    )
    args = parser.parse_args()

    # Send the path as given (typically relative to repo root). The dispatch
    # container resolves it inside /app, where ./briefings is mounted at the
    # same relative location.
    body = json.dumps({
        "briefing_path": str(args.briefing),
        "target_minutes": args.target_minutes,
    }).encode()
    req = urllib.request.Request(
        f"{args.dispatch_url.rstrip('/')}/dispatch",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"dispatch failed ({e.code}): {e.read().decode()}\n")
        sys.exit(1)
    except urllib.error.URLError as e:
        sys.stderr.write(
            f"could not reach dispatch service at {args.dispatch_url}: {e.reason}\n"
            f"is the dispatch container running? `docker compose up -d`\n"
        )
        sys.exit(1)

    print(f"run_id        {payload['run_id']}")
    print(f"room          {payload['room']}")
    print(f"briefing      {payload['briefing_path']}")
    print(f"target_min    {payload['target_minutes']}")
    print()
    print("Open this URL in a browser, allow mic, and join:")
    print(payload["join_url"])
    print()
    print("Shared view (read-only):")
    print(payload["webapp_url"])


if __name__ == "__main__":
    main()
