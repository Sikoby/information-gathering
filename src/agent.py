"""LiveKit worker entrypoint for the briefing-driven voice agent.

Phase 1 form: hardcoded briefing, no metadata reading, no objectives extraction.
"""

from __future__ import annotations

from datetime import datetime, timezone

from dotenv import load_dotenv
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

from .harness import MeetingState, Objective, ObjectiveStatus
from .persistence import Persistence
from .tools import end_meeting, note_followup, record_finding, update_objective_status

load_dotenv()


_HARDCODED_BRIEFING = """\
# Briefing: Phase 1 smoke test

Conduct a brief data warehouse requirements interview. Ask about source
systems (which apps, which databases) and refresh frequency expectations.
Five-minute target. End with a confirmation of the top priority.
"""


_INSTRUCTIONS = f"""\
# ROLE
You are a senior consultant attending a client meeting alone. You are professional,
concise, and warm. You speak in short turns (one or two sentences) and listen.

# MEETING BRIEFING
{_HARDCODED_BRIEFING}

# OPERATING RULES
1. Read the briefing fully before your first turn.
2. After every stakeholder turn, silently ask yourself what the next-highest-value question is.
3. Adapt. Do not run a fixed script. Probe when answers are vague.
4. When you learn something material, call record_finding(topic, content).
5. When the stakeholder signals end of meeting, call end_meeting(reason).
6. If the stakeholder digresses, follow briefly, then steer back.
7. Never invent facts. Never read the briefing aloud.
"""


async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()

    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    persist = Persistence(run_id)
    persist.write_briefing_inline(_HARDCODED_BRIEFING)
    logger.info("run_id={} room={}", run_id, ctx.room.name)

    objective = Objective(
        id="OBJ1",
        objective="Surface source systems and refresh frequencies",
        success_criteria="Stakeholder named at least two source systems and stated refresh expectations.",
    )
    state = MeetingState(
        run_id=run_id,
        briefing_path="<hardcoded>",
        target_minutes=5,
        started_at=datetime.now(timezone.utc),
        briefing_markdown=_HARDCODED_BRIEFING,
        objectives=[objective],
        tracker={objective.id: ObjectiveStatus()},
    )
    persist.write_objectives(state.objectives)

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

    async def _flush_on_shutdown() -> None:
        if state.end_reason is None:
            state.end_reason = "user_ended"
        if state.ended_at is None:
            state.ended_at = datetime.now(timezone.utc)
        persist.flush_state(state)
        logger.info("flushed state to {}", persist.run_dir)

    ctx.add_shutdown_callback(_flush_on_shutdown)

    agent = Agent(
        instructions=_INSTRUCTIONS,
        tools=[record_finding, update_objective_status, note_followup, end_meeting],
    )

    await session.start(agent=agent, room=ctx.room)
    await session.generate_reply(
        instructions=(
            "Greet the stakeholder warmly in two sentences (brief intro plus "
            "your first question per the briefing). Begin now."
        )
    )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, agent_name="briefing-agent"))
