# CLAUDE.md — template-generator container (`src/template_generator/`)

> **Rule of the house:** any substantial change to this service's endpoints, [Dockerfile.python](../../Dockerfile.python), entry point, environment variables, dependencies, or the impl+critique loop semantics MUST update this CLAUDE.md in the same commit. If you change the request/response shape, persistence layout, or LLM models, update this file. If you finish a change without touching docs, ask yourself whether it was really "substantial" — when in doubt, write the doc.

## Scope

Long-running aiohttp service that turns a free-form meeting description (plus an optional reference template) into a structured [`templates.Template`](../templates/schema.py). Quality is enforced by an **implementation + critique loop** that runs two OpenAI Responses API calls per iteration and stops on critique approval or after `max_iterations`.

This service is **independent of the agent and dispatch path**. The [`console`](../console/) service calls `POST /generate` when a user creates a meeting; the console then lets the user edit the result and passes the final template to the agent inline (via dispatch metadata). Templates are also written to disk. They are **not** auto-registered into the agent's [`TEMPLATES`](../templates/__init__.py) dict.

## File map

```
src/template_generator/
  __init__.py          module marker, doc only.
  __main__.py          aiohttp app + handlers + persistence.
  generator.py         the impl+critique loop, OpenAI calls, prompt construction.
  document_parser.py   .pptx + .pdf → DocumentOutline (title/body/speaker_notes per slide).
  schemas.py           Pydantic request/response/critique models + DocumentOutline.
```

The compose service shares the agent's [Dockerfile.python](../../Dockerfile.python) (different command, same image). Adds `python-pptx` + `pypdf` to `pyproject.toml` for the document parser; everything else (`openai`, `pydantic`, `aiohttp`, `loguru`, `python-dotenv`) was already there.

## Endpoints

| Route | Behavior |
| --- | --- |
| `POST /generate` | Body `{description, reference_template?, document_outline?, max_iterations?, name_hint?}`. Runs the loop, persists, returns `{template_id, storage_path, approved, iterations_used, template, iterations}`. |
| `POST /extract` | Multipart with a `file` part (.pptx / .pdf). Returns a `DocumentOutline` JSON: `{source_name, kind, slides: [{index, title, content, speaker_notes}]}`. Synchronous, no persistence. |
| `GET /templates` | Returns `{templates: [template_id...]}` from disk. |
| `GET /templates/{template_id}` | Returns `{template_id, storage_path, request, template, iterations}` for a previously generated template. |
| `GET /healthz` | 200 iff `OPENAI_API_KEY` is set and `TEMPLATES_DIR` is writable; 503 otherwise. |

### `POST /generate` semantics

- `description` (required): the user's free-form meeting description.
- `reference_template` (optional): a name from [`TEMPLATES`](../templates/__init__.py) — currently one of `requirements`, `research`, `eval`, `generic`. Unknown names return 400. The reference is rendered into the implementation system prompt as structural inspiration; it is **not** copied verbatim.
- `document_outline` (optional): a `DocumentOutline` previously returned by `POST /extract`. When present, the propose and critique system prompts switch on **presentation mode**: the agent emits one TOPIC per slide (in order), copies `speaker_notes` verbatim into `private_notes`, and wraps the walkthrough in framing phases (introduction — AI self-disclosure + consent, Q&A, wrap). A slide may be split into a parent + 2-3 child TOPICs when it covers multiple aspects.
- `max_iterations` (optional, default 3, max 8): hard cap on (propose, critique) cycles. The loop exits early when `critique.approved=true`.
- `name_hint` (optional): suggests a snake_case template id; the implementation agent may override if it has a better idea.

### `POST /extract` semantics

- Multipart upload, single `file` part. `.pptx` and `.pdf` are accepted (detected by extension or `Content-Type`).
- Slide cap: the first 80 slides are returned; longer documents are truncated.
- PDFs have no real "speaker notes" — the first line of each page is treated as the title, the rest as `content`, `speaker_notes` is `null`.
- Failures (unparseable file, wrong MIME) return 400/415 with an error message; the caller is expected to surface it to the user.
- `client_max_size` is 50 MB. Bigger uploads are rejected by aiohttp.

