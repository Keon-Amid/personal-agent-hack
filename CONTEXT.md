# Personal Agents Hackathon — team context

For the team's Claude sessions: read this before doing anything. Facts below were pulled from the two event pages on Nov 20, 2026, around 11:40 PT. Anything marked **unknown** was not published. Ask the organizers; don't guess.

## Team
Keon, Brendan, Alistair, Kyle. Repo: https://github.com/Keon-Amid/personal-agent-hack (Keon's account).
Keon is on UI. The other lanes below are proposed; confirm them in CONTRACT.md.

## The plan (chosen 12:30; details still need to go in CONTRACT.md)
**A room-furnishing shopping agent with 3D rendering.** The person uploads a photo of an empty or ugly room. The agent works out the room's size and style, picks real products with real dimensions, **proves each one fits and is allowed**, shows the result as a 3D room, and builds a real cart that the person approves.

It's inspired by "people-coming-over", which won the grand prize at an earlier event run by these organizers (https://github.com/Nela62/peoplecomingover). That project was a chat window + vision model + product search + a browser agent buying from a **mock** store. It had no 3D, no fit checks and no audit trail. **Don't copy it.** These are the differences:
- **Not a chat app.** The screen is the room plus the audit trail.
- **Verified fit.** Real product W×D×H is checked against the wall, the floor and the doorway. "Sofa B is 3 inches too wide" is our negative control on stage.
- **Rules.** Lease, dorm or fire-code rules live in a Senso KB. Senso fact-checks each pick before it goes in the cart.
- **Audit trail on every item:** why it was picked, its source page, the fit math, Senso's verdict and the price.
- **Real cart, held for approval.** No fake store. If an action is mocked, label it.

**Still undecided: the specific person.** Options: a college student furnishing a dorm (the school publishes room sizes and banned items), a renter on a fixed budget with lease limits, or a refugee resettlement caseworker with a required-items list and a per-family budget (verify the facts first). Pick one in CONTRACT.md.

### Sponsors
| Sponsor | Role in our app |
|---|---|
| **Senso** (core, biggest prize) | KB of product specs and room rules. `senso_check_text` verifies each "fits and is allowed" claim before carting, and that verdict goes in the audit trail. |
| **Superlinked SIE** (core, 2 prizes) | Extracts dimensions from product pages, matches style to the room, reranks candidates with visible scores. |
| **Amplitude** (easy add, UI lane) | A few UI events: item swapped, cart approved. |
| Firedrill (if time) | Rehearse the checkout in a simulation before the real cart. Event code `TOKENSAND`. |
| Cognee (if time) | Remembers taste, budget and room measurements across sessions. |
| Arcee (maybe) | Cheap open model for bulk extraction, framed around their cost/quality "Pareto frontier" prize. |
| Skip | Guild and Persona (access may be sales-gated), SingleStore (overlaps with the core), Airbyte (no data source). |

### Stack
- **Frontend:** React + Vite + TypeScript + **React Three Fiber** (`@react-three/fiber`, `@react-three/drei`).
- **Furniture models:** one generic low-poly model per category (Kenney Furniture Kit, kenney.nl, or Poly Pizza), **scaled to each real product's dimensions**. No per-product models needed.
- **Room:** a room box built from measurements (walls, door, window). The vision model estimates size from the photo using a reference object such as a door or a sheet of paper. Full 3D reconstruction from a photo is out of scope. Stretch: an iPhone Pro LiDAR scan exported as a 3D file (test the export first).
- **Backend:** Python + FastAPI. Claude handles vision and agent reasoning.
- **Data:** about 40 real products with real dimensions (IKEA pages list them) in a JSON file, built in the first hour.
- **Demo video:** QuickTime or Loom.

### Timeline (submission 16:30)
| Time | Goal |
|---|---|
| 12:30–12:50 | CONTRACT.md: the person, the room, budget and rules, the audit-record shape, the frontend↔backend API. Make a fake data file so every lane can start. Keys. |
| 12:50–14:30 | Everyone builds against the fake data. |
| **14:30** | First full run: photo → agent → 3D room → cart |
| **15:30** | Demo works end to end. Polish and record the video. |
| 16:00 | Freeze. Make the repo public. |
| 16:15 | Submit (15 minutes of buffer) |

### Lanes (proposed)
- **Keon, UI:** 3D room view, item cards, audit-trail timeline, approve-cart panel, Amplitude events.
- **Brendan, agent:** photo → room size and style → needs list → picks → Senso check → writes the audit records.
- **Alistair, data + fit:** product catalog, dimension extraction (Superlinked), fit math (wall, floor, doorway clearance), price vs. quality options chart.
- **Kyle, backend + glue:** FastAPI, loading the Senso KB, the real cart action, deploy, submission and video.

