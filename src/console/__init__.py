"""Meeting console API service.

A stateless, horizontally-scalable aiohttp service that owns the meeting
lifecycle registry (Redis `meeting:*`), drives template generation via the
template-generator service, and starts meetings via the dispatch service.

The console serves a JSON API only — the console SPA is a separate
`console-frontend` container (nginx) that proxies `/api` here.

See [CLAUDE.md](CLAUDE.md) for endpoints, env vars, and the background tasks.
"""
