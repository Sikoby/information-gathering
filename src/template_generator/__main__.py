"""Long-running template-generator HTTP service.

Endpoints:

- `POST /generate` — runs the impl+critique loop, persists artefacts, returns the final template + iteration history.
- `GET /templates` — lists template_ids already on disk.
- `GET /templates/{id}` — returns a previously generated template + history.
- `GET /healthz` — 200 iff `OPENAI_API_KEY` is set and `TEMPLATES_DIR` exists.

Persistence layout (per generation):

    templates_generated/<template_id>/
      request.json       the originating GenerateRequest
      template.json      the final Template
      iterations.jsonl   one JSON line per (template, critique) iteration
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import web
from dotenv import load_dotenv
from loguru import logger
from pydantic import ValidationError

from .generator import (
    DEFAULT_CRITIQUE_MODEL,
    DEFAULT_IMPL_MODEL,
    generate,
)
from .schemas import (
    GenerateRequest,
    GenerateResponse,
    GenerationIteration,
)


_DEFAULT_TEMPLATES_DIR = Path("/app/templates_generated")
_ID_SAFE_RE = re.compile(r"[^a-z0-9_-]+")


def _templates_dir() -> Path:
    return Path(os.environ.get("TEMPLATES_DIR", str(_DEFAULT_TEMPLATES_DIR)))


def _slugify(value: str) -> str:
    value = value.strip().lower().replace(" ", "_")
    value = _ID_SAFE_RE.sub("", value)
    return value or "template"


def _make_template_id(name: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"{_slugify(name)}-{ts}"


def _persist(
    template_id: str,
    request: GenerateRequest,
    iterations: list[GenerationIteration],
    final_template_json: str,
) -> Path:
    root = _templates_dir() / template_id
    root.mkdir(parents=True, exist_ok=True)

    (root / "request.json").write_text(request.model_dump_json(indent=2))
    (root / "template.json").write_text(final_template_json)
    with (root / "iterations.jsonl").open("w") as f:
        for it in iterations:
            f.write(it.model_dump_json() + "\n")
    return root


async def _post_generate(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "invalid JSON body"}, status=400)

    try:
        gen_request = GenerateRequest.model_validate(body)
    except ValidationError as e:
        return web.json_response(
            {"error": "invalid request", "details": json.loads(e.json())},
            status=400,
        )

    try:
        result = await generate(gen_request)
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)
    except Exception as e:
        logger.exception("generation failed")
        return web.json_response({"error": str(e)}, status=500)

    template_id = _make_template_id(result.template.name)
    final_template_json = result.template.model_dump_json(indent=2)
    storage_path = _persist(
        template_id, gen_request, result.iterations, final_template_json
    )

    response = GenerateResponse(
        template_id=template_id,
        storage_path=str(storage_path),
        approved=result.approved,
        iterations_used=len(result.iterations),
        template=result.template,
        iterations=result.iterations,
    )
    logger.info(
        "generated template_id={} approved={} iterations={}",
        template_id,
        result.approved,
        len(result.iterations),
    )
    return web.json_response(json.loads(response.model_dump_json()))


async def _get_templates(_request: web.Request) -> web.Response:
    root = _templates_dir()
    if not root.exists():
        return web.json_response({"templates": []})
    ids = sorted(p.name for p in root.iterdir() if p.is_dir())
    return web.json_response({"templates": ids})


async def _get_template_by_id(request: web.Request) -> web.Response:
    template_id = request.match_info["template_id"]
    if "/" in template_id or template_id in {".", ".."}:
        return web.json_response({"error": "invalid template_id"}, status=400)

    folder = _templates_dir() / template_id
    if not folder.is_dir():
        return web.json_response({"error": "not found"}, status=404)

    try:
        template_data = json.loads((folder / "template.json").read_text())
        request_data = json.loads((folder / "request.json").read_text())
        iterations: list[dict] = []
        iter_file = folder / "iterations.jsonl"
        if iter_file.exists():
            for line in iter_file.read_text().splitlines():
                if line.strip():
                    iterations.append(json.loads(line))
    except (OSError, json.JSONDecodeError) as e:
        return web.json_response({"error": f"failed to read: {e}"}, status=500)

    return web.json_response(
        {
            "template_id": template_id,
            "storage_path": str(folder),
            "request": request_data,
            "template": template_data,
            "iterations": iterations,
        }
    )


async def _get_healthz(_request: web.Request) -> web.Response:
    if not os.environ.get("OPENAI_API_KEY"):
        return web.Response(status=503, text="missing env var: OPENAI_API_KEY")
    root = _templates_dir()
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return web.Response(status=503, text=f"templates dir unusable: {e}")
    return web.Response(status=200, text="ok")


def build_app() -> web.Application:
    app = web.Application(client_max_size=1024 * 1024)
    app.router.add_post("/generate", _post_generate)
    app.router.add_get("/templates", _get_templates)
    app.router.add_get("/templates/{template_id}", _get_template_by_id)
    app.router.add_get("/healthz", _get_healthz)
    return app


def main() -> None:
    load_dotenv()
    port = int(os.environ.get("TEMPLATE_GEN_PORT", "8768"))
    logger.info(
        "template-generator starting on :{} (impl_model={}, critique_model={}, "
        "templates_dir={})",
        port,
        DEFAULT_IMPL_MODEL,
        DEFAULT_CRITIQUE_MODEL,
        _templates_dir(),
    )
    web.run_app(build_app(), host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
