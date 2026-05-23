"""Template generation service.

A separate container that turns a free-form meeting description (plus an optional
reference template) into a structured `templates.Template` via an implementation
+ critique loop driven by the OpenAI Responses API.

See [CLAUDE.md](CLAUDE.md) for endpoints, env vars, and the loop semantics.
"""
