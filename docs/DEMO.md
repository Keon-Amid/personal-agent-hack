# Fits: demo run sheet (finalist demo 17:00, video uses the same script)

Every screen below was clicked through live on 2026-11-20 at 15:50 (plan `739e77ac7237`, our scanned room,
$900 budget). Every number comes from a run file; the file is named next to it. ✏️ = humans decide.

## The story in one breath
✏️ *Person + one real number* (suggested: a renter furnishing a small living room online, no tape measure handy).
"Online furniture is bought blind: you find out it doesn't fit when the box won't go through the door.
Fits scans your room, lets an agent pick real IKEA pieces, **proves** each one fits and is allowed, and
leaves you at IKEA's checkout with a bag that matches what it promised, to the cent."

## Roles
| Who | Job on stage |
|---|---|
| ✏️ Driver (Keon suggested: built the UI) | Clicks through the app, tells the story |
| ✏️ Operator (Brendan suggested: built the backend) | Laptop terminal: server, checkout script, fallbacks |
| Alistair | Q&A on fit math, catalog, Senso KB, Arcee frontier |
| Kyle | Records the video from this script; Q&A on the 3D models |

## T-15 min preflight (demo laptop) - all must be green
```sh
git pull                                   # main
./scripts/dev.sh                           # server :8000 + UI :5173 (UI goes live by itself)
curl -s localhost:8000/api/health          # claude_code, superlinked_key, senso_key all true
.venv/bin/pip install -r server/requirements.txt   # includes playwright (IKEA checkout)
```
- [ ] `.env` on the demo laptop has `SENSO_API_KEY`, `SIE_API_KEY`, **`ARCEE_API_KEY` and
      `ARCEE_WHY_MODEL=zai-org/glm-5.3-flash`** (without these two, live runs show no Arcee why).
- [ ] `claude` is signed in on this laptop (headless agent uses the subscription).
- [ ] App top bar says **Live agent ready** (green dot), not replay.
- [ ] One full rehearsal today ends with the cart showing **"Your IKEA bag matches this cart"**.
- [ ] Phone (for the QR beat) on the same Wi-Fi; Polycam scan `.glb` saved on it.
- [ ] Backup tab open on a finished plan (see Fallbacks).

## Run sheet (about 3 minutes)
| # | Time | Screen / click | Say | Proof (source) | Sponsor / tech |
|---|---|---|---|---|---|
| 1 | 0:00 | Start screen "Furnish a room with things that fit" | The person and the problem (✏️) | | |
| 2 | 0:15 | Scan the **QR** with the phone, pick the Polycam `.glb` on `/upload`; the room opens. Header: **Wall 190.6 · Depth 139.7 · Door 32 ±1 in** | "We scanned this room today. Real walls, the real door, the table and chairs already here." | `assets/room_scan_roomplan.glb`, `fit/scan.py` | iPhone LiDAR / RoomPlan |
| 3 | 0:35 | Type "warm minimal living room, light oak and linen, easy to clean", **Set a budget → 900**, **Furnish** | "No chat. The agent works on its own, and the tools enforce the rules: it physically can't cart something that doesn't fit or isn't verified." | `agent/tools.py` | Claude Code headless + MCP tools |
| 4 | 0:50 | Audit trail streams; pieces appear in 3D. Point at the red row **"Rejected LILLESÄTER: over budget"** | "It says no before you spend, with the math." | live plan audit | |
| 5 | 1:05 | Point at **"Ranked the catalog by style"** rows (photo rank + text rank) | "Style is matched by image and by IKEA's own descriptions, fused." | `data/sie.py` | **Superlinked** SigLIP + Qwen3 reranker |
| 6 | 1:15 | Click the **sofa**: 3D dimension tags; badges **Fits** + **Verified by Senso 100%**; fit checks "width 71.625 in ≤ 190.6 in", "box 13.75 in ≤ 32 in door" | "Every claim about this sofa was fact-checked against our knowledge base before it was allowed in the cart." | item panel, Senso check id | **Senso** `check` |
| 7 | 1:35 | Same panel: **Arcee's why** with model, cost, latency | "An open model writes a second explanation for about two hundredths of a cent." | `contracts/arcee_pareto.json`: glm-5.3-flash $0.00023/item, 2.4 s, 0 invented numbers | **Arcee** Pareto frontier |
| 8 | 1:45 | Run done: **5 pieces, $887.97, $12.03 under budget, 45 claims verified** | | live plan | |
| 9 | 1:55 | **Review the cart → Approve 5 pieces** | "At approval it re-reads every price live from IKEA. Nothing is bought." | audit "IKEA's page still lists $449.00" | live data |
| 10 | 2:10 | Operator runs `.venv/bin/python scripts/ikea_checkout.py <plan_id>` (id is in the URL `/plan/<id>`). A Chrome window fills the **real IKEA bag** (~30 s) | "Now the meaningful action: a real IKEA bag." | `docs/ikea-cart-browser.md` | Playwright + `ikea_bag.js` |
| 11 | 2:40 | Back in the app's cart: **"Your IKEA bag matches this cart: 5 items, IKEA's own total $887.97"** | "IKEA's own total equals what the agent promised, to the cent. You just pay." | `POST /api/plan/{id}/bag` → audit | `agent/bag_reconcile.py` |
| 12 | 2:50 | Close on the proof line | "We tested the guardrails, not just the happy path: 6 of 6 scenarios, including a wrong width that Senso flags as a conflict." | `contracts/eval.json` 6/6 | Senso negative control |

