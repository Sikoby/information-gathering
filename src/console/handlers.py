"""HTTP handlers for the meeting console API (`/api/*` + `/healthz`).

The console serves two resource types:

  - **Templates** (`/api/templates`) are the reusable thing. A user creates
    one from a prompt (and optionally an uploaded .pptx/.pdf), edits it, and
    can launch one meeting after another from it.
  - **Meetings** (`/api/meetings`) are instances that reference a template,
    own the LiveKit run state, and live forever as an audit log of past
    meetings. A meeting is born `running` — there is no planned state on
    the meeting side.
"""

from __future__ import annotations

import json
from typing import TypeVar

from aiohttp import web
from loguru import logger
from pydantic import BaseModel, ValidationError

from ..templates import TEMPLATES
from ..templates.schema import Template
from . import auth, clients, generation, registry
from .models import (
    MeetingRecord,
    MeetingStartFromTemplate,
    TemplateCreate,
    TemplatePatch,
    TemplateRecord,
    TemplateRegenerate,
)


_START_LOCK_PREFIX = "console:start:lock:"
_START_LOCK_TTL_SECONDS = 5

_T = TypeVar("_T", bound=BaseModel)


def _validation_error(e: ValidationError) -> web.Response:
    return web.json_response(
        {"error": "invalid request", "details": json.loads(e.json())},
        status=400,
    )


async def _parse_body(
    request: web.Request, model: type[_T], *, optional: bool = False
) -> _T | web.Response:
    raw = await request.read()
    if optional and not raw.strip():
        body: dict = {}
    else:
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            return web.json_response({"error": "invalid JSON body"}, status=400)
    try:
        return model.model_validate(body)
    except ValidationError as e:
        return _validation_error(e)


def _check_reference_template(name: str | None) -> web.Response | None:
    if name and name not in TEMPLATES:
        return web.json_response(
            {"error": f"unknown reference_template; known: {sorted(TEMPLATES)}"},
            status=400,
        )
    return None


# ============================================================== templates


async def post_templates(request: web.Request) -> web.Response:
    payload = await _parse_body(request, TemplateCreate)
    if isinstance(payload, web.Response):
        return payload
    if (err := _check_reference_template(payload.reference_template)) is not None:
        return err

    template_id = registry.new_template_id()
    now = registry.now_iso()
    rec = TemplateRecord(
        template_id=template_id,
        owner_email=request["user_email"],
        title=payload.title,
        source_prompt=payload.source_prompt,
        reference_template=payload.reference_template,
        default_target_minutes=payload.default_target_minutes,
        template_status="generating",
        created_at=now,
        updated_at=now,
    )
    await registry.create_template(rec)
    generation.spawn(request.app["http_session"], template_id, rec.generation_seq)
    logger.info(
        "created template_id={} owner={}", template_id, rec.owner_email
    )
    return web.json_response(rec.model_dump(mode="json"), status=201)


async def post_templates_upload(request: web.Request) -> web.Response:
    """Multipart create: file + form fields. Extracts the document, then
    creates a template record with `document_outline` attached and spawns
    generation in presentation mode."""
    if not request.content_type.startswith("multipart/"):
        return web.json_response(
            {"error": "expected multipart/form-data"}, status=415
        )

    reader = await request.multipart()
    fields: dict[str, str] = {}
    file_bytes: bytes | None = None
    file_name: str | None = None
    file_content_type: str | None = None

    while True:
        part = await reader.next()
        if part is None:
            break
        if part.name == "file":
            file_name = part.filename or "upload"
            file_content_type = part.headers.get("Content-Type")
            file_bytes = await part.read(decode=False)
        elif part.name in {
            "title",
            "source_prompt",
            "reference_template",
            "default_target_minutes",
        }:
            fields[part.name] = (await part.read(decode=True)).decode("utf-8")

    if file_bytes is None or file_name is None:
        return web.json_response({"error": "missing 'file' part"}, status=400)
    kind = _detect_kind(file_name, file_content_type)
    if kind is None:
        return web.json_response(
            {"error": f"unsupported file type: {file_name!r} (need .pptx or .pdf)"},
            status=415,
        )

    create_body: dict = {
        "title": fields.get("title", "").strip(),
        "source_prompt": fields.get("source_prompt", "").strip(),
    }
    if fields.get("reference_template"):
        create_body["reference_template"] = fields["reference_template"]
    if fields.get("default_target_minutes"):
        try:
            create_body["default_target_minutes"] = int(
                fields["default_target_minutes"]
            )
        except ValueError:
            return web.json_response(
                {"error": "default_target_minutes must be an integer"}, status=400
            )

    try:
        payload = TemplateCreate.model_validate(create_body)
    except ValidationError as e:
        return _validation_error(e)
    if (err := _check_reference_template(payload.reference_template)) is not None:
        return err

    try:
        outline = await clients.extract_document(
            request.app["http_session"],
            filename=file_name,
            content_type=file_content_type or "",
            data=file_bytes,
        )
    except Exception as e:  # noqa: BLE001 - surface as 502
        logger.exception("extract failed filename={}", file_name)
        return web.json_response(
            {"error": f"failed to extract document: {e}"}, status=502
        )

    template_id = registry.new_template_id()
    now = registry.now_iso()
    rec = TemplateRecord(
        template_id=template_id,
        owner_email=request["user_email"],
        title=payload.title,
        source_prompt=payload.source_prompt,
        reference_template=payload.reference_template,
        default_target_minutes=payload.default_target_minutes,
        template_status="generating",
        created_at=now,
        updated_at=now,
        document_filename=file_name,
        document_kind=kind,
        document_outline=outline,
    )
    await registry.create_template(rec)
    generation.spawn(request.app["http_session"], template_id, rec.generation_seq)
    logger.info(
        "created template_id={} owner={} from document={} ({} slides)",
        template_id,
        rec.owner_email,
        file_name,
        len(outline.get("slides", [])),
    )
    return web.json_response(rec.model_dump(mode="json"), status=201)