### Team Slack (agentchat)
Agents post status to the team channel with `~/team-kit/bin/agentchat` (`merged`, `touched`, `contract`, `blocked`). New member setup: get invited to the Slack workspace and the agent channel, get access to the private `EdanBarrios/team-kit` repo (Edan owns it), clone it to `~/team-kit`, run `cp .env.example .env`, and fill in the bot token (sent by DM, never pasted in a channel or repo), the channel ID and your lowercase name. Test with `bin/agentchat merged "test: hello from <name>"`. Hold off on `install.sh`: the kit's rules are still written for the Archil event.

## The event
- **Personal Agents Hackathon** by tokens&, held at AWS Builder Loft, San Francisco, Fri Nov 20, 2026. In person only.
- Pages: https://tokensand.com/personalagenthack (main) and https://luma.com/personalagenthack
- Discord: https://bit.ly/discord-17
- Teams of 2–4, one project per team. **"Build your project during the event."** Don't present pre-built work.

### Schedule (PT)
| Time | What |
|---|---|
| 11:00 | Kickoff + hacking starts |
| 13:30 | Lunch |
| **16:30** | **Submission deadline** (hard) |
| 17:00 | Finalist demos + judging |
| 19:00 | Awards |

That leaves about 5.5 hours. Plan to have the demo working by 15:30 and to freeze at 16:00.

### The brief (verbatim)
> Build a personal agent that does something useful beyond a chat window. Pick one real task, make it work end to end, and show what your agent can do.
>
> **Challenge Statement: Build a shopping agent with an audit trail.** Build a personal agent that helps someone make a purchase or complete a shopping task. Your agent should use reliable context to make decisions, take a meaningful action, and show the information and steps behind what it did. Pick a real problem, build a working experience, and show us the result.

From the Luma page:
> Personal agents can do far more than their demos show. Booking a flight or planning a trip? That's stuff you'd happily do yourself. The web is going agent-native, but most agents are still stuck inside chat apps. We think a personal agent should be its own category. Think beyond the problems in SF. And more importantly build a personal agent that can compete with the current one's.

**What this means for us:**
1. It's a **shopping or purchase task**, and it has to do something real (cart, order, claim, return, email). A recommendation alone doesn't count.
2. The **audit trail is the product.** Every decision should show what source it relied on, which step produced it, and why.
3. **Not a chat app.** The agent should run on its own (triggered by an email, a receipt, a price change or a schedule) and only show up when it needs the person.
4. **Not an SF problem.** Skip trip planners, restaurant bookers and generic gift finders. Pick a real person somewhere else with a real cost.

### Submission (via the tokens& form at /personalagenthack/submit, sign-in required)
- A GitHub repo reviewers can access. **This repo is private right now; make it public before 16:30.**
- A short demo video with a shareable link (length not stated; aim for about 2–3 minutes)
- What we built and which tools we used
- Team names and contact emails
- A working website and a screenshot are optional but welcome

### Judging criteria: **unknown** (not published)
Past tokens& events used five equal criteria: idea, technical implementation, sponsor tool use (sometimes "use at least 3"), the demo, and autonomy ("acts on real-time data without manual intervention"). Assume the same until told otherwise.

## Prizes (all sponsor "Best Use" prizes; no overall prize listed)
| Sponsor | Prize | What they want |
|---|---|---|
| **Senso.ai** | **1st 10k credits, 2nd 5k, 3rd 1k** | A shopping agent using Senso's Context Layer: show the context, the action and the decision trail. This is the event's own challenge, written as a prize. |
| Amplitude + Statsig | $1,000 / $500 | Agent analytics, feature flags, experiments |
| Superlinked (SIE Serverless) | Two prizes, each $500 cash + $500 credits | "Best Personal Agent Harness" and "Best Technical Build" |
| Guild AI | 100M / 50M / 25M tokens | "Most Interesting Use of Agents" |
| Airbyte | $1,000 / $500 / $250 Visa | Context layer, 700+ data connectors |
| Arcee AI | $500 credits + $250 merch / … | "Most Impressive Use of the Pareto Frontier" (open models, cost vs quality) |
| Cognee | $500 cash + $500 credits / … | Agent memory |
| Firedrill | $500 Visa + sub + 40k credits / … | Agent simulation |
| SingleStore | $1,000 / $750 / $500 gift cards | Real-time DB |
| Persona | $250 Keychron gift card each + swag | Verify the person behind the agent |

One project can be submitted for several sponsor prizes. Pick **2–3 sponsors that are actually load-bearing**. A judge can tell when a tool was bolted on.

