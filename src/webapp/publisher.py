"""Per-meeting state publisher and module-level registry.

The agent process holds one `StatePublisher` per active meeting, keyed by
`run_id`. Each publisher snapshots `MeetingState` to JSON and broadcasts to all
connected SSE subscribers. Subscribers receive the current snapshot on connect
and every subsequent `publish()` call.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from ..harness import MeetingState


class StatePublisher:
    def __init__(self, state: "MeetingState") -> None:
        self.state: "MeetingState" = state
        self._subscribers: set[asyncio.Queue[str]] = set()

    def latest_snapshot_json(self) -> str:
        return json.dumps(self.state.model_dump(mode="json"))

    async def publish(self) -> None:
        snapshot = self.latest_snapshot_json()
        for q in list(self._subscribers):
            try:
                q.put_nowait(snapshot)
            except asyncio.QueueFull:
                logger.warning(
                    "subscriber queue full for run_id={}; dropping snapshot",
                    self.state.run_id,
                )

    def subscribe(self) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=32)
        q.put_nowait(self.latest_snapshot_json())
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[str]) -> None:
        self._subscribers.discard(q)


_publishers: dict[str, StatePublisher] = {}


def register(state: "MeetingState") -> StatePublisher:
    pub = StatePublisher(state)
    _publishers[state.run_id] = pub
    logger.info("registered state publisher for run_id={}", state.run_id)
    return pub


def unregister(run_id: str) -> None:
    _publishers.pop(run_id, None)


def get_publisher(run_id: str) -> StatePublisher | None:
    return _publishers.get(run_id)


async def publish(state: "MeetingState") -> None:
    """Broadcast the latest state for `state.run_id`. No-op if unregistered."""
    pub = _publishers.get(state.run_id)
    if pub is None:
        return
    pub.state = state
    await pub.publish()
