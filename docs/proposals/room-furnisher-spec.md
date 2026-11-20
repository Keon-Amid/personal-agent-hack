> **Proposal from brendan, for review. Not decided:** only `CONTRACT.md` counts. Please check it against your own research and the plan in `CONTEXT.md`, and post where they disagree.

# Room Furnisher — Hackathon Spec Sheet

Personal Agents Hackathon (tokens&, SF) · Nov 20, 2026 · @brendan

## Overview

**Pitch:** Snap 4 photos of an empty room, take a 3-question style quiz, and get 3 furnished versions side by side. Every item is checked to fit, priced, and buyable in one tap.

**How it answers the challenge** ("a shopping agent with an audit trail: reliable context, a meaningful action, the steps behind it"):

- **Reliable context:** the room's measured dimensions, our clearance rules (stored in Senso) and real product specs.
- **Meaningful action:** buy the whole room (mock checkout), or swap any item for one that fits.
- **Audit trail:** tap any item to see its price, store, delivery estimate, the fit maths, and the verdict with the governing rule quoted from Senso.

**Target tracks** (one project per team; whether one project can enter several prizes is not published, so ask in Discord at kickoff):

| Track | Prize | Why we fit |
| --- | --- | --- |
| Best Use of Senso (primary) | $10k / $5k / $1k credits | Its stated criteria (context, action, trail) map onto the fit check |
| Best Use of Amplitude or Statsig | $1,000 / $500 | The 3 variants are 3 versions of one Statsig AI config, scored by evaluators |
| Best Use of SingleStoreDB | $1,000 / $750 / $500 | Refresh is one query: vector style match plus SQL fit filter |

## Red-team review (12:45 PM)

**Verdict: still buildable, but only the smaller version below.** It is 12:39 PM, so about 3.5 hours of build time remain, not 5.5. Four assumptions in the first draft were wrong, and each is fixed in the sections below.

