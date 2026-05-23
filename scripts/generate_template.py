"""Thin CLI wrapper that POSTs to the local template-generator service.

The actual generation (impl+critique loop, OpenAI calls, persistence) runs in
the template-generator container at $TEMPLATE_GEN_URL. This script just
relays a single request and prints a summary of the response.

Usage:
    python scripts/generate_template.py \\
        --description "Design review for the data ingestion pipeline rewrite" \\
        --reference requirements \\
        --max-iterations 3
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--description",
        required=True,
        help="Free-form description of the meeting to design a template for.",
    )
    parser.add_argument(
        "--reference",
        default=None,
        help="Optional reference template name (requirements / research / eval / generic).",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="Hard cap on impl+critique cycles (default: 3).",
    )
    parser.add_argument(
        "--name-hint",
        default=None,
        help="Optional snake_case identifier suggestion.",
    )
    parser.add_argument(
        "--template-gen-url",
        default=os.environ.get("TEMPLATE_GEN_URL", "http://localhost:8768"),
    )
    parser.add_argument(
        "--print-template",
        action="store_true",
        help="Print the final template JSON to stdout instead of a summary.",
    )
    args = parser.parse_args()

    body: dict = {
        "description": args.description,
        "max_iterations": args.max_iterations,
    }
    if args.reference:
        body["reference_template"] = args.reference
    if args.name_hint:
        body["name_hint"] = args.name_hint

    req = urllib.request.Request(
        f"{args.template_gen_url.rstrip('/')}/generate",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        # Generation can take a while: 3 iterations × 2 LLM calls each.
        with urllib.request.urlopen(req, timeout=300) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"generation failed ({e.code}): {e.read().decode()}\n")
        sys.exit(1)
    except urllib.error.URLError as e:
        sys.stderr.write(
            f"could not reach template-generator at {args.template_gen_url}: {e.reason}\n"
            f"is the container running? `docker compose up -d template-generator`\n"
        )
        sys.exit(1)

    if args.print_template:
        print(json.dumps(payload["template"], indent=2))
        return

    print(f"template_id       {payload['template_id']}")
    print(f"storage_path      {payload['storage_path']}")
    print(f"approved          {payload['approved']}")
    print(f"iterations_used   {payload['iterations_used']}")
    print()
    print("Final template:")
    print(f"  name        {payload['template']['name']}")
    print(f"  description {payload['template']['description']}")
    print(f"  sections    {[s['id'] for s in payload['template']['sections']]}")
    print(f"  phases      {[p['id'] for p in payload['template']['phases']]}")
    print()
    print("Critique trail:")
    for it in payload["iterations"]:
        c = it["critique"]
        print(
            f"  #{it['iteration']:>2} approved={c['approved']} "
            f"issues={len(c['issues'])} "
            f"focus={c.get('next_iteration_focus') or '-'}"
        )


if __name__ == "__main__":
    main()
