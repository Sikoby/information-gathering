"""Async HTTP clients for the dispatch and template-generator services."""

from __future__ import annotations

import json
import os

import aiohttp


def _dispatch_url() -> str:
    return os.environ.get("DISPATCH_URL", "http://dispatch:8766").rstrip("/")


def _template_gen_url() -> str:
    return os.environ.get(
        "TEMPLATE_GEN_URL", "http://template-generator:8768"
    ).rstrip("/")


class DownstreamError(RuntimeError):
    """A downstream service returned a non-2xx response."""

    def __init__(self, service: str, status: int, body: str) -> None:
        self.service = service
        self.status = status
        self.body = body
        super().__init__(f"{service} returned {status}: {body[:500]}")


async def generate_template(
    session: aiohttp.ClientSession,
    *,
    description: str,
    reference_template: str | None,
    max_iterations: int,
) -> dict:
    """Call template-generator `POST /generate`. Blocks 1-4 min."""
    payload: dict = {"description": description, "max_iterations": max_iterations}
    if reference_template:
        payload["reference_template"] = reference_template
    timeout = aiohttp.ClientTimeout(total=420)
    async with session.post(
        f"{_template_gen_url()}/generate", json=payload, timeout=timeout
    ) as resp:
        body = await resp.text()
        if resp.status != 200:
            raise DownstreamError("template-generator", resp.status, body)
        return json.loads(body)


async def dispatch_meeting(
    session: aiohttp.ClientSession,
    *,
    run_id: str,
    briefing_description: str,
    custom_template: dict,
    target_minutes: int,
) -> dict:
    """Call dispatch `POST /dispatch` to create a room + dispatch the agent."""
    payload = {
        "run_id": run_id,
        "briefing_description": briefing_description,
        "custom_template": custom_template,
        "target_minutes": target_minutes,
    }
    timeout = aiohttp.ClientTimeout(total=30)
    async with session.post(
        f"{_dispatch_url()}/dispatch", json=payload, timeout=timeout
    ) as resp:
        body = await resp.text()
        if resp.status != 200:
            raise DownstreamError("dispatch", resp.status, body)
        return json.loads(body)