def _detect_kind(filename: str, content_type: str | None) -> str | None:
    name = filename.lower()
    if name.endswith(".pptx") or content_type == (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ):
        return "pptx"
    if name.endswith(".pdf") or content_type == "application/pdf":
        return "pdf"
    return None


async def _load_owned_template(
    request: web.Request,
) -> TemplateRecord | web.Response:
    """Load the template named in the URL; return 404 on miss or owner mismatch.

    404 (not 403) on mismatch so we don't leak the existence of other users'
    templates.
    """
    rec = await registry.get_template(request.match_info["template_id"])
    if rec is None or rec.owner_email != request["user_email"]:
        return web.json_response({"error": "not found"}, status=404)
    return rec


async def _load_owned_meeting(
    request: web.Request,
) -> MeetingRecord | web.Response:
    rec = await registry.get(request.match_info["meeting_id"])
    if rec is None or rec.owner_email != request["user_email"]:
        return web.json_response({"error": "not found"}, status=404)
    return rec


async def get_templates(request: web.Request) -> web.Response:
    recs = await registry.list_templates_by_owner(request["user_email"])
    return web.json_response(
        {"templates": [r.model_dump(mode="json") for r in recs]}
    )


async def get_template(request: web.Request) -> web.Response:
    rec = await _load_owned_template(request)
    if isinstance(rec, web.Response):
        return rec
    return web.json_response(rec.model_dump(mode="json"))


async def patch_template(request: web.Request) -> web.Response:
    template_id = request.match_info["template_id"]
    patch = await _parse_body(request, TemplatePatch)
    if isinstance(patch, web.Response):
        return patch

    rec = await _load_owned_template(request)
    if isinstance(rec, web.Response):
        return rec

    fields = patch.model_dump(exclude_unset=True, exclude_none=True)
    if "template" in fields:
        try:
            validated = Template.model_validate(fields["template"])
        except ValidationError as e:
            return web.json_response(
                {"error": "invalid template", "details": json.loads(e.json())},
                status=400,
            )
        # Store the re-serialized template (with the auto-appended "other").
        fields["template"] = validated.model_dump(mode="json")

    if fields:
        await registry.update_template(template_id, **fields)
    updated = await registry.get_template(template_id)
    if updated is None:
        return web.json_response({"error": "not found"}, status=404)
    return web.json_response(updated.model_dump(mode="json"))


async def post_template_regenerate(request: web.Request) -> web.Response:
    template_id = request.match_info["template_id"]
    opts = await _parse_body(request, TemplateRegenerate, optional=True)
    if isinstance(opts, web.Response):
        return opts
    if (err := _check_reference_template(opts.reference_template)) is not None:
        return err

    rec = await _load_owned_template(request)
    if isinstance(rec, web.Response):
        return rec

    new_seq = rec.generation_seq + 1
    fields: dict = {
        "generation_seq": new_seq,
        "template_status": "generating",
        "template_error": None,
        **opts.model_dump(exclude_unset=True, exclude_none=True),
    }
    await registry.update_template(template_id, **fields)
    generation.spawn(request.app["http_session"], template_id, new_seq)
    updated = await registry.get_template(template_id)
    logger.info("regenerate template_id={} seq={}", template_id, new_seq)
    return web.json_response(
        updated.model_dump(mode="json") if updated else {}, status=202
    )


