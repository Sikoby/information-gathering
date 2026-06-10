"""Per-meeting participant app — backend package.

This module is the agent's view of the meeting service. The meeting API runs in
its own container (`python -m src.meeting`); the agent only writes state via the
functions re-exported here.

Public surface used by agent.py and tools.py:
- publish(state)       → broadcast the latest state to Redis
- register(state)      → mark a run as active + publish its first snapshot
- unregister(run_id)   → remove a run from the active set
"""

from __future__ import annotations

from .publisher import publish, register, unregister

__all__ = ["publish", "register", "unregister"]
