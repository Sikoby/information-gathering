"""HTTP handlers for the meeting console API (`/api/*` + `/healthz`)."""

from __future__ import annotations

import json

from aiohttp import web
from loguru import logger
from pydantic import ValidationError

from ..templates import TEMPLATES
from ..templates.schema import Template
from . import clients, generation, registry
from .models import (
    MeetingCreate,
    MeetingPatch,
    MeetingRecord,
    MeetingRegenerate,
    MeetingStart,
)


def _record_json(rec: MeetingRecord) -> dict:
    return json.loads(rec.model_dump_json())


def _validation_error(e: ValidationError) -> web.Response:
    return web.json_response(
        {"error": "invalid request", "details": json.loads(e.json())},
        status=400,
    )


async def _required_body(request: web.Request) -> dict:
    raw = await request.read()
    return json.loads(raw)  # raises JSONDecodeError on bad/empty body


async def _optional_body(request: web.Request) -> dict:
    raw = await request.read()
    return json.loads(raw) if raw.strip() else {}


async def post_meetings(request: web.Request) -> web.Response:
    try:
        body = await _required_body(request)
    except json.JSONDecodeError:
        return web.json_response({"error": "invalid JSON body"}, status=400)
    try:
        payload = MeetingCreate.model_validate(body)
    except ValidationError as e:
        return _validation_error(e)

    if payload.reference_template and payload.reference_template not in TEMPLATES:
        return web.json_response(
            {"error": f"unknown reference_template; known: {sorted(TEMPLATES)}"},
            status=400,
        )

    meeting_id = registry.new_meeting_id()
    now = registry.now_iso()
    rec = MeetingRecord(
        meeting_id=meeting_id,
        title=payload.title,
        prompt=payload.prompt,
        reference_template=payload.reference_template,
        target_minutes=payload.target_minutes,
        status="planned",
        template_status="generating",
        run_id=meeting_id,
        created_at=now,
        updated_at=now,
    )
    await registry.create(rec)
    generation.spawn(request.app["http_session"], meeting_id, rec.generation_seq)
    logger.info("created meeting_id={}", meeting_id)
    return web.json_response(_record_json(rec), status=201)


async def get_meetings(_request: web.Request) -> web.Response:
    recs = await registry.list_all()
    return web.json_response({"meetings": [_record_json(r) for r in recs]})


async def get_meeting(request: web.Request) -> web.Response:
    rec = await registry.get(request.match_info["meeting_id"])
    if rec is None:
        return web.json_response({"error": "not found"}, status=404)
    return web.json_response(_record_json(rec))


async def patch_meeting(request: web.Request) -> web.Response:
    meeting_id = request.match_info["meeting_id"]
    try:
        body = await _required_body(request)
    except json.JSONDecodeError:
        return web.json_response({"error": "invalid JSON body"}, status=400)
    try:
        patch = MeetingPatch.model_validate(body)
    except ValidationError as e:
        return _validation_error(e)

    rec = await registry.get(meeting_id)
    if rec is None:
        return web.json_response({"error": "not found"}, status=404)
    if rec.status != "planned":
        return web.json_response(
            {"error": f"cannot edit a {rec.status} meeting"}, status=409
        )

    fields: dict = {}
    if patch.title is not None:
        fields["title"] = patch.title
    if patch.prompt is not None:
        fields["prompt"] = patch.prompt
    if patch.target_minutes is not None:
        fields["target_minutes"] = patch.target_minutes
    if patch.template is not None:
        try:
            validated = Template.model_validate(patch.template)
        except ValidationError as e:
            return web.json_response(
                {"error": "invalid template", "details": json.loads(e.json())},
                status=400,
            )
        # Store the re-serialized template (with the auto-appended "other").
        fields["template"] = json.loads(validated.model_dump_json())

    if fields:
        await registry.update(meeting_id, **fields)
    updated = await registry.get(meeting_id)
    if updated is None:
        return web.json_response({"error": "not found"}, status=404)
    return web.json_response(_record_json(updated))


