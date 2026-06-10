"""Invite delivery over SMTP.

The console builds the `.ics` (see `ics.py`) and emails it to `rec.invitees`
as a calendar attachment, alongside the stable join link and its PIN. When
`SMTP_HOST` is unset (local dev with no relay), this degrades to the previous
logged no-op so nothing breaks without a mail server.

Intentional simplification: mail is sent `From: SMTP_FROM` (a system mailbox)
while the `.ics` `ORGANIZER` stays the meeting owner. That mismatch is fine
under the calendar `METHOD:PUBLISH` ("here is an event, add it") payload; a true
`REQUEST`/RSVP flow with a matching organizer mailbox is out of scope.
"""

from __future__ import annotations

import os

import aiosmtplib
from email.message import EmailMessage

from loguru import logger

from . import ics
from .models import MeetingRecord


def _meeting_base() -> str:
    return os.environ.get("MEETING_PUBLIC_URL", "http://localhost:8765").rstrip("/")


def _smtp_config() -> dict | None:
    """SMTP settings from env, or None when unconfigured (no `SMTP_HOST`)."""
    host = os.environ.get("SMTP_HOST")
    if not host:
        return None
    return {
        "host": host,
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "username": os.environ.get("SMTP_USERNAME", ""),
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "sender": os.environ.get("SMTP_FROM", "meetings@localhost"),
    }


def _build_message(rec: MeetingRecord, *, summary: str, sender: str) -> EmailMessage:
    join_url = f"{_meeting_base()}/join/{rec.meeting_id}"
    live_view = rec.live_view_url or ""

    body = [
        f"You're invited to: {summary}",
        "",
        f"When: {rec.scheduled_at}",
        "",
        f"Join the meeting:  {join_url}",
        f"PIN:               {rec.join_pin or '(none)'}",
        "",
        "The room opens at the scheduled start time; the PIN is required to "
        "enter. The attached calendar invite has the same details.",
    ]
    if live_view:
        body += ["", f"Live view (read-only): {live_view}"]

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(rec.invitees)
    msg["Subject"] = f"Invitation: {summary}"
    msg.set_content("\n".join(body))

    ics_doc = ics.build_event(
        rec,
        summary=summary,
        organizer_email=rec.owner_email,
        join_url=join_url,
        pin=rec.join_pin,
    )
    msg.add_attachment(
        ics_doc.encode("utf-8"),
        maintype="text",
        subtype="calendar",
        filename="invite.ics",
        params={"method": "PUBLISH", "name": "invite.ics"},
    )
    return msg


async def send_invites(rec: MeetingRecord, *, summary: str) -> bool:
    """Email the calendar invite to `rec.invitees`. True iff a send happened.

    Best-effort: returns False (and logs) when there are no invitees, SMTP is
    unconfigured, or the send raises — the caller treats False as "not sent"
    and never fails meeting creation on it.
    """
    if not rec.invitees:
        return False

    cfg = _smtp_config()
    if cfg is None:
        logger.info(
            "invites: SMTP not configured; skipping email for meeting_id={} "
            "({} invitee(s))",
            rec.meeting_id,
            len(rec.invitees),
        )
        return False

    msg = _build_message(rec, summary=summary, sender=cfg["sender"])

    send_kwargs: dict = {"hostname": cfg["host"], "port": cfg["port"]}
    if cfg["username"] and cfg["password"]:
        send_kwargs["username"] = cfg["username"]
        send_kwargs["password"] = cfg["password"]
    if cfg["port"] == 465:
        send_kwargs["use_tls"] = True
    elif cfg["port"] == 587:
        send_kwargs["start_tls"] = True
    # else (25 / dev relays like mailpit:1025): plain, no TLS.

    try:
        await aiosmtplib.send(msg, **send_kwargs)
    except Exception as e:  # noqa: BLE001 - best-effort; never crash creation
        logger.exception(
            "invites: SMTP send failed for meeting_id={}: {}", rec.meeting_id, e
        )
        return False

    logger.info(
        "invites: emailed {} invitee(s) for meeting_id={} scheduled_at={}",
        len(rec.invitees),
        rec.meeting_id,
        rec.scheduled_at,
    )
    return True