async def delete_template(request: web.Request) -> web.Response:
    template_id = request.match_info["template_id"]
    rec = await _load_owned_template(request)
    if isinstance(rec, web.Response):
        return rec

    meetings = await registry.list_meetings_by_owner(request["user_email"])
    referencing = [m for m in meetings if m.template_id == template_id]
    if referencing:
        running_count = sum(1 for m in referencing if m.status == "running")
        return web.json_response(
            {
                "error": "template is referenced by meetings",
                "total_count": len(referencing),
                "running_count": running_count,
            },
            status=409,
        )

    await registry.delete_template(template_id)
    return web.Response(status=204)


async def post_template_start_meeting(request: web.Request) -> web.Response:
    template_id = request.match_info["template_id"]
    email = request["user_email"]
    opts = await _parse_body(request, MeetingStartFromTemplate, optional=True)
    if isinstance(opts, web.Response):
        return opts

    tmpl = await _load_owned_template(request)
    if isinstance(tmpl, web.Response):
        return tmpl
    if tmpl.template_status != "ready" or tmpl.template is None:
        return web.json_response(
            {"error": f"template is not ready (status={tmpl.template_status})"},
            status=424,
        )

    # Narrow the read-modify-write race across replicas — scoped to this
    # user, since the one-at-a-time guard is per-user. The list check below
    # is the real guard; this just shrinks the window.
    if not await registry.try_acquire_leader(
        f"{_START_LOCK_PREFIX}{email}", _START_LOCK_TTL_SECONDS
    ):
        return web.json_response(
            {"error": "another start is in progress"}, status=409
        )

    running = [
        m
        for m in await registry.list_meetings_by_owner(email)
        if m.status == "running"
    ]
    if running:
        return web.json_response(
            {
                "error": "another meeting is running",
                "running_meeting_id": running[0].meeting_id,
            },
            status=409,
        )

    meeting_id = registry.new_meeting_id()
    target_minutes = opts.target_minutes or tmpl.default_target_minutes
    effective_title = opts.title_override or tmpl.title
    briefing = f"# {effective_title}\n\n{tmpl.source_prompt}"

    try:
        result = await clients.dispatch_meeting(
            request.app["http_session"],
            run_id=meeting_id,
            briefing_description=briefing,
            custom_template=tmpl.template,
            target_minutes=target_minutes,
        )
    except Exception as e:  # noqa: BLE001 - surface any dispatch failure as 502
        logger.exception("dispatch failed template_id={}", template_id)
        return web.json_response({"error": str(e)}, status=502)

    now = registry.now_iso()
    rec = MeetingRecord(
        meeting_id=meeting_id,
        owner_email=email,
        template_id=template_id,
        title_override=opts.title_override,
        target_minutes=target_minutes,
        status="running",
        run_id=result["run_id"],
        room=result.get("room"),
        join_url=result.get("join_url"),
        webapp_url=result.get("webapp_url"),
        created_at=now,
        updated_at=now,
        dispatched_at=now,
    )
    await registry.create(rec)
    logger.info(
        "started meeting_id={} owner={} from template_id={} run_id={}",
        meeting_id,
        email,
        template_id,
        result["run_id"],
    )
    return web.json_response(rec.model_dump(mode="json"), status=201)


# =============================================================== meetings


async def get_meetings(request: web.Request) -> web.Response:
    recs = await registry.list_meetings_by_owner(request["user_email"])
    return web.json_response(
        {"meetings": [r.model_dump(mode="json") for r in recs]}
    )


async def get_meeting(request: web.Request) -> web.Response:
    rec = await _load_owned_meeting(request)
    if isinstance(rec, web.Response):
        return rec
    return web.json_response(rec.model_dump(mode="json"))


async def delete_meeting(request: web.Request) -> web.Response:
    rec = await _load_owned_meeting(request)
    if isinstance(rec, web.Response):
        return rec
    if rec.status == "running":
        return web.json_response(
            {"error": "cannot delete a running meeting"}, status=409
        )
    await registry.delete(rec.meeting_id)
    return web.Response(status=204)


# ================================================================ helpers


async def get_reference_templates(_request: web.Request) -> web.Response:
    return web.json_response(
        {
            "templates": [
                {"name": name, "description": tmpl.description}
                for name, tmpl in TEMPLATES.items()
            ]
        }
    )


async def get_me(request: web.Request) -> web.Response:
    """Identity probe for the SPA — echoes the authenticated email back so
    the frontend can render `signed in as <email>` and detect 401, plus the
    Cloudflare Access logout URL (team-domain; null in local dev)."""
    return web.json_response(
        {
            "email": request["user_email"],
            "logout_url": auth.resolve_logout_url(),
        }
    )


async def get_healthz(_request: web.Request) -> web.Response:
    try:
        await registry.get_client().ping()
    except Exception as e:  # noqa: BLE001
        return web.Response(status=503, text=f"redis unreachable: {e}")
    return web.Response(status=200, text="ok")