| # | Finding | Severity | Evidence | Fix applied |
| --- | --- | --- | --- | --- |
| 1 | The draft assumed an 11:00 start; it is now 12:39 | Critical | Clock | Roadmap re-timed; scope cut to 1 photo, a rectangle room and 30 products |
| 2 | Senso's REST API has no verify endpoint; `senso_check_text` exists only as an MCP tool with OAuth sign-in | Critical | The [quickstart](https://docs.senso.ai/docs/quickstart) lists ingest, search and search/context only; the [MCP page](https://docs.senso.ai/docs/mcp-server) lists the check tool | Our fit code decides the verdict. `POST /api/v1/org/search/context` returns the rule passage and its content id, which the tap panel cites. Calling the MCP check tool is a stretch goal |
| 3 | The fallback was circular: the parking idea also needs Senso | Critical | Spec | If Senso fails: a local rules file, drop the Senso track, and Statsig becomes primary |
| 4 | The demo's key beat could never happen: refresh only returned items that fit, so no conflict would appear | High | Spec | Refresh ranks by style and budget only; the fit check runs afterwards and shows rejected candidates |
| 5 | An LLM placing x/y coordinates is unreliable | High | Judgment | Fixed layout templates per category; the LLM picks products and writes the reasons |
| 6 | Statsig evaluator scores are not instant: online grading lands about 1 minute later, and offline runs take "a few minutes" | High | [Online eval docs](https://docs.statsig.com/agent-experimentation/online-evaluation), [offline eval docs](https://docs.statsig.com/agent-experimentation/offline-evaluation) | Compute scores in code and log them with `logEvalGrade`; open the Statsig view before the demo |
| 7 | Treating 3 styles as 3 config versions could look like misuse to a Statsig judge | Medium | [Configs docs](https://docs.statsig.com/agent-experimentation/configs): a Candidate is evaluated against Live or tested in an experiment | Pitch it as 3 stylist prompts competing. The user's pick plus the graders decide which to promote, and the demo shows the promotion |
| 8 | The catalog count was inconsistent (60 vs 36) | Medium | Spec | 30 products: 3 styles × 5 categories × 2 |
| 9 | SingleStore's Node driver is `singlestore-nodejs`, not `mysql2` | Medium | [SingleStore Node docs](https://docs.singlestore.com/cloud/developer-resources/connect-with-application-development-tools/connect-with-node-js/) | Stack updated. Free Shared edition (1 GB) and `<*>` dot-product confirmed in the [vector docs](https://docs.singlestore.com/cloud/developer-resources/functional-extensions/working-with-vector-data/) |
| 10 | The 4 photos were never used for measurement, and judges will ask why | Medium | Spec | 1 photo required (for the render), up to 4 optional |
| 11 | Senso's free credit amount isn't stated, a 402 means credits ran out, and ingest is async (202, then poll) | Medium | [Quickstart](https://docs.senso.ai/docs/quickstart) | Ingest the rules once at setup, and cache search results for the demo room |
| 12 | Gemini model: `gemini-nano-banana-2.1` takes up to 10 object images | Verified | [AI Studio image docs](https://aistudio.google.com/docs/image-generation) | One render = the room photo + up to 5 product images |
| 13 | One config can hold 1 Live plus 2 Candidate versions | Verified | [Configs docs](https://docs.statsig.com/agent-experimentation/configs) | No change |

**Still unverified:** whether one project can enter several prizes, and Senso's free credit allowance. Ask both in Discord now.

## Scope

We ship one living room, three styles and a curated catalog of 30 real products, in a rectangular room. Everything else is a stretch goal or cut.

| In (must ship) | Stretch (only if ahead at 3:00 PM) | Out (say so in the demo) |
| --- | --- | --- |
| 1 photo (up to 4) plus a rectangle: width, length, door wall and offset | 3D box room in three.js | Reconstructing a 3D room from photos |
| 2D floor plan (SVG) from the measurements | Persona check before "Buy room" | Live Amazon or Facebook Marketplace data |
| 3-question style quiz shown while the variants generate | More than one room type | Real payment |
| 3 variants generated in parallel, about 5 items each | Delivery date from a live API | Odd-shaped rooms (rectangles only) |
| Fit check in code, with the governing rule cited from Senso, for every item |  |  |
| Tap an item to see price, store, delivery, fit maths and verdict |  |  |
| Refresh an item for a same-style option that fits |  |  |
| Gemini preview render of the room for each variant |  |  |
| Mock "Buy room" cart with totals and the audit trail |  |  |

**The catalog rule:** every product is real. Each has a real link, price and dimensions, collected by hand, and the demo calls it a "curated catalog". The agent's job is choosing, fitting and justifying, not scraping.

## Architecture and stack

One Next.js (TypeScript) repo holds the app and the agent server. All sponsor calls happen server-side, so no key reaches the browser.

[embedded content: system architecture · 1 app, 1 server, 5 services]

The app calls the agent server; the server alone talks to the five services. Every LLM and tool call is wrapped so it appears as a span in Statsig.

| Part | Choice | Notes |
| --- | --- | --- |
| App and API | Next.js, TypeScript | One repo; deploy to Vercel only if time allows |
| LLM | Claude (`claude-sonnet-5-5`) via Statsig `wrapAnthropic` | Every model call becomes a traced span |
| Statsig | `@statsig/statsig-ai` + `@statsig/statsig-node-core` | Node AI SDK is v1.0; the Python one is still a beta |
| Senso | REST search/context endpoint, X-API-Key header | No REST verify endpoint; our fit code decides and Senso supplies the cited rule |
| SingleStore | Node `mysql2` driver plus the vector-data docs linked from the event page | Fallback for refresh: match on style tags, no vectors |
| Embeddings | Gemini embeddings (reuses the Gemini key) | Only needed for SingleStore vector search |
| Images | Gemini image editing on the user's photo | gemini-nano-banana-2.1; room photo plus up to 5 product images |

**Keys (in `.env`, which is in `.gitignore` from the first commit; the repo will be public to reviewers):** `STATSIG_SDK_KEY` (server secret), `STATSIG_API_KEY` (console key, for code-run evals), `ANTHROPIC_API_KEY`, `SENSO_API_KEY`, `SINGLESTORE_URL`, `GEMINI_API_KEY`.

## Team roles

Four roles with no shared files: each owns its folder and talks to the others only through the data contracts below. Put a name in each role heading at kickoff. With 3 people, D's work splits between A (renders) and C (quiz); with 2, one person takes A and B and the other C and D.

### Role A: Catalog and data (SingleStore)

**Owns:** `/data`, `/lib/catalog`, the SingleStore database, `GET /api/refresh`.

- [ ] 12:45 to 1:00: create a free Shared SingleStore cluster; connect with `singlestore-nodejs`; insert one test row.
- [ ] By 1:30: 30 real products in a shared sheet: 3 styles (Warm Minimal, Mid-Century, Cozy Eclectic) × 5 categories (sofa, rug, coffee table, accent chair, lamp) × 2. Each row has name, store, URL, price, delivery days, width/depth/height in inches, image URL and style tags. Include one deliberately oversized rug per style for the demo.
- [ ] By 2:15: `products` table seeded with a `VECTOR` embedding column.
- [ ] By 2:15: `GET /api/refresh` ranks same-category items by style similarity (`<*>` dot product) and filters by budget only. It does **not** filter by fit; B's fit check does that, so rejections show.
- [ ] By 2:15: export `catalog.json` for B.
- [ ] 2:45 to 3:45: help C wire refresh; open every product link and image once.
- [ ] 3:45 to 4:15: full test run; cache the demo room's results so the live demo cannot stall.

**Fallback:** if embeddings fail, refresh ranks by style-tag overlap. Same endpoint, no vectors. If SingleStore setup isn't done by 1:30, serve `catalog.json` from memory and drop the SingleStore track.

### Role B: Agent and sponsor integrations (Statsig, Senso, Claude)

**Owns:** `/lib/agent`, `/lib/fit`, `/lib/senso`, `/lib/statsig`, `POST /api/variants`, `POST /api/checkout`.

- [ ] 12:45 to 1:15: write the clearance rules as Senso documents (`POST /api/v1/org/kb/raw`, `X-API-Key`): 36 in walkway, keep the door-swing arc clear, rug at least 6 in from walls, sofa on the longest wall. Poll until processing is complete. These are our chosen defaults, not an external standard.
- [ ] By 1:30 (G1): `POST /api/v1/org/search/context` returns the walkway rule passage from code, AND Statsig config `room_stylist` serves 1 Live + 2 Candidate versions via `getPrompt`.
- [ ] By 2:15: fixed layout templates (sofa on the longest wall, rug centred, table on the rug, chair angled, lamp beside the sofa). Claude picks one product per slot from the catalog and writes a one-line reason. It never places coordinates.
- [ ] By 2:30: the fit module checks each placement against the walls, walkway and door arc in code. Each item gets a `FitVerdict` citing the Senso passage and content id.
- [ ] By 2:45 (G2): `POST /api/variants` runs the 3 versions in parallel with `withVersion`, all traced through `wrapAnthropic`.
- [ ] By 3:15: code graders (fit rate, within budget, style-tag consistency) logged with `logEvalGrade`; events `variant_chosen`, `item_refreshed` and `room_purchased` logged.
- [ ] By 3:30: `POST /api/checkout` returns the cart, the totals and the full trail. Open the Statsig traces view and leave it ready for the demo.

**Fallback:** if Senso misses G1, load the same rules from a local file and cite them ourselves; Statsig becomes the primary track. If Statsig's AI SDK misses G1, hard-code the 3 prompts and keep the graders and events. Calling Senso's MCP `senso_check_text` from code is a stretch goal, attempted only after G2.

### Role C: Front end and experience

**Owns:** `/app` pages and components.

- [ ] By 1:15: page shell; room form with 1 required photo (up to 4), room width and length, door wall and offset.
- [ ] By 1:30: floor-plan SVG drawn from a `Room` (rectangle, door-swing arc, scale in inches).
- [ ] By 2:30: 3-up variant grid on mock `Variant` JSON (floor plan with item rectangles plus a render slot), and the tap panel: price, store, delivery, fit maths, verdict and the quoted rule.
- [ ] By 3:15: switch to real data; refresh button that shows rejected candidates with their reason before the accepted one.
- [ ] By 3:45: cart page with totals, delivery per item, the expandable audit trail and the "Buy room" mock confirmation.
- [ ] 3:45 to 4:15: loading states only, no new features.

**Fallback:** if behind at 2:30, show one variant large plus two small thumbnails.

### Role D: Visuals, demo and submission

**Owns:** `/public`, the quiz content, `/lib/render`, the README, the demo video, the submission.

- [ ] 12:45: ask in Discord whether one project can enter several prizes, and what Senso's free credits are; post the answers to the team.
- [ ] By 1:15: photograph the demo room and tape-measure it; take a backup room too.
- [ ] By 1:45: the 3-question quiz (style images, budget band, must-have piece) on C's components.
- [ ] By 2:45: `POST /api/render` using `gemini-nano-banana-2.1` with the room photo plus up to 5 product images; 3 renders started in parallel while the quiz runs.
- [ ] 2:45 to 3:45: rehearse the demo script twice on the cached demo room; draft the README.
- [ ] By 4:00: demo video recorded and uploaded with a shareable link.
- [ ] By 4:15: README final, screenshot, repo access checked, form submitted.

**Fallback:** if Gemini placement looks wrong, label it "style preview" and keep the floor plan as the source of truth.

## Data contracts

These shapes are frozen at 1:00 PM. Commit them as `/lib/types.ts` first, so A, B and C can build against mocks in parallel. All lengths are inches, all prices US dollars.

```ts
type Room = {
  id: string;
  walls: { id: 'N' | 'E' | 'S' | 'W'; length_in: number }[];
  ceiling_in: number;
  door: { wall: 'N' | 'E' | 'S' | 'W'; offset_in: number; width_in: number; swing_in: number };
  windows: { wall: 'N' | 'E' | 'S' | 'W'; offset_in: number; width_in: number }[];
  photos: string[];            // 1 required, up to 4
  quiz: { style: string; budget_usd: number; must_have: string };
};

type Product = {
  id: string; name: string; store: string; url: string;
  price_usd: number; delivery_days: number;
  category: 'sofa' | 'rug' | 'coffee_table' | 'chair' | 'lamp' | 'shelf';
  style_tags: string[];
  width_in: number; depth_in: number; height_in: number;
  image_url: string;
};

type Placement = { product_id: string; x_in: number; y_in: number; rotation: 0 | 90 | 180 | 270; wall?: string };

type FitVerdict = {
  product_id: string;
  claim: string;               // "Fits: 84 in sofa + 36 in walkway <= 132 in wall"
  math: string;                // the arithmetic shown in the tap panel
  verdict: 'verified' | 'conflict';  // decided by our fit code
  passage?: string; senso_content_id?: string;  // rule cited from Senso search/context
};

type Variant = {
  config_version: string;      // Statsig AI config version id
  style_name: string;
  placements: Placement[];
  verdicts: FitVerdict[];
  total_usd: number;
  latest_delivery_days: number;
  render_url?: string;         // Gemini preview, filled by D
  scores?: { fit: number; budget: number; style: number };   // 0 to 1, computed in code, logged with logEvalGrade
};
```

| Endpoint | Owner | Input | Returns |
| --- | --- | --- | --- |
| `POST /api/room` | C | photos + measurements + quiz | `Room` |
| `POST /api/variants` | B | `Room` | `Variant[3]` |
| `GET /api/refresh?variant=&item=` | A | variant id + product id | up to 3 `Product` with `FitVerdict` |
| `POST /api/render` | D | `Room` + `Variant` | `{ render_url }` |
| `POST /api/checkout` | B | chosen `Variant` | cart, totals, full trail |

## Roadmap

Build time runs from 12:45 to 4:15 PM in four phases. At each gate, B calls the result out loud, and a miss triggers the named cut with no debate past five minutes.

[embedded content: roadmap · 4 lanes, 4 phases, 3 gates]

1. **12:45:** start. Repo created, `.env` gitignored, `types.ts` committed by 1:00. D asks Discord about multiple prizes and Senso credits.
2. **1:30, G1:** a Senso `search/context` call returns a rule passage from code, AND a Statsig config serves 3 versions. Miss: rules come from a local file, the Senso track is dropped, and Statsig becomes the primary track.
3. **2:45, G2:** one variant runs end to end on real data (catalog, layout, fit check, tap panel). Miss: ship one variant plus refresh.
4. **3:45, freeze:** no new features. Fix bugs and rehearse only.
5. **4:00:** demo video recorded. **4:15:** submitted. **4:30:** deadline. **5:00:** finalist demos.

Eat lunch (1:30) at the desk. Nobody leaves their lane before G2.

## Demo script

The demo runs under 2 minutes, built around one moment: refresh offers a rug, Senso says it blocks the door, and the agent swaps it. Use the same script for the video and the live finalist demo.

| Beat | Time | On screen | Say |
| --- | --- | --- | --- |
| 1. Room in | 0:00 to 0:10 | Upload 4 photos, enter measurements; the floor plan draws | "An empty room and a tape measure. That's all it needs." |
| 2. Quiz while it builds | 0:10 to 0:35 | 3 quiz questions; 3 variant cards fill in beside them | "Three designers work in parallel while you answer." |
| 3. Tap an item | 0:35 to 0:55 | Sofa panel: price, store, delivery Tuesday, fit maths, verified, with the rule quoted from Senso | "Every item shows why it's here and why it fits." |
| 4. Refresh (the moment) | 0:55 to 1:20 | Refresh the rug. The first candidate fails the fit check: **conflict** (blocks the door swing), rule quoted from Senso; the next one fits | "It checks every claim against your room's rules before it shows you anything." |
| 5. Buy and prove it | 1:20 to 1:55 | Pick a variant, Buy room, cart with totals and trail; cut to Statsig showing the 3 versions' evaluator scores and which one was chosen | "One tap buys the room, and every decision behind it is on record." |

**Rule for the refresh beat:** seed the catalog so the top-ranked rug for the demo room is too big. Then the conflict happens on every run, not by luck. Say plainly in the README that the demo room is staged.

## Submission checklist

D owns the submission and must have everything in by 4:15 PM. Items come from the event page's "What to submit" list.

- [ ] GitHub repo that reviewers can access, with `.env` absent from every commit (`git log -p | grep -i key` before making it public)
- [ ] Demo video with a shareable link, under 2 minutes, following the demo script
- [ ] Write-up: what we built and the tools we used (Senso, Statsig, SingleStore, Claude, Gemini, Next.js)
- [ ] Team names and contact emails
- [ ] Optional: working website URL and a project screenshot
- [ ] README states the catalog is curated, checkout is a mock, and the demo room is staged
- [ ] Each sponsor's use is named in the write-up with the exact feature: Statsig AI config versions + evaluators, Senso rule search, SingleStore vector + filter query

## Risks, fallbacks and open questions

The biggest risk is scope: four integrations with no slack. Every row below has an owner and a cut that saves the demo.

| Risk | Owner | Fallback |
| --- | --- | --- |
| Senso search/context not answering by 1:30 (G1) | B | Rules from a local file; drop the Senso track; Statsig becomes primary |
| Statsig AI SDK setup eats time | B | Plain configs for the 3 prompts; keep the evaluators and events |
| Embeddings or vector query fail | A | Refresh by style-tag overlap |
| Gemini puts items in the wrong place | D | Label it "style preview"; the floor plan is the source of truth |
| Variants slow (3 LLM calls plus 3 renders) | B, D | Start renders while the quiz runs; cache the demo room's results |
| Behind at 2:45 (G2) | All | One variant plus refresh |
| Video upload fails at 4:25 | D | Record by 4:00; upload to two hosts |

**Open questions to check today:**

- [ ] Can one project enter several sponsor prizes? (Not published; ask in Discord.)
- [ ] Resolved: Senso's quickstart shows no REST verify endpoint, so we use search/context.
- [ ] Statsig's included model credits are not stated, so bring our own Anthropic key.
- [ ] Resolved: the Gemini model is gemini-nano-banana-2.1.
- [ ] Amazon and Facebook Marketplace access: believed not self-serve, not verified, and not used.

**Sources** (opened during research on 2026-11-20):

- [Event page on Luma](https://luma.com/personalagenthack): agenda, team size, judges, partners
- The tokens& hackathon page (pasted by the team): tracks, prizes, submission list, "build your project during the event"
- [Statsig Agent Experimentation overview](https://docs.statsig.com/agent-experimentation/overview), [Node AI SDK](https://docs.statsig.com/agent-experimentation/node), [online evaluation](https://docs.statsig.com/agent-experimentation/online-evaluation), [offline evaluation](https://docs.statsig.com/agent-experimentation/offline-evaluation), [pricing](https://www.statsig.com/pricing)
- [Statsig: Introducing Agent Experimentation](https://statsig.com/blog/introducing-agent-experimentation) (Nov 17, 2026)
- [Senso MCP server docs](https://docs.senso.ai/docs/mcp-server): `senso_check_text` verdicts
- [Senso docs home](https://docs.senso.ai)

Added in the red-team review (opened 12:40 PM):

- [Senso quickstart](https://docs.senso.ai/docs/quickstart): REST endpoints, `X-API-Key`, async ingest, credits
- [Statsig configs](https://docs.statsig.com/agent-experimentation/configs): Live and Candidate versions
- [SingleStore Node.js driver](https://docs.singlestore.com/cloud/developer-resources/connect-with-application-development-tools/connect-with-node-js/), [vector data](https://docs.singlestore.com/cloud/developer-resources/functional-extensions/working-with-vector-data/), [free Shared edition](https://docs.singlestore.com/cloud/getting-started-with-singlestore-helios/)
- [Gemini image generation](https://aistudio.google.com/docs/image-generation): model IDs and reference-image limits
