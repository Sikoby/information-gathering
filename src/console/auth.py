"""Per-user identity for the console.

Identity comes from the `Cf-Access-Authenticated-User-Email` header that
Cloudflare Access stamps onto every request once the user has signed in.
In local dev the request goes through nginx → console with no Cloudflare in
front, so a `CONSOLE_DEV_USER_EMAIL` env var supplies a fallback email.

The middleware is applied to every route except `/healthz`; a missing
identity yields `401`. Handlers read `request["user_email"]`.
"""

from __future__ import annotations

import os

from aiohttp import web

_HEADER = "Cf-Access-Authenticated-User-Email"
_ENV_FALLBACK = "CONSOLE_DEV_USER_EMAIL"
_TEAM_ENV = "CONSOLE_CF_TEAM_DOMAIN"
_OPEN_PATHS = frozenset({"/healthz"})


def resolve_user_email(request: web.Request) -> str | None:
    email = request.headers.get(_HEADER) or os.environ.get(_ENV_FALLBACK, "")
    email = email.strip().lower()
    return email or None


def resolve_logout_url() -> str | None:
    """Team-domain Access logout URL from CONSOLE_CF_TEAM_DOMAIN (None if unset)."""
    team = os.environ.get(_TEAM_ENV, "").strip()
    if not team:
        return None
    host = team if "." in team else f"{team}.cloudflareaccess.com"
    return f"https://{host}/cdn-cgi/access/logout"


@web.middleware
async def auth_middleware(request: web.Request, handler):
    if request.path in _OPEN_PATHS:
        return await handler(request)
    email = resolve_user_email(request)
    if email is None:
        return web.json_response(
            {"error": "not authenticated"}, status=401
        )
    request["user_email"] = email
    return await handler(request)
