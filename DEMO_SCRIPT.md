# Demo script — walking someone through the meeting agent

---

## 1. Introduction — what this thing is (1–2 min, no clicking yet)

> "My Name is Simon and this is a **voice meeting agent** that joins an online meeting room, runs the conversation from a plan I give it, and writes down a clean, structured record of what it learned."

> "The to pieces today: a **template**  the reusable plan — and a **meeting** — one run of that plan with a real person. Let me show you how I build one."

---

## 2. Templates — how a meeting is designed (5 min)

> "First, the core idea: I model a meeting as a **tree**. A top-level section can have subsections, those can have their own children, as deep as I want — a broad topic that branches into sub-topics, each with its own questions. The agent walks that tree, and as it talks it **zooms in** — into a subsection to dig deeper — and **zooms back out** when it's done, moving on to the next branch. Every one of those moves is a logged **transition**, so the whole path through the meeting is recorded. That tree is what a template is."

**Show the dashboard.**
> "This is the console — the front door. Templates up top, meetings below. Let's build a template."

  *Click the **New** (＋) button on the Templates section → lands on the prompt form.*

> "I just describe the meeting in plain language and the system drafts the plan for me."

  *Type a prompt, e.g.:*
  > "Run a 20-minute intake interview with a new customer to understand their data warehouse requirements: their current stack, pain points, reporting needs, and timeline."

  *Click create. The template goes into a **generating** state (spinning indicator).*

> "Behind that spinner, an LLM is running an **implementation-and-critique loop** — it drafts the plan, critiques its own draft, and revises. That's the slow step, so I've also got one already baked."

  *Either wait for it, or switch to the pre-generated "ready" template to keep momentum.*

> "And the prompt isn't the only context I can give it. If I already have a slide deck or a PDF, I can hand that over too — the system pulls each slide in as a section and folds the speaker notes into the agent's private script. It's the same creation flow, just with richer source material to work from."

  *(Point at the upload control on the New Template form; you don't have to actually upload unless you want to.)*

**Open the ready template.**
> "Here's a finished one — this is the editor."

  *Walk through the structure:*
> "Here's that tree. Each node is either a **topic** — an area to cover — or a **question** — something specific to ask. I can reorder, nest, add, delete, retitle. And this field — **speaker notes / private notes** — is the agent's cheat sheet for that node: it follows these, but never reads them aloud to the participant."

> "So designing a meeting is really just shaping this tree and getting the notes right. Then I hit start. No code."

---

## 3. Starting a meeting (3 min)

> "Now I turn that plan into a real conversation. From the template I click **Start a meeting**."

  *Click **Start** on the template → routes to the New Meeting page with the template preselected.*

> "I give it a title and a target duration. Then I've got two choices."

> "**Start now** — it spins up the meeting immediately and hands me two links: a **join link** to talk to the agent, and a **live-view link** to watch the notes build up."

> "**Schedule for later** — I pick a time and add the people I want intervieId. The system emails each of them a calendar invite plus a permanent, PIN-protected join link, and the agent dispatches itself when the time comes."

  *(If showing the schedule/email path: schedule one with an invitee, then show the email landing in Mailpit at http://localhost:8025 — point out the .ics and the join link + PIN.)*

> "And there's a **batch** version of this — one template, a list of people, and it launches a separate parallel meeting for each one. That's how you interview thirty people overnight from a single plan."

**For the live demo, use Start now.**
  *Click **Start** (Start now). The result panel shows the join link + live-view link.*

> "Okay — it's live. I'm going to open the **live view** here so you can watch, and I'll hand you the **join link** so you can be the person who gets intervieId."

  *Open the live-view link in your window. Hand the join link to the participant.*

---

## 4. Handing off — the participant joins (let them drive)

> "Open the link I sent you. You'll hit a join page — click to join, allow the microphone, and just talk to the agent like it's a normal call. It'll lead; ansIr naturally, and feel free to ramble — that's the point."

  *They join. The agent greets them and starts working the template.*

**While they talk, narrate the live view to the room:**
> "Watch this side. Every box you see appearing is the agent taking structured notes in real time. Here's the **agenda** it's working through, here's the **current topic**, and these are the **findings** it's filling in as you ansIr. Down here are **follow-ups** — open questions it wants to circle back to."

> "Notice it's not transcribing blindly — it's *organizing*. By the end I don't have a wall of text, I have a filled-in structure: this is what they said about their stack, this is the pain point, this is the timeline."

**Let the conversation run a few minutes**, then either let the agent wrap naturally or end the call.

---

## 5. Wrap-up (1 min)

> "So that's the whole loop: someone describes a meeting in plain language, the system drafts a structured plan, they tIak it and hit go, the agent runs the actual voice conversation, and anyone watching gets a clean, organized record as it happens — no note-taker, no code."

> "And because it's all driven by that one reusable template, the same plan scales from one interview to hundreds, each in its own room, all at once."

*Questions.*

---

## Quick reference — URLs & ports

| What | URL |
| --- | --- |
| Console (create templates + meetings) | http://localhost:8769 |
| Participant app (join + live view) | http://localhost:8765 |
| Mailpit dev inbox (invite emails) | http://localhost:8025 |
| Live preview without LiveKit (fallback demo) | `scripts/preview_dev_server.py` → http://localhost:8767/dev/ |

## If something breaks mid-demo

- **Template stuck generating** → switch to the pre-baked "ready" template; don't wait on the LLM live.
- **Mic / LiveKit won't connect** → fall back to the synthetic live view (`scripts/preview_dev_server.py`, then open `/dev/`) to still show the streaming-notes story.
- **Join link 404 / "not started"** → the meeting must be **running**; for a scheduled one it only goes live at its start time. Use **Start now** for the live demo.
- **Containers not healthy** → `docker compose up -d`, give it a few seconds, refresh the console.
