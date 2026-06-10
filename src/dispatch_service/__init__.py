"""Long-running dispatch HTTP service.

Run with `python -m src.dispatch_service`. Exposes:
- POST /dispatch  body {briefing_description, target_minutes,
                  custom_template?, run_id?}
                  returns {run_id, room, join_url, live_view_url}
- GET  /runs      returns active run_ids from Redis (best-effort)
- GET  /healthz   200 if LiveKit env vars present
"""