The response includes the **full iteration history** so callers can inspect the critique trail. Even when `approved=false` after the cap, a best-effort template is returned (the final iteration).

### The loop, briefly

1. **Propose** — OpenAI `responses.parse` with `text_format=Template`. On revisions the prior template and critique are injected into the user message.
2. **Critique** — OpenAI `responses.parse` with `text_format=CritiqueResult`. Severity rubric: `blocker`, `major`, `minor`. `approved` is true only when there are zero blocker and zero major issues.
3. Repeat until `approved=true` or `max_iterations` reached.

Both calls use the same model by default (`TEMPLATE_GEN_IMPL_MODEL` / `TEMPLATE_GEN_CRITIQUE_MODEL`, defaulting to `gpt-5`).

## Persistence

```
templates_generated/<template_id>/
  request.json       the originating GenerateRequest
  template.json      the final Template
  iterations.jsonl   one JSON line per (template, critique) iteration
```

`<template_id>` is `<slug-of-template-name>-<utc-iso-timestamp>`. The host's `./templates_generated/` is bind-mounted to `/app/templates_generated/` (read-write) so generated templates survive container restarts.

## What it depends on

- **OpenAI** — implementation + critique calls. No other external services.
- **Volumes** — `./templates_generated:/app/templates_generated` (read-write). No briefings or out volume.
- **No Redis dependency** — the loop is synchronous from the caller's POV; results land in the response and on disk.

## Entry point and command

```
python -m src.template_generator
```

Reads `TEMPLATE_GEN_PORT` (default 8768), `OPENAI_API_KEY`, `TEMPLATES_DIR` (default `/app/templates_generated`), `TEMPLATE_GEN_IMPL_MODEL`, `TEMPLATE_GEN_CRITIQUE_MODEL` from env.

## Env vars

| Variable | Required | Notes |
| --- | --- | --- |
| `OPENAI_API_KEY` | yes | Both impl and critique calls. |
| `TEMPLATE_GEN_PORT` | optional (default 8768) | aiohttp listen port. |
| `TEMPLATES_DIR` | optional (default `/app/templates_generated`) | Where artefacts are written. |
| `TEMPLATE_GEN_IMPL_MODEL` | optional (default `gpt-5`) | Model for the implementation agent. |
| `TEMPLATE_GEN_CRITIQUE_MODEL` | optional (default `gpt-5`) | Model for the critique agent. |

## Verify changes

```
docker compose build template-generator
docker compose up -d template-generator
curl -s http://localhost:8768/healthz                                        # → ok
curl -s -X POST http://localhost:8768/generate \
     -H 'Content-Type: application/json' \
     -d '{
       "description": "Quarterly design review with the platform team. Discuss the proposed architecture, surface risks, identify owners.",
       "reference_template": "requirements",
       "max_iterations": 3
     }' | jq '.template_id, .approved, .iterations_used'

# Extract an uploaded deck (presentation mode):
curl -s -X POST http://localhost:8768/extract \
     -F "file=@deck.pptx" | jq '.kind, (.slides | length)'
```

Or use the CLI: `uv run python scripts/generate_template.py --description "..." --reference requirements`.

## Out of scope (deferred)

- Auto-registration into the agent's hardcoded `TEMPLATES` dict — it still holds only the four built-ins. Custom templates reach the agent inline via dispatch metadata (the console path), not this dict.
- Browsing the on-disk `templates_generated/` store. The console keeps its own copy of a generated template in the `meeting:*` registry; nothing reads the disk artefacts back.
- Caching — every request re-runs both LLM calls. Add prompt caching if costs become an issue.
- Auth on the public endpoint. Same posture as dispatch / meeting today.

## Scaling

Stateless except for the disk volume, which is shared. Multiple replicas can serve `POST /generate` concurrently and write into the same templates directory; the `<name>-<timestamp>` id makes collisions improbable.
