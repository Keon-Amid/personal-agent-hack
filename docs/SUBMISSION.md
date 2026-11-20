# Submission draft (for the tokens& form) — EDIT BEFORE SENDING

Draft by alistair's agent, 15:30. Every number below comes from a saved run file in this repo (named next to it).
**TO DECIDE (humans):** the person, the one real number, the project name. Lines marked ✏️ need you.

---

## Project name ✏️
Room Furnisher *(working name)*

## One-line pitch ✏️
Scan or photograph your room; an agent picks real IKEA furniture that **provably fits**, checks every claim with Senso,
and hands you a cart you approve, with the math and sources behind every pick.

## The person and the problem ✏️
*(pick one and add a real number, e.g. what a return of furniture that doesn't fit costs)*
- Option: a renter furnishing a small living room on a fixed budget, ordering online without a tape measure handy.
- Option: a college student furnishing a dorm with published room sizes.

## What we built
A personal shopping agent that runs on its own, not a chat window:
1. **Room in:** an iPhone LiDAR scan (Polycam Floorplan / Apple RoomPlan) or a photo plus a few measurements.
   Our own room was scanned today: L-shaped, 190.6 × 139.7 in interior, 32 × 97 in door, plus the furniture already
   in it (`assets/room_scan_roomplan.glb`, `fit/scan.py`).
2. **Agent:** Claude (headless Claude Code) calls our tools. The tools enforce the rules, the model chooses the order
   and writes the explanations (`agent/`).
3. **Real catalog:** 102 real IKEA US products (dimensions, every shipping box, price, rating, photos) read from IKEA's
   pages, nothing typed by hand (`data/products.json`, `data/fetch_ikea.py`).
4. **Fit is proven, not guessed:** every pick is checked against the wall, the 36 in walkway, the doorway (every box)
   and, in the scanned room, the existing furniture and door swing (`fit/`). Estimated measurements carry ± error;
   "too close to call" asks the person to measure that one thing.
5. **Audit trail:** every step is a record with its source (fit math, Superlinked score, Senso verdict, Claude's or
   Arcee's reason) shown in the UI timeline; rejected items show as red ghosts with the math.
6. **Action:** a real cart of IKEA links with totals, approved by the person. Checkout is MOCKED (no purchase is made).
7. **Budget is enforced by the tools**, not the prompt: picks can't exceed it and the cart refuses anything that would.

### Real results (from run files)
| Run | What happened | File |
|---|---|---|
| Live agent run, 88 in wall | 5 slots furnished, \$1,027.97 cart, Senso verified 42/46 claims, 0 conflicts; rugs rejected on real numbers ("94 in + 2 × 6 in margin = 106 in > 88 in"); 65 audit records; ~2 min | `contracts/plan.live.json` |
| Quiz-driven live run | Style from a 5-question quiz → \$1,017.97 cart, 46/47 verified | `contracts/plan.quiz_live.json` |
| Our scanned room | 5 slots in ~3 min, \$1,407.97, 55/58 verified, 75 audit records | `contracts/plan.room_scan.json` |
| Demo-room fixture | ARNÄSVALL armchair rejected: "box 32.5 in > 30 in door"; KIVIK "89.4 in ≈ 88 in ±4" → measure first | `contracts/plan.example.json` |

### Guardrails, tested live: 6 of 6 pass (`contracts/eval.json`, `scripts/eval_guardrails.py`)
Each scenario runs the real tools on a fresh plan with live Superlinked + Senso (no LLM, so the rules alone are tested):
| Scenario | What the tools did |
|---|---|
| Sofa too wide for the wall | KIVIK and UPPLAND rejected: "width 89.75 in > 88 in" |
| Box too big for the door | ARNÄSVALL rejected: "box smallest side 32.5 in > 24 in" |
| Over budget | Per-item $200 cap: picked GLOSTAD at $199, pricier sofas skipped |
| Senso catches a wrong fact | SALTSJÖBADEN claimed 92.75 in wide (true: 80.75 in) → Senso conflict |
| Cart without a Senso check | Refused: "PERSBOL … has no Senso check: call senso_check first" |
| A good pick passes | SALTSJÖBADEN, 80.75 in ≤ 88 in, verified, added to the cart |

Plus the live run in the app (88 in wall, $1,000 budget): GULLVALLA and SALTSJÖBADEN rejected over budget
("$449 > $400"), STOCKHOLM rejected "95.625 in > 88 in", cart \$717.97, 96 audit records, ~3 min.

## Sponsor tools (exact use)
- **Senso (context layer):** all 102 products (every dimension, box, price) plus the room rules are loaded as Senso
  knowledge-base documents (`agent/senso_kb.py`). Before any item can go in the cart, its claims are fact-checked with
  Senso's `evals/text`; `cart_add` refuses an item without a verified check. We found Senso only scores claims phrased
  as the org's own ("Our catalog lists … IKEA article …"), so `fit/claims.py` writes them that way: GLOSTAD 10/10 and
  JÄRNVÄG 8/8 claims grounded; a wrong width came back `contradicts_kb`.
- **Superlinked (SIE serverless):** SigLIP embeddings of every product photo; room style detected zero-shot from the
  room photo; Qwen3-Reranker-4B over IKEA's product text; the two rankings fused (`data/sie.py`). The agent walks that
  ranking and picks the first item that fits (`fit/pick.py`), so the top style match being rejected for fit is visible
  in the trail. One room photo → 5 slots ranked in 4.7 s.
- **Arcee:** open-weight models served by Arcee write an alternative one-line why for each pick from the tools' facts
  only, with cost and latency recorded (`agent/arcee.py`). Cost/quality frontier over 6 models × 5 real picks
  (`contracts/arcee_pareto.json`): **zai-org/glm-5.3-flash at \$0.00023 per item, 2.4 s, no invented numbers in 5/5**,
  vs moonshotai/kimi-k3 at \$0.0083 per item (36× the cost), 9.1 s.
- *(Amplitude: ✏️ only if Keon's events land.)*

## Other tools
Claude (agent reasoning, Claude Code headless + MCP server so anyone's Claude can use the tools), React + Vite + React
Three Fiber, FastAPI, Polycam (RoomPlan scan), Hyper3D Rodin (3D models from IKEA photos, 25 models), Blender (renders).

## Honest limits ✏️ (say these out loud)
- Checkout is MOCKED: the cart is IKEA links; nothing is bought.
- IKEA US shows no delivery dates, so none are shown.
- 3D models are AI-generated from IKEA photos and stretched to the listed size; rugs are flat boxes.
- Arcee's "quality" score is judge-free (no invented numbers, names price and fit); it penalises correct arithmetic.

## Team ✏️
Keon Amid, Brendan, Alistair Clark, Kyle Coogan — emails: ✏️

## Links ✏️
- Repo: https://github.com/Keon-Amid/personal-agent-hack (must be public)
- Demo video: ✏️
