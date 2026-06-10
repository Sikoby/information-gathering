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
import os
import re
import secrets
from datetime import datetime, timezone
from typing import TypeVar

from aiohttp import web
from loguru import logger
from pydantic import BaseModel, ValidationError

from ..templates import TEMPLATES
from ..templates.schema import Template
from . import auth, clients, generation, ics, invites, registry
from .models import (
    BatchScheduleFromTemplate,
    BatchStartFromTemplate,
    MeetingRecord,
    MeetingScheduleFromTemplate,
    MeetingStartFromTemplate,
    TemplateCreate,
    TemplatePatch,
    TemplateRecord,
    TemplateRegenerate,
)


def _meeting_public_url() -> str:
    return os.environ.get("MEETING_PUBLIC_URL", "http://localhost:8765").rstrip("/")


def _parse_iso(value: str) -> datetime:
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _ics_filename(summary: str) -> str:
    """Slugify the title into a safe ASCII .ics filename (no quotes/CRLF)."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", summary).strip("-").lower()
    return slug or "meeting-invite"


def _meeting_summary(rec: MeetingRecord, tmpl: TemplateRecord | None) -> str:
    """The human title for the calendar event / email subject.

    A meeting's own `title_override` wins; otherwise the template title; a
    constant last-resort so the `.ics` SUMMARY is never empty. Shared by the
    `.ics` download endpoint and the invite email so the two never drift.
    """
    return rec.title_override or (tmpl.title if tmpl else None) or "Meeting"


def _join_url(meeting_id: str) -> str:
    """The stable, permanent join link mailed in the invite."""
    return f"{_meeting_public_url()}/join/{meeting_id}"


def _new_join_pin() -> str:
    """A 6-digit PIN shown in the invite and required on the join page."""
    return f"{secrets.randbelow(10**6):06d}"


async def _send_invites(rec: MeetingRecord, summary: str) -> None:
    """Best-effort invite email; stamp `invite_sent_at` on a successful send.

    A send failure — or unconfigured SMTP — never fails meeting creation: it is
    logged inside `invites.send_invites` and the record keeps `invite_sent_at`
    unset. Mutates `rec` so the JSON response reflects the stamp.
    """
    if not rec.invitees:
        return
    if await invites.send_invites(rec, summary=summary):
        sent_at = registry.now_iso()
        await registry.update(rec.meeting_id, invite_sent_at=sent_at)
        rec.invite_sent_at = sent_at

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
        live_view_url=result.get("live_view_url"),
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


async def post_template_schedule_meeting(request: web.Request) -> web.Response:
    """Schedule a future meeting from a template.

    Unlike start-now, this does NOT dispatch. The reconcile loop dispatches
    it when `scheduled_at` arrives. The record is given a deterministic
    `live_view_url` immediately so the invite has a stable link before dispatch
    mints the real voice-join URL.
    """
    template_id = request.match_info["template_id"]
    email = request["user_email"]
    payload = await _parse_body(request, MeetingScheduleFromTemplate)
    if isinstance(payload, web.Response):
        return payload

    tmpl = await _load_owned_template(request)
    if isinstance(tmpl, web.Response):
        return tmpl
    if tmpl.template_status != "ready" or tmpl.template is None:
        return web.json_response(
            {"error": f"template is not ready (status={tmpl.template_status})"},
            status=424,
        )

    # scheduled_at is format-normalized to a UTC instant by the model; the
    # future check is time-relative so it lives here.
    if _parse_iso(payload.scheduled_at) <= datetime.now(timezone.utc):
        return web.json_response(
            {"error": "scheduled_at must be in the future"}, status=400
        )

    meeting_id = registry.new_meeting_id()
    target_minutes = payload.target_minutes or tmpl.default_target_minutes
    now = registry.now_iso()
    rec = MeetingRecord(
        meeting_id=meeting_id,
        owner_email=email,
        template_id=template_id,
        title_override=payload.title_override,
        target_minutes=target_minutes,
        status="scheduled",
        scheduled_at=payload.scheduled_at,
        invitees=payload.invitees,
        join_pin=_new_join_pin() if payload.invitees else None,
        live_view_url=f"{_meeting_public_url()}/{meeting_id}/",
        created_at=now,
        updated_at=now,
    )
    await registry.create(rec)
    await _send_invites(rec, _meeting_summary(rec, tmpl))
    logger.info(
        "scheduled meeting_id={} owner={} template_id={} at={} invitees={}",
        meeting_id,
        email,
        template_id,
        payload.scheduled_at,
        len(payload.invitees),
    )
    return web.json_response(rec.model_dump(mode="json"), status=201)


def _batch_title(prefix: str | None, name: str | None) -> str | None:
    """Per-meeting title from the batch prefix + interviewee name.

    Both present → "<prefix><name>" (the prefix carries its own separator);
    otherwise whichever is set, or `None` (then the meeting falls back to the
    template title downstream).
    """
    if prefix and name:
        return f"{prefix}{name}"
    return prefix or name


async def post_template_start_batch(request: web.Request) -> web.Response:
    """Start N meetings from one template — one per interviewee, in parallel.

    Best-effort: each interviewee is dispatched independently; a failure is
    collected in `errors[]` and the rest continue. Always returns 201 (even if
    every dispatch failed — the caller compares `meetings` against `errors`).
    """
    template_id = request.match_info["template_id"]
    email = request["user_email"]
    payload = await _parse_body(request, BatchStartFromTemplate)
    if isinstance(payload, web.Response):
        return payload

    tmpl = await _load_owned_template(request)
    if isinstance(tmpl, web.Response):
        return tmpl
    if tmpl.template_status != "ready" or tmpl.template is None:
        return web.json_response(
            {"error": f"template is not ready (status={tmpl.template_status})"},
            status=424,
        )

    target_minutes = payload.target_minutes or tmpl.default_target_minutes
    meetings: list[dict] = []
    errors: list[dict] = []
    for person in payload.interviewees:
        title = _batch_title(payload.title_prefix, person.name)
        effective_title = title or tmpl.title
        briefing = f"# {effective_title}\n\n{tmpl.source_prompt}"
        meeting_id = registry.new_meeting_id()
        try:
            result = await clients.dispatch_meeting(
                request.app["http_session"],
                run_id=meeting_id,
                briefing_description=briefing,
                custom_template=tmpl.template,
                target_minutes=target_minutes,
            )
        except Exception as e:  # noqa: BLE001 - collect + continue (best-effort)
            logger.exception(
                "batch dispatch failed template_id={} email={}",
                template_id,
                person.email,
            )
            errors.append(
                {"name": person.name, "email": person.email, "error": str(e)}
            )
            continue

        now = registry.now_iso()
        rec = MeetingRecord(
            meeting_id=meeting_id,
            owner_email=email,
            template_id=template_id,
            title_override=title,
            target_minutes=target_minutes,
            status="running",
            invitees=[person.email],
            run_id=result["run_id"],
            room=result.get("room"),
            join_url=result.get("join_url"),
            live_view_url=result.get("live_view_url"),
            created_at=now,
            updated_at=now,
            dispatched_at=now,
        )
        await registry.create(rec)
        meetings.append(rec.model_dump(mode="json"))

    logger.info(
        "batch-started template_id={} owner={} ok={} failed={}",
        template_id,
        email,
        len(meetings),
        len(errors),
    )
    return web.json_response({"meetings": meetings, "errors": errors}, status=201)


async def post_template_schedule_batch(request: web.Request) -> web.Response:
    """Schedule N future meetings from one template — one per interviewee.

    Like single-schedule: no dispatch (the reconcile loop starts each when
    `scheduled_at` arrives), a deterministic `live_view_url` so the invite has a
    stable link, and a per-meeting `.ics` whose SUMMARY is the interviewee name
    and whose single ATTENDEE is their email.
    """
    template_id = request.match_info["template_id"]
    email = request["user_email"]
    payload = await _parse_body(request, BatchScheduleFromTemplate)
    if isinstance(payload, web.Response):
        return payload

    tmpl = await _load_owned_template(request)
    if isinstance(tmpl, web.Response):
        return tmpl
    if tmpl.template_status != "ready" or tmpl.template is None:
        return web.json_response(
            {"error": f"template is not ready (status={tmpl.template_status})"},
            status=424,
        )

    if _parse_iso(payload.scheduled_at) <= datetime.now(timezone.utc):
        return web.json_response(
            {"error": "scheduled_at must be in the future"}, status=400
        )

    target_minutes = payload.target_minutes or tmpl.default_target_minutes
    meetings: list[dict] = []
    for person in payload.interviewees:
        title = _batch_title(payload.title_prefix, person.name)
        meeting_id = registry.new_meeting_id()
        now = registry.now_iso()
        rec = MeetingRecord(
            meeting_id=meeting_id,
            owner_email=email,
            template_id=template_id,
            title_override=title,
            target_minutes=target_minutes,
            status="scheduled",
            scheduled_at=payload.scheduled_at,
            invitees=[person.email],
            join_pin=_new_join_pin(),
            live_view_url=f"{_meeting_public_url()}/{meeting_id}/",
            created_at=now,
            updated_at=now,
        )
        await registry.create(rec)
        await _send_invites(rec, _meeting_summary(rec, tmpl))
        meetings.append(rec.model_dump(mode="json"))

    logger.info(
        "batch-scheduled template_id={} owner={} count={} at={}",
        template_id,
        email,
        len(meetings),
        payload.scheduled_at,
    )
    return web.json_response({"meetings": meetings}, status=201)


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


async def get_meeting_invite_ics(request: web.Request) -> web.Response:
    """Download an `.ics` calendar invite for a scheduled meeting.

    Owner-scoped (404 on mismatch, so other users' meetings stay invisible).
    Only a scheduled meeting carries a start time, so a meeting without
    `scheduled_at` returns 409. This is the download endpoint; the future
    email step (see invites.py) attaches the same payload.
    """
    rec = await _load_owned_meeting(request)
    if isinstance(rec, web.Response):
        return rec
    if not rec.scheduled_at:
        return web.json_response(
            {"error": "meeting has no scheduled time"}, status=409
        )

    tmpl = await registry.get_template(rec.template_id)
    summary = _meeting_summary(rec, tmpl)
    body = ics.build_event(
        rec,
        summary=summary,
        organizer_email=rec.owner_email,
        join_url=_join_url(rec.meeting_id),
        pin=rec.join_pin,
    )
    return web.Response(
        text=body,
        content_type="text/calendar",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{_ics_filename(summary)}.ics"'
            )
        },
    )


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
