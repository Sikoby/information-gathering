"""Pydantic models for the meeting console registry and HTTP API.

Two record types live in Redis:

  - `TemplateRecord` at `template:<template_id>` is the reusable thing the
    user creates from a prompt (and optionally a .pptx/.pdf upload). It
    carries the generated `Template` body plus the generation metadata.
  - `MeetingRecord` at `meeting:<meeting_id>` is a thin instance pointing at
    a template; it owns the LiveKit run state and the lifecycle. A meeting
    is born `running` — there is no `planned` state on the meeting side
    (the equivalent lives on the template as `template_status`).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator


MeetingStatus = Literal["scheduled", "running", "done"]
TemplateStatus = Literal["generating", "ready", "failed"]

_PROMPT_MAX = 16_000
_TITLE_MAX = 200


class TemplateRecord(BaseModel):
    """The reusable template stored (as JSON) at `template:<template_id>`.

    `template` and `document_outline` are stored as embedded JSON *strings*
    so the atomic Lua merge never round-trips their nested arrays through
    cjson (which would corrupt empty arrays into `{}`).
    """

    template_id: str
    owner_email: str
    title: str
    source_prompt: str
    reference_template: str | None = None
    default_target_minutes: int = 30

    template_status: TemplateStatus = "generating"
    template: dict | None = None
    template_error: str | None = None
    template_approved: bool | None = None
    template_iterations_used: int | None = None
    generation_seq: int = 0

    document_filename: str | None = None
    document_kind: Literal["pptx", "pdf"] | None = None
    document_outline: dict | None = None

    created_at: str
    updated_at: str


class MeetingRecord(BaseModel):
    """A meeting instance stored (as JSON) at `meeting:<meeting_id>`.

    A meeting is born `running` (start-now) or `scheduled` (a future start);
    a scheduled meeting carries `scheduled_at` + `invitees` and is dispatched
    later by the reconcile loop when its start time arrives.

    `invitees` is stored as an embedded JSON *string* (see registry) so the
    atomic Lua merge never round-trips the list through cjson — which would
    collapse an empty list to `{}` and corrupt the record.
    """

    meeting_id: str
    owner_email: str
    template_id: str
    title_override: str | None = None
    target_minutes: int = 30

    status: MeetingStatus = "running"

    scheduled_at: str | None = None
    invitees: list[str] = Field(default_factory=list)
    invite_sent_at: str | None = None
    join_pin: str | None = None

    run_id: str | None = None
    room: str | None = None
    join_url: str | None = None
    live_view_url: str | None = None

    created_at: str
    updated_at: str
    dispatched_at: str | None = None
    ended_at: str | None = None
    end_reason: str | None = None


class TemplateCreate(BaseModel):
    """`POST /api/templates` body."""

    title: str = Field(min_length=1, max_length=_TITLE_MAX)
    source_prompt: str = Field(min_length=1, max_length=_PROMPT_MAX)
    reference_template: str | None = None
    default_target_minutes: int = Field(default=30, ge=1, le=120)


class TemplatePatch(BaseModel):
    """`PATCH /api/templates/{id}` body — all fields optional."""

    title: str | None = Field(default=None, min_length=1, max_length=_TITLE_MAX)
    source_prompt: str | None = Field(default=None, min_length=1, max_length=_PROMPT_MAX)
    template: dict | None = None
    default_target_minutes: int | None = Field(default=None, ge=1, le=120)


class TemplateRegenerate(BaseModel):
    """`POST /api/templates/{id}/regenerate` body — optional."""

    source_prompt: str | None = Field(default=None, min_length=1, max_length=_PROMPT_MAX)
    reference_template: str | None = None


class MeetingStartFromTemplate(BaseModel):
    """`POST /api/templates/{id}/meetings` body — optional."""

    title_override: str | None = Field(default=None, min_length=1, max_length=_TITLE_MAX)
    target_minutes: int | None = Field(default=None, ge=1, le=120)


_INVITEES_MAX = 100


def _clean_email(raw: str) -> str:
    """Strip + lowercase + validate `local@domain`. Raises ValueError if bad."""
    email = raw.strip().lower()
    local, _, domain = email.partition("@")
    if not local or "." not in domain:
        raise ValueError(f"invalid email: {raw!r}")
    return email


def _normalize_scheduled_at(v: str) -> str:
    """Parse an ISO 8601 datetime → a UTC ISO instant. Raises if unparseable.

    Time-relative checks (is it in the future?) belong in the handler, against
    its own clock — not here.
    """
    s = v.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError as e:
        raise ValueError("scheduled_at must be an ISO 8601 datetime") from e
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


class MeetingScheduleFromTemplate(BaseModel):
    """`POST /api/templates/{id}/scheduled-meetings` body.

    `scheduled_at` is required and normalized to a UTC ISO instant; the
    handler enforces that it is in the future (time-relative, so it does not
    belong in the schema). `invitees` are cleaned, lowercased, and deduped.
    """

    scheduled_at: str
    title_override: str | None = Field(default=None, min_length=1, max_length=_TITLE_MAX)
    target_minutes: int | None = Field(default=None, ge=1, le=120)
    invitees: list[str] = Field(default_factory=list)

    @field_validator("scheduled_at")
    @classmethod
    def _validate_scheduled_at(cls, v: str) -> str:
        return _normalize_scheduled_at(v)

    @field_validator("invitees")
    @classmethod
    def _clean_invitees(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for raw in v:
            if not raw.strip():
                continue
            email = _clean_email(raw)
            if email not in seen:
                seen.add(email)
                out.append(email)
        if len(out) > _INVITEES_MAX:
            raise ValueError(f"too many invitees (max {_INVITEES_MAX})")
        return out


class BatchInterviewee(BaseModel):
    """One person in a batch run: an optional display name plus their email.

    The name (if present) becomes the meeting's `title_override`; the email
    becomes the meeting's single invitee.
    """

    name: str | None = Field(default=None, max_length=_TITLE_MAX)
    email: str

    @field_validator("name")
    @classmethod
    def _blank_name_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        return _clean_email(v)


class BatchStartFromTemplate(BaseModel):
    """`POST /api/templates/{id}/batch-meetings` body.

    One template, N interviewees — each becomes its own meeting (own room,
    own run_id), all started now and running in parallel. At least one
    interviewee is required; there is no upper cap and duplicates are allowed.
    """

    target_minutes: int | None = Field(default=None, ge=1, le=120)
    title_prefix: str | None = Field(default=None, min_length=1, max_length=_TITLE_MAX)
    interviewees: list[BatchInterviewee]

    @field_validator("interviewees")
    @classmethod
    def _require_one(cls, v: list[BatchInterviewee]) -> list[BatchInterviewee]:
        if not v:
            raise ValueError("at least one interviewee is required")
        return v


class BatchScheduleFromTemplate(BatchStartFromTemplate):
    """`POST /api/templates/{id}/scheduled-batch-meetings` body.

    The start-now batch plus a `scheduled_at` (normalized to a UTC ISO
    instant; the handler enforces it is in the future). Each interviewee
    becomes its own scheduled meeting dispatched by the reconcile loop.
    """

    scheduled_at: str

    @field_validator("scheduled_at")
    @classmethod
    def _validate_scheduled_at(cls, v: str) -> str:
        return _normalize_scheduled_at(v)