async def post_start(request: web.Request) -> web.Response:
    meeting_id = request.match_info["meeting_id"]
    try:
        body = await _optional_body(request)
    except json.JSONDecodeError:
        return web.json_response({"error": "invalid JSON body"}, status=400)
    try:
        opts = MeetingStart.model_validate(body)
    except ValidationError as e:
        return _validation_error(e)

    rec = await registry.get(meeting_id)
    if rec is None:
        return web.json_response({"error": "not found"}, status=404)
    if rec.status != "planned":
        return web.json_response(
            {"error": f"meeting is already {rec.status}"}, status=409
        )
    if rec.template_status != "ready" or rec.template is None:
        return web.json_response(
            {"error": f"template is not ready (status={rec.template_status})"},
            status=424,
        )

    target_minutes = opts.target_minutes or rec.target_minutes
    briefing = f"# {rec.title}\n\n{rec.prompt}"
    try:
        result = await clients.dispatch_meeting(
            request.app["http_session"],
            run_id=rec.run_id or meeting_id,
            briefing_description=briefing,
            custom_template=rec.template,
            target_minutes=target_minutes,
        )
    except Exception as e:  # noqa: BLE001 - surface any dispatch failure as 502
        logger.exception("dispatch failed meeting_id={}", meeting_id)
        return web.json_response({"error": str(e)}, status=502)

    await registry.update(
        meeting_id,
        status="running",
        target_minutes=target_minutes,
        run_id=result["run_id"],
        room=result.get("room"),
        join_url=result.get("join_url"),
        webapp_url=result.get("webapp_url"),
        dispatched_at=registry.now_iso(),
    )
    updated = await registry.get(meeting_id)
    logger.info("started meeting_id={} run_id={}", meeting_id, result["run_id"])
    return web.json_response(_record_json(updated) if updated else {})


async def post_regenerate(request: web.Request) -> web.Response:
    meeting_id = request.match_info["meeting_id"]
    try:
        body = await _optional_body(request)
    except json.JSONDecodeError:
        return web.json_response({"error": "invalid JSON body"}, status=400)
    try:
        opts = MeetingRegenerate.model_validate(body)
    except ValidationError as e:
        return _validation_error(e)

    if opts.reference_template and opts.reference_template not in TEMPLATES:
        return web.json_response(
            {"error": f"unknown reference_template; known: {sorted(TEMPLATES)}"},
            status=400,
        )

    rec = await registry.get(meeting_id)
    if rec is None:
        return web.json_response({"error": "not found"}, status=404)
    if rec.status != "planned":
        return web.json_response(
            {"error": f"cannot regenerate a {rec.status} meeting"}, status=409
        )

    new_seq = rec.generation_seq + 1
    fields: dict = {
        "generation_seq": new_seq,
        "template_status": "generating",
        "template_error": None,
    }
    if opts.prompt is not None:
        fields["prompt"] = opts.prompt
    if opts.reference_template is not None:
        fields["reference_template"] = opts.reference_template
    await registry.update(meeting_id, **fields)
    generation.spawn(request.app["http_session"], meeting_id, new_seq)
    updated = await registry.get(meeting_id)
    logger.info("regenerate meeting_id={} seq={}", meeting_id, new_seq)
    return web.json_response(_record_json(updated) if updated else {}, status=202)


async def delete_meeting(request: web.Request) -> web.Response:
    meeting_id = request.match_info["meeting_id"]
    rec = await registry.get(meeting_id)
    if rec is None:
        return web.json_response({"error": "not found"}, status=404)
    if rec.status == "running":
        return web.json_response(
            {"error": "cannot delete a running meeting"}, status=409
        )
    await registry.delete(meeting_id)
    return web.Response(status=204)


async def get_reference_templates(_request: web.Request) -> web.Response:
    return web.json_response(
        {
            "templates": [
                {"name": name, "description": tmpl.description}
                for name, tmpl in TEMPLATES.items()
            ]
        }
    )


async def get_healthz(_request: web.Request) -> web.Response:
    try:
        await registry.get_client().ping()
    except Exception as e:  # noqa: BLE001
        return web.Response(status=503, text=f"redis unreachable: {e}")
    return web.Response(status=200, text="ok")
