"""In-process animated face for the agent.

The agent process renders its own avatar frames (via PIL) and publishes them
as the agent participant's video track in the LiveKit room. No third party,
no remote service, perfect A/V sync — the same audio buffer that feeds the
LiveKit audio track also drives the visualizer.

Wiring (in `src/agent.py`):

    avatar = OrbAvatarSession()
    await avatar.start(session, room=ctx.room)
    await session.start(agent=agent, room=ctx.room)

Avatar MUST be started before AgentSession so its audio output replaces the
default room audio sink cleanly; otherwise the base class logs a warning.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

import numpy as np
from livekit import rtc
from livekit.agents import utils
from livekit.agents.voice import AgentSession
from livekit.agents.voice.avatar import (
    AudioSegmentEnd,
    AvatarOptions,
    AvatarRunner,
    AvatarSession,
    QueueAudioOutput,
    VideoGenerator,
)
from loguru import logger

from .avatar_render import AnimationState, CANVAS, push_audio_samples, render_frame

VIDEO_FPS = 24
AUDIO_SAMPLE_RATE = 24000  # gpt-realtime output rate
AUDIO_CHANNELS = 1

_AMP_ATTACK = 0.4   # how fast smoothed amplitude rises toward new RMS
_AMP_DECAY_PER_FRAME = 0.92  # exponential decay applied each video tick


class _OrbVideoGenerator(VideoGenerator):
    """Drives the render loop, passes audio through, computes amplitude."""

    def __init__(self, opts: AvatarOptions) -> None:
        self._opts = opts
        self._out: utils.aio.Chan[rtc.VideoFrame | rtc.AudioFrame | AudioSegmentEnd] = (
            utils.aio.Chan()
        )
        self._anim_state = AnimationState()
        self._render_task: asyncio.Task[None] | None = None
        self._start_monotonic = 0.0
        self._closed = False

    def start(self) -> None:
        self._start_monotonic = time.monotonic()
        self._render_task = asyncio.create_task(self._render_loop())

    def set_semantic_state(self, state: str) -> None:
        if state in ("initializing", "idle", "listening", "thinking", "speaking"):
            self._anim_state.semantic_state = state  # type: ignore[assignment]

    async def push_audio(self, frame: rtc.AudioFrame | AudioSegmentEnd) -> None:
        if isinstance(frame, rtc.AudioFrame):
            self._update_amplitude(frame)
        await self._out.send(frame)

    def clear_buffer(self) -> None:
        # Drop any audio frames queued but not yet consumed by the runner.
        # We must NOT drop video frames — the orb must keep animating.
        keep: list[rtc.VideoFrame] = []
        while True:
            try:
                item = self._out.recv_nowait()
            except utils.aio.channel.ChanEmpty:
                break
            if isinstance(item, rtc.VideoFrame):
                keep.append(item)
        for f in keep:
            self._out.send_nowait(f)
        # Force amplitude to decay quickly after interruption.
        self._anim_state.amplitude *= 0.3

    def __aiter__(self) -> AsyncIterator[rtc.VideoFrame | rtc.AudioFrame | AudioSegmentEnd]:
        return self._out

    async def aclose(self) -> None:
        self._closed = True
        if self._render_task is not None:
            await utils.aio.cancel_and_wait(self._render_task)
        self._out.close()

    def _update_amplitude(self, frame: rtc.AudioFrame) -> None:
        # int16 mono PCM → RMS in [0, 1].
        samples_i16 = np.frombuffer(bytes(frame.data), dtype=np.int16)
        if samples_i16.size == 0:
            return
        push_audio_samples(samples_i16)
        samples = samples_i16.astype(np.float32)
        rms = float(np.sqrt(np.mean(samples * samples))) / 32768.0
        # Slight perceptual boost so quiet speech still moves the bars.
        boosted = min(1.0, rms * 3.5)
        prev = self._anim_state.amplitude
        self._anim_state.amplitude = prev + _AMP_ATTACK * (boosted - prev) if boosted > prev else boosted

    async def _render_loop(self) -> None:
        period = 1.0 / self._opts.video_fps
        next_tick = time.monotonic()
        while not self._closed:
            t = time.monotonic() - self._start_monotonic
            try:
                pil_img = render_frame(self._anim_state, t)
                raw = pil_img.tobytes()  # RGBA
                vf = rtc.VideoFrame(
                    width=self._opts.video_width,
                    height=self._opts.video_height,
                    type=rtc.VideoBufferType.RGBA,
                    data=raw,
                )
                await self._out.send(vf)
            except Exception:
                logger.exception("avatar render failed; skipping frame")

            if self._anim_state.semantic_state != "speaking":
                self._anim_state.amplitude *= _AMP_DECAY_PER_FRAME

            next_tick += period
            sleep_for = next_tick - time.monotonic()
            if sleep_for < 0:
                next_tick = time.monotonic()
            else:
                await asyncio.sleep(sleep_for)


class OrbAvatarSession(AvatarSession):
    """Publishes the agent's audio + a Python-rendered orb video into the room."""

    def __init__(self) -> None:
        super().__init__()
        self._runner: AvatarRunner | None = None
        self._video_gen: _OrbVideoGenerator | None = None
        self._audio_io: QueueAudioOutput | None = None
        self._agent_session: AgentSession | None = None
        self._room: rtc.Room | None = None

    @property
    def avatar_identity(self) -> str:
        if self._room is not None and self._room.local_participant is not None:
            return self._room.local_participant.identity
        return "orb-avatar"

    @property
    def provider(self) -> str:
        return "orb-local"

    async def start(self, agent_session: AgentSession, room: rtc.Room) -> None:
        self._room = room  # set before super().start so its wait task can read identity
        await super().start(agent_session, room)
        self._agent_session = agent_session

        opts = AvatarOptions(
            video_width=CANVAS,
            video_height=CANVAS,
            video_fps=VIDEO_FPS,
            audio_sample_rate=AUDIO_SAMPLE_RATE,
            audio_channels=AUDIO_CHANNELS,
        )

        self._audio_io = QueueAudioOutput(sample_rate=AUDIO_SAMPLE_RATE)
        self._video_gen = _OrbVideoGenerator(opts)
        self._runner = AvatarRunner(
            room=room,
            audio_recv=self._audio_io,
            video_gen=self._video_gen,
            options=opts,
        )

        agent_session.on("agent_state_changed", self._on_agent_state_changed)

        self._video_gen.start()
        await self._runner.start()

        # Route the agent's TTS audio through our queue so the runner can read it.
        agent_session.output.audio = self._audio_io
        logger.info("orb avatar session started ({}x{} @ {} fps)", CANVAS, CANVAS, VIDEO_FPS)

    def _on_agent_state_changed(self, ev) -> None:
        if self._video_gen is not None:
            self._video_gen.set_semantic_state(ev.new_state)

    async def aclose(self) -> None:
        if self._agent_session is not None:
            self._agent_session.off("agent_state_changed", self._on_agent_state_changed)
        if self._video_gen is not None:
            await self._video_gen.aclose()
        if self._runner is not None:
            await self._runner.aclose()
        logger.info("orb avatar session closed")
