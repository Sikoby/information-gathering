"""Invite delivery — placeholder for server-side email.

Today this is a logged no-op: the console generates a downloadable `.ics`
(see `ics.py`) and the organizer sends it themselves. This module is the
single wiring point where SMTP — or a transactional email provider — will
plug in later. The commented `SMTP_*` slots live in `.env.example`.

When email lands, this is where it goes: build the `.ics` via
`ics.build_event(...)`, attach it to a calendar invite addressed to
`rec.invitees`, send it, and stamp `invite_sent_at` on the record.
"""

from __future__ import annotations

from loguru import logger

from .models import MeetingRecord


async def send_invites(rec: MeetingRecord) -> None:
    """Deliver calendar invites to `rec.invitees`. Currently a logged no-op."""
    if not rec.invitees:
        return
    # TODO(email): wire up SMTP / provider here, then stamp invite_sent_at.
    logger.info(
        "invites: would email {} invitee(s) for meeting_id={} scheduled_at={}",
        len(rec.invitees),
        rec.meeting_id,
        rec.scheduled_at,
    )
