"""Minimal RFC 5545 VCALENDAR/VEVENT builder for meeting invites.

Hand-rolled (no `icalendar` dependency): a single `VEVENT` with correct text
escaping and 75-octet line folding so common calendar clients (Google, Apple,
Outlook) import it cleanly. This is what the `GET …/invite.ics` download
endpoint returns, and what the future email step (see `invites.py`) will
attach.

Simplification: the calendar `METHOD` is `PUBLISH` (a "here is an event, add
it to your calendar" payload). `ATTENDEE` lines are included for visibility
of who is invited; a true `REQUEST`/RSVP flow arrives with server-side email.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .models import MeetingRecord


_PRODID = "-//information-gathering//meeting-console//EN"


def _parse_iso_utc(value: str) -> datetime:
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _ical_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _escape(text: str) -> str:
    """Escape a TEXT value per RFC 5545 §3.3.11."""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def _fold(line: str) -> str:
    """Fold one content line to <=75 octets, continued with CRLF + space.

    Folds on UTF-8 byte boundaries so a multibyte character is never split.
    """
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    out = bytearray()
    start = 0
    first = True
    while start < len(raw):
        limit = 75 if first else 74  # continuation lines carry a leading space
        end = min(start + limit, len(raw))
        # back off so we never cut inside a UTF-8 multibyte sequence
        while end < len(raw) and (raw[end] & 0xC0) == 0x80:
            end -= 1
        if not first:
            out += b" "
        out += raw[start:end]
        if end < len(raw):
            out += b"\r\n"
        start = end
        first = False
    return out.decode("utf-8")


def _serialize(lines: list[str]) -> str:
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def build_event(
    rec: MeetingRecord,
    *,
    summary: str,
    organizer_email: str,
) -> str:
    """Return a single-VEVENT VCALENDAR document for a scheduled meeting.

    `rec.scheduled_at` must be set (the caller guarantees it). The event URL
    and description point at the meeting's stable public live-view page
    (`rec.webapp_url`); the short-lived voice-join link does not exist until
    the deferred dispatch fires at start time.
    """
    start = _parse_iso_utc(rec.scheduled_at or "")
    end = start + timedelta(minutes=rec.target_minutes)
    now = datetime.now(timezone.utc)

    live_view = rec.webapp_url or ""
    description = (
        f"AI-run meeting.\\n\\nLive view (read-only): {live_view}\\n\\n"
        "The voice-join link is issued when the meeting starts."
    )

    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{_PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{rec.meeting_id}@information-gathering",
        f"DTSTAMP:{_ical_utc(now)}",
        f"DTSTART:{_ical_utc(start)}",
        f"DTEND:{_ical_utc(end)}",
        f"SUMMARY:{_escape(summary)}",
        f"DESCRIPTION:{description}",
        f"ORGANIZER;CN={_escape(organizer_email)}:mailto:{organizer_email}",
    ]
    if live_view:
        lines.append(f"URL:{live_view}")
    for invitee in rec.invitees:
        lines.append(
            "ATTENDEE;ROLE=REQ-PARTICIPANT;RSVP=TRUE;"
            f"CN={_escape(invitee)}:mailto:{invitee}"
        )
    lines += ["STATUS:CONFIRMED", "END:VEVENT", "END:VCALENDAR"]
    return _serialize(lines)
