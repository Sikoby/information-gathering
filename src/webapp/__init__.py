"""Per-meeting read-only webapp.

This module is the agent's view of the webapp service. The webapp runs in its
own container (`python -m src.webapp`); the agent only writes state via the
functions re-exported here.

Public surface used by agent.py and tools.py:
- publish(state)       → broadcast the latest state to Redis
- register(state)      → mark a run as active + publish its first snapshot
- unregister(run_id)   → remove a run from the active set
"""

from __future__ import annotations

from .publisher import publish, register, unregister

__all__ = ["publish", "register", "unregister"]