## Sponsor quick-start (from their docs; verify before relying on it)
- **Senso**: a knowledge base with an MCP server. `claude mcp add --transport http --scope user senso https://apiv2.senso.ai/mcp` then `claude mcp login senso`. REST base `https://apiv2.senso.ai/api/v1`, header `X-API-Key` (keys start `tgr_`), env `SENSO_API_KEY`. CLI: `npm i -g @senso-ai/cli` (Node 22.12+). Main tools: `senso_search`, `senso_get_doc`, `senso_create_doc`, and **`senso_check_text`**, which fact-checks a draft against the KB and returns verified, conflict, unsupported or not_verifiable with passages. Fact checks cost no credits. That check is a ready-made audit artifact. Hackathon setup doc (Google Doc, couldn't be fetched automatically; open it in a browser): https://docs.google.com/document/d/17tFdnTaLQAFhe1_k0k1Ve_kLov9HHO7pyenw0X8Pv04/edit
- **Firedrill**: a simulation sandbox. The agent runs against fake Gmail, Slack, Stripe, GitHub and more, and you get a drill report of every tool call. Sign up at https://app.firedrill.run. **Event code `TOKENSAND`** (Billing > Event code) gives 1,500 credits, no card needed. `npm i -g firedrill-run@latest` (v3.0.5+). Quickstart: https://firedrill.run/hacker-docs. What judges want to see: an outcome you can check inside the tool (e.g. "the email was drafted, not sent").
- **Guild AI**: an agent control plane with workspaces, server-side credentials, spend budgets and per-session event logs. That makes it a natural audit trail. `npm i -g @guildai/cli`, `guild auth login`, SDK `@guildai/agents-sdk`. The quickstart may say "talk to sales", so access could take time. Docs: https://docs.guild.ai/
- **Cognee**: open-source memory that builds a knowledge graph; runs locally with `LLM_API_KEY`. Calls are `remember` / `recall` / `forget`. Cookbook: https://docs.cognee.ai/cookbooks/personalized-email. Good for remembering preferences, budget and past orders.
- **Superlinked SIE**: hosted small models for embeddings, reranking and field extraction. `pip install sie-sdk`, key `sk-sie-…`, base `https://api.superlinked.com`. Reranker `Qwen/Qwen3-Reranker-4B`. Good for ranking candidates with visible scores.
- **Arcee**: open models behind an OpenAI-compatible API, `base_url="https://api.arcee.ai/api/v1"`, key from platform.arcee.ai. Responses include `reasoning_content`, which can go straight into the trail.
- **Airbyte**: read-only MCP over connected sources: `claude mcp add --transport http airbyte https://mcp.airbyte.com/mcp`. Needs Airbyte Cloud (14-day trial) plus a connected source. Only worth it if we already have the data source.
- **SingleStore**: SQL plus a vector column type. `pip install singlestoredb`. Could store the audit log as rows.
- **Persona (Know Your Agent)**: access is sales-gated. If we use the idea, **mock it and say so clearly** ("verify the person before buys over $X").
- **Amplitude / Statsig**: event analytics and feature flags; sign up at amplitude.com/get-started and console.statsig.com.

## Judges (20)
Meta (eng manager), Cursor (engineer), Plato (CEO), Intuit (staff eng), GAP Inc (Sr staff eng, **retail**), Ocular AI (CEO, YC W24), **Broccoli CEO + CTO** (AI voice agents for plumbers and HVAC, i.e. non-SF small businesses), plus sponsor staff: Amplitude, Superlinked ×2 (incl. founder Daniel Svonava), Arcee ×2, Cognee, Guild.ai, Airbyte, Firedrill (CEO), Persona, SingleStore ×2.
Most of them are sponsor people, so real use of their tool counts for a lot.

## How we work (lessons from our last hackathons, which we lost)
- **Start with one specific person and one measurable problem**, e.g. "Maria, a home-care aide in Fresno, loses $X/month because…". Winners lead with that and show real before/after numbers.
- **Don't overclaim.** No faked API calls, hardcoded "learning" or invented numbers. If something is mocked, label it in the UI and in the pitch. Every claim in the pitch must come from a real run.
- **Only decisions written in `CONTRACT.md` count.** Claude agents don't get to declare something "locked".
- **Scope to half of what feels possible.** Last time we planned about 2× what we finished.
- **Get the UI and demo onto main early** so judges actually see them. Get one end-to-end path working before polishing anything.
- **Check setup first:** API keys, repo access, Node 22+, Python. Do it in the first 15 minutes.
- **Never commit secrets.** Keys go in `.env` (gitignored).

## Ideas (earlier shortlist)
See `IDEAS.md`.
