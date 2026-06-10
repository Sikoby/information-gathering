"""LiveKit worker entrypoint for the briefing-driven voice agent.

Reads briefing_description, run_id, target_minutes (and an optional
custom_template) from ctx.job.metadata (JSON), selects a Template, builds a
typed MeetingState, and starts a gpt-realtime session whose system prompt is
composed from the briefing and the live section tree.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone

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
from openai.types.realtime.realtime_audio_input_turn_detection import ServerVad

from .briefing_plan import select_template
from .harness import (
    MeetingState,
    build_instructions,
    new_state_sections,
    schedule_time_warning,
)
from . import meeting
from .extraction import run_extractor
from .persistence import Persistence
from .templates import (
    ROOT_SECTION_ID,
    Template,
    scheduled_nodes,
    section_by_id,
)
from .tools import (
    deliver_pyramid_summary,
    end_meeting,
    navigate,
    note_followup,
    record_finding,
)

load_dotenv()


def _parse_metadata(raw: str | None) -> dict:
    if not raw:
        raise RuntimeError(
            "Job metadata is empty. This worker only runs on explicit dispatch with "
            "JSON metadata {briefing_description, run_id, target_minutes}. "
            "Use scripts/dispatch.py or the console."
        )
    try:
        meta = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Job metadata is not valid JSON: {e}") from e
    for key in ("briefing_description", "run_id", "target_minutes"):
        if key not in meta:
            raise RuntimeError(f"Job metadata missing required key: {key}")
    return meta


async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()

    meta = _parse_metadata(ctx.job.metadata)
    run_id: str = meta["run_id"]
    target_minutes: int = int(meta["target_minutes"])
    briefing_markdown: str = meta["briefing_description"]

    logger.info("run_id={} room={}", run_id, ctx.room.name)

    persist = Persistence(run_id)
    persist.write_briefing_inline(briefing_markdown)

    custom_template = (
        Template.model_validate(meta["custom_template"])
        if "custom_template" in meta
        else None
    )
    template, briefing_body = select_template(
        briefing_markdown, custom_template=custom_template
    )
    logger.info(
        "template={} custom_template={}",
        template.name,
        custom_template is not None,
    )

    briefing_path = persist.briefing_path
    sections = new_state_sections(template)
    # Start the cursor in the introduction phase (first scheduled top-level
    # TOPIC), not at the synthetic _root. The agent's whole opening — AI self-
    # intro, consent, agenda preview — now lives in that first phase, so there's
    # no separate "frame the meeting then drill down into the intro" double-open.
    first_phase = next(iter(scheduled_nodes(sections)), None)
    start_id = first_phase.id if first_phase else ROOT_SECTION_ID
    # Seed the MEETING overview card from the template (replaces what the removed
    # frame_meeting tool used to populate for the live viewer).
    root = section_by_id(sections, ROOT_SECTION_ID)
    if root is not None:
        root.header = template.name
        root.body = template.description
    state = MeetingState(
        run_id=run_id,
        briefing_path=str(briefing_path),
        target_minutes=target_minutes,
        started_at=datetime.now(timezone.utc),
        briefing_markdown=briefing_body,
        template=template,
        sections=sections,
        current_section_id=start_id,
        visited_section_ids=[start_id] if start_id != ROOT_SECTION_ID else [],
    )
    await meeting.register(state)

    meeting_base = os.environ.get("MEETING_PUBLIC_URL", "http://localhost:8765")
    live_view_url = f"{meeting_base}/{run_id}/"

    async def _post_live_view_url() -> None:
        try:
            await ctx.room.local_participant.send_text(
                f"Live meeting view: {live_view_url}",
                topic="lk.chat",
            )
            logger.info("posted live view url to chat: {}", live_view_url)
        except Exception as e:
            logger.warning("failed to post live view url to chat: {}", e)

    @ctx.room.on("participant_connected")
    def _on_participant_connected(participant: rtc.RemoteParticipant) -> None:
        logger.info("participant joined: {}", participant.identity)
        asyncio.create_task(_post_live_view_url())

    realtime_model = oai_plugin.realtime.RealtimeModel(
        model="gpt-realtime",
        voice="cedar",
        input_audio_transcription=openai_realtime.AudioTranscription(
            model="gpt-4o-mini-transcribe",
        ),
        # End the user's turn a fixed 600ms after they stop speaking. The
        # plugin default is semantic_vad (eagerness="medium") — a model-based
        # "have you finished your thought?" judgment that stalled 30-50s on
        # short/ambiguous utterances. server_vad is silence-based and prompt.
        # The session defers to this server-side detection (the local silero
        # VAD is only used for interruptions), so this is the knob that matters.
        turn_detection=ServerVad(
            type="server_vad",
            threshold=0.5,
            prefix_padding_ms=300,
            silence_duration_ms=600,
            create_response=True,
            interrupt_response=True,
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
        asyncio.create_task(meeting.publish(state))

    async def _flush_on_shutdown() -> None:
        if state.end_reason is None:
            state.end_reason = "user_ended"
        if state.ended_at is None:
            state.ended_at = datetime.now(timezone.utc)
        # Best-effort: let the extractor file any still-queued notes before we snapshot.
        if state._note_queue is not None:
            try:
                await asyncio.wait_for(state._note_queue.join(), timeout=20.0)
            except asyncio.TimeoutError:
                logger.warning("extractor drain timed out; some notes may be unfiled")
        persist.flush_state(state)
        await meeting.publish(state)
        await meeting.unregister(state.run_id)
        logger.info("flushed state to {}", persist.run_dir)

    ctx.add_shutdown_callback(_flush_on_shutdown)

    instructions = build_instructions(state, elapsed_minutes=0.0)
    agent = Agent(
        instructions=instructions,
        tools=[
            record_finding,
            navigate,
            deliver_pyramid_summary,
            note_followup,
            end_meeting,
        ],
    )
    # Runtime handles for the tools: the Agent (navigate uses it to refresh instructions
    # and window history) and the note queue (record_finding enqueues onto it).
    state._agent = agent
    state._note_queue = asyncio.Queue()

    await session.start(agent=agent, room=ctx.room)

    # Single background worker drains the note queue, files findings via gpt-5-mini.
    asyncio.create_task(run_extractor(state))

    # Wait for a human before greeting — a greeting to an empty room is never heard.
    await ctx.wait_for_participant()
    state.started_at = datetime.now(timezone.utc)

    asyncio.create_task(schedule_time_warning(agent, state))
    await session.generate_reply(
        instructions=(
            "Open the meeting now. You're already in the first phase — the "
            "introduction. Start by introducing yourself: say you're an AI voice "
            "agent running this meeting and briefly what it's about, then ask the "
            "participant whether they're happy to go ahead. Don't wait for a formal "
            "yes — read their reply and continue naturally into the introduction. "
            "Briefly preview the agenda, then begin. Do NOT call navigate — you "
            "already start in the first phase."
        )
    )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, agent_name="briefing-agent"))