**While the agent streams (beats 4–7, ~80 s) keep talking**: that wait *is* the demo. If it is slower than
90 s, click a finished piece and narrate the panel.

## Fallbacks (decide in 5 seconds, don't debug on stage)
| If | Do |
|---|---|
| Phone/QR upload fails | Start screen → **AWS Builder Loft, meeting room** (same scan, already on the laptop) |
| Live run errors or Wi-Fi dies | Same room in **replay** (the UI falls back by itself) or open `/plan/739e77ac7237` (finished, approved, bag PASS, on the laptop that ran it) |
| Checkout script fails on stage | Show the trail on `/plan/739e77ac7237`: the red "bag does not match" (first try, 3/5) then "filled and checked" PASS. Say it: "it caught its own failed action." |
| No Arcee why in the live panel | Open the replay of `plan.live` (Arcee frontier shown there) or show `contracts/arcee_pareto.json` |
| A judge asks "is it bought?" | No. Approval + bag; the person pays on ikea.com. Say it plainly. |

## Judge Q&A (short, true answers)
- **What stops the model from lying?** The tools: `pick` returns only fitting items, `cart_add` refuses anything
  without a Senso check that has a verified claim and no conflict, and over-budget items. Proof: `contracts/eval.json`.
- **Where do the dimensions come from?** IKEA's own product pages (102 products, every shipping box), read by
  `data/fetch_ikea.py`; nothing typed by hand.
- **Photo instead of a scan?** Works, but the estimate is rough (±18 in on the wall in our test), so the app asks you
  to tape-measure that one wall. The scan is ±1 in.
- **Why Senso?** Each "fits and is allowed" claim is checked against the KB of product specs + room rules; the check id
  and verdict are in the audit trail; a wrong width comes back `conflict`.
- **Why Superlinked?** Photo-to-photo SigLIP match + Qwen3 reranker on IKEA's text, fused by reciprocal rank; ranks
  and scores shown per item.
- **Why Arcee?** Cheap open model for the per-item explanation; 6 models × 5 picks measured, frontier at glm-5.3-flash.

## Honest limits (say if asked)
Living rooms only today (bedroom catalog + rules are loaded, the mode is next). Checkout ends at the IKEA bag; we never
pay. The bag lives in the Chrome window the script opens. Photo-only measurements are rough; scan or tape-measure.
