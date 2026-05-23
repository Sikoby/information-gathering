"""Pydantic models for the meeting console registry and HTTP API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


MeetingStatus = Literal["planned", "running", "done"]
TemplateStatus = Literal["generating", "ready", "failed"]

_PROMPT_MAX = 16_000


class MeetingRecord(BaseModel):
    """The full meeting record stored (as JSON) at `meeting:<meeting_id>`.

    `template` is a Template JSON object in this model and in API responses;
    the registry stores it as an embedded JSON *string* so the atomic Lua
    merge never round-trips its nested arrays through cjson.
    """

    meeting_id: str
    title: str
    prompt: str
    reference_template: str | None = None
    target_minutes: int = 30

    status: MeetingStatus = "planned"
    template_status: TemplateStatus = "generating"

    template: dict | None = None
    template_error: str | None = None
    template_approved: bool | None = None
    template_iterations_used: int | None = None
    generation_seq: int = 0

    run_id: str | None = None
    room: str | None = None
    join_url: str | None = None
    webapp_url: str | None = None

    created_at: str
    updated_at: str
    dispatched_at: str | None = None
    ended_at: str | None = None
    end_reason: str | None = None


class MeetingCreate(BaseModel):
    """`POST /api/meetings` body."""

    title: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1, max_length=_PROMPT_MAX)
    reference_template: str | None = None
    target_minutes: int = Field(default=30, ge=1, le=120)


class MeetingPatch(BaseModel):
    """`PATCH /api/meetings/{id}` body — all fields optional."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    prompt: str | None = Field(default=None, min_length=1, max_length=_PROMPT_MAX)
    template: dict | None = None
    target_minutes: int | None = Field(default=None, ge=1, le=120)


class MeetingStart(BaseModel):
    """`POST /api/meetings/{id}/start` body — optional."""

    target_minutes: int | None = Field(default=None, ge=1, le=120)


class MeetingRegenerate(BaseModel):
    """`POST /api/meetings/{id}/regenerate` body — optional."""

    prompt: str | None = Field(default=None, min_length=1, max_length=_PROMPT_MAX)
    reference_template: str | None = None
