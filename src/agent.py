"""LiveKit worker entrypoint for the briefing-driven voice agent.

Reads briefing_path, run_id, target_minutes from ctx.job.metadata (JSON),
selects a template from the briefing, builds a typed MeetingState, and starts
a gpt-realtime session whose system prompt is composed from the briefing and
the live section tree.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    WorkerOptions,
    cli,
)
from livekit.agents.llm import ChatMessage
from livekit.plugins import openai as oai_plugin, silero
from loguru import logger
from openai.types import realtime as openai_realtime

from .avatar import OrbAvatarSession
from .briefing_plan import select_template
from .harness import (
    MeetingState,
    build_instructions,
    elapsed_minutes,
    new_state_sections,
    schedule_time_warning,
)
from . import webapp
from .persistence import Persistence
from .templates import ROOT_SECTION_ID
from .tools import (
    deliver_pyramid_summary,
    end_meeting,
    frame_meeting,
    navigate,
    note_followup,
    record_finding,
)

load_dotenv()


def _parse_metadata(raw: str | None) -> dict:
    if not raw:
        raise RuntimeError(
            "Job metadata is empty. This worker only runs on explicit dispatch with "
            "JSON metadata {briefing_path, run_id, target_minutes}. Use scripts/dispatch.py."
        )
    try:
        meta = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Job metadata is not valid JSON: {e}") from e
    for key in ("briefing_path", "run_id", "target_minutes"):
        if key not in meta:
            raise RuntimeError(f"Job metadata missing required key: {key}")
    return meta


async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()

    meta = _parse_metadata(ctx.job.metadata)
    briefing_path = Path(meta["briefing_path"])
    run_id: str = meta["run_id"]
    target_minutes: int = int(meta["target_minutes"])
    briefing_markdown = briefing_path.read_text()

    logger.info("run_id={} room={} briefing={}", run_id, ctx.room.name, briefing_path)

    persist = Persistence(run_id)
    persist.copy_briefing(briefing_path)

    template, briefing_body = select_template(briefing_markdown)
    logger.info(
        "template={} sections={} phases={}",
        template.name,
        len(template.sections),
        len(template.scheduled_nodes()),
    )

    state = MeetingState(
        run_id=run_id,
        briefing_path=str(briefing_path),
        target_minutes=target_minutes,
        started_at=datetime.now(timezone.utc),
        briefing_markdown=briefing_body,
        template=template,
        sections=new_state_sections(template),
        current_section_id=ROOT_SECTION_ID,
    )
    await webapp.register(state)

    webapp_base = os.environ.get(
        "WEBAPP_PUBLIC_URL",
        f"http://localhost:{os.environ.get('WEBAPP_PORT', '8765')}",
    )
    webapp_url = f"{webapp_base}/{run_id}/"

    async def _post_webapp_url() -> None:
        try:
            await ctx.room.local_participant.send_text(
                f"Live meeting view: {webapp_url}",
                topic="lk.chat",
            )
            logger.info("posted webapp url to chat: {}", webapp_url)
        except Exception as e:
            logger.warning("failed to post webapp url to chat: {}", e)

    @ctx.room.on("participant_connected")
    def _on_participant_connected(participant: rtc.RemoteParticipant) -> None:
        logger.info("participant joined: {}", participant.identity)
        asyncio.create_task(_post_webapp_url())

    realtime_model = oai_plugin.realtime.RealtimeModel(
        model="gpt-realtime",
        voice="cedar",
        input_audio_transcription=openai_realtime.AudioTranscription(
            model="gpt-4o-mini-transcribe",
        ),
    )

    session: AgentSession[MeetingState] = AgentSession(
        userdata=state,
        llm=realtime_model,
        vad=silero.VAD.load(),
    )

    @session.on("conversation_item_added")
    def _on_item_added(ev) -> None:
        item = ev.item
        if isinstance(item, ChatMessage) and item.role in ("user", "assistant"):
            text = item.text_content
            if text:
                persist.append_transcript(item.role, text)

    @session.on("user_state_changed")
    def _on_user_state_changed(ev) -> None:
        if ev.old_state != "speaking" or ev.new_state != "listening":
            return
        state.user_turn_count += 1
        asyncio.create_task(webapp.publish(state))
        if state.user_turn_count % 4 == 0:
            new = build_instructions(state, elapsed_minutes(state))
            asyncio.create_task(agent.update_instructions(new))
            logger.info("instructions refreshed at user turn {}", state.user_turn_count)

    async def _flush_on_shutdown() -> None:
        if state.end_reason is None:
            state.end_reason = "user_ended"
        if state.ended_at is None:
            state.ended_at = datetime.now(timezone.utc)
        persist.flush_state(state)
        await webapp.publish(state)
        await webapp.unregister(state.run_id)
        logger.info("flushed state to {}", persist.run_dir)

    ctx.add_shutdown_callback(_flush_on_shutdown)

    instructions = build_instructions(state, elapsed_minutes=0.0)
    agent = Agent(
        instructions=instructions,
        tools=[
            record_finding,
            navigate,
            frame_meeting,
            deliver_pyramid_summary,
            note_followup,
            end_meeting,
        ],
    )

    avatar = OrbAvatarSession()
    await avatar.start(session, room=ctx.room)

    await session.start(agent=agent, room=ctx.room)
    asyncio.create_task(schedule_time_warning(agent, state))
    await session.generate_reply(
        instructions=(
            "Open the meeting now. First call frame_meeting(bluf, situation, "
            "complication), then speak the BLUF + situation + complication + "
            "agenda aloud in 2–3 sentences. Then navigate to the first phase."
        )
    )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, agent_name="briefing-agent"))
