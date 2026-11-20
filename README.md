# personal-agent-hack

Our entry for the [tokens& Personal Agents Hackathon](https://tokensand.com/personalagenthack) (Nov 20, 2026, AWS Builder Loft SF).

**Challenge:** build a shopping agent with an audit trail. It helps someone make a purchase or finish a shopping task, takes a real action, and shows the sources and steps behind every decision.

**Team:** Keon, Brendan, Alistair, Kyle

> Project name and pitch go here once the idea is locked in `CONTRACT.md`.

## Start here
1. `git clone https://github.com/Keon-Amid/personal-agent-hack && cd personal-agent-hack`
2. `cp .env.example .env` and fill in the keys you'll use
3. `./scripts/check-setup.sh` checks tools, repo access and keys (it never prints them)
4. Open Claude Code in this folder. It reads `CLAUDE.md` → `CONTEXT.md` automatically.

| File | What it's for |
|---|---|
| `CONTEXT.md` | Event brief, deadlines, prizes, sponsor setup, judges, team rules |
| `IDEAS.md` | Idea shortlist and the real past winners behind them |
| `CONTRACT.md` | What the team has actually agreed on. Nothing else counts as decided. |
| `.env.example` | Every sponsor key we might need |

## Backend
A FastAPI layer over the agent in `agent/`. Run it from the repo root:
```sh
.venv/bin/pip install -r server/requirements.txt
.venv/bin/uvicorn server.app:app --port 8000
```
It loads `.env` at startup and allows the Vite dev server (`localhost:5173`) by default; set `ROOM_FURNISHER_CORS` to change that.

| Endpoint | What it does |
|---|---|
| `POST /api/plan` | Starts a run from room measurements (and optional style, budget, photo or quiz answers); returns `plan_id` at once |
| `GET /api/plan/{id}` | The plan so far: items, cart, audit trail, and run status. Poll it every second |
| `POST /api/plan/{id}/swap` | Swaps one slot's product, re-checks it with Senso and updates the cart |
| `POST /api/plan/{id}/approve` | Records the person's approval in the audit trail and returns a shopping list |
| `GET /api/quiz`, `POST /api/quiz/score` | The 5-question style quiz and its scoring |
| `GET /api/health` | Whether Claude Code and the sponsor keys are available (never the keys) |

Checkout is not automated: approving the cart produces a shopping list of IKEA links and places no order (**MOCKED checkout**).
Full request and response shapes are in `CONTRACT.md` under the Agent section.

## Deadlines (PT)
Demo works end to end by **15:30** · code freeze **16:00** · submit by **16:30** (repo public + demo video link)

## Audit trail format (proposal; agree on it in CONTRACT.md)
Every step the agent takes appends one record, and the UI renders these as a timeline:
```json
{"ts": "2026-11-20T14:02:11Z", "step": "check_policy", "input": "...", "source": {"kind": "senso", "doc": "target-price-match", "passage": "..."}, "decision": "claim", "why": "...", "status": "verified | blocked | sent", "amount_usd": 12.50}
```

## Built with
_Fill in at submission: which sponsor tools we used and for what._
