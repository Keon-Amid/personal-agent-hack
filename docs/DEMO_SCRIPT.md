# Fits: the demo script

Spoken word for word. **[DO]** = what the driver clicks. Times are cumulative (stage version ≈ 3:00).
Every number is from a run file or a live run today (sources at the bottom). ✏️ = humans fill before going on.
Run sheet, roles, preflight and fallbacks: `docs/DEMO.md`.

## Short script (3:00, use this one)
| Time | Do | Say |
|---|---|---|
| 0:00 | Start screen | Furniture bought online often doesn't fit. You find out when it arrives. **Fits** is a shopping agent that proves furniture fits your room before you buy, then fills your real IKEA bag. |
| 0:15 | QR → send scan → room opens | We scanned this room with an iPhone: every wall, the door, the furniture already here. 190.6 by 139.7 inches, door 32 inches, accurate to one inch. |
| 0:35 | Style → budget 900 → Furnish | I enter a style and a budget of $900, then press Furnish. That's all I do. |
| 0:50 | Trail streams | Claude runs on its own and calls our tools one step at a time. The tools hold the rules: the agent cannot add an item that doesn't fit, isn't verified, or is over budget. Every step appears on the left with its source. |
| 1:10 | "Ranked the catalog by style" | Superlinked ranks 102 real IKEA products by style. It compares product photos and reads IKEA's descriptions; the two rankings are combined. |
| 1:25 | Red "Rejected" row → click sofa | This sofa was rejected: over budget, with the reason shown. The chosen sofa is 71.6 inches wide on a 190.6-inch wall. Its shipping box is 13.75 inches against a 32-inch door. We check every box. |
| 1:45 | "Verified by Senso" + claims | Senso checks every claim against our knowledge base of product specs and room rules. Width, wall rule, walkway rule: verified. No item enters the cart without this check. |
| 2:05 | Arcee explanation | An Arcee open model writes a second explanation. It costs $0.00023 per item. |
| 2:15 | Review the cart → Approve | Five pieces, $887.97, under budget. On approval, it re-checks every price live on IKEA. |
| 2:25 | `scripts/ikea_checkout.py <plan_id>` → back to cart | Now it adds all five items to a real IKEA bag on ikea.com and reads it back: IKEA's total is $887.97. It matches. You pay. The agent never does. |
| 2:45 | Close | We tested the rules: too wide, too big for the door, over budget, a false fact. All blocked. Six of six. **Fits.** Furniture that's proven to fit, with a reason for every choice. |

---

## Long version

## 0:00 — Cold open (no slides, the app is already on the start screen)

> Raise your hand if you've ever bought furniture online… and it didn't fit.
>
> The couch that's three inches too wide for the wall. The wardrobe that can't get through the door.
> You don't find out until the box is in your hallway.
>
> ✏️ *[Person + one real number. Suggested: "Meet a renter furnishing a living room on a $900 budget,
> with no tape measure and no second chance."]*
>
> We built **Fits**: a personal shopping agent that doesn't *guess* that furniture fits.
> It **proves** it, line by line, and then it fills your real IKEA bag.

## 0:20 — The room is real

**[DO]** Scan the QR code with the phone → pick the Polycam scan → the room opens on the laptop.

> This is the room we're standing in. We scanned it with an iPhone this morning.
> Apple RoomPlan gives us every wall, the door, even the table and chairs already here.
> Look at the header: **190.6 by 139.7 inches, door 32 inches, plus or minus one.**
> Every decision from here on is measured against *this* room. Not a guess. Not a template.

## 0:40 — Hand it to the agent

**[DO]** Type *"warm minimal living room, light oak and linen, easy to clean"* → **Set a budget: 900** → **Furnish**.

> I give it a style and a budget. That's it. No chatbot, no back-and-forth.
>
> Under the hood, Claude is running headless with its own set of tools, and here's the key idea:
> **the tools enforce the rules, not the prompt.** The model *can't* put something in the cart that
> doesn't fit, isn't verified, or blows the budget. The tools refuse.

## 0:55 — Watch it think (audit trail streams, furniture appears in 3D)

**[DO]** Point at the left panel as rows stream in.

> Every row on the left is a decision with its source. Watch:
>
> **"Ranked the catalog by style."** That's **Superlinked**. Two signals: SigLIP compares the *look*
> of 102 real IKEA products to the style, and a Qwen3 reranker reads IKEA's own descriptions.
> Fused by rank, so neither score can bully the other.
>
> **[DO]** Point at the red row.
>
> And there, in red: **"Rejected: over budget."** The agent's favorite pick, rejected *before* you spent
> a dollar, with the math written right next to it.

## 1:20 — Open a piece: the receipts

**[DO]** Click the **sofa** in the 3D room. Dimension tags appear; the panel opens.

> Click any piece and you get the receipts.
>
> **71.6 inches wide, against a 190.6-inch wall. Fits.** Thirty-six inches of walkway kept clear in front.
> And this one's my favorite: **the shipping box**. Its smallest side is 13.75 inches against our
> 32-inch door. We check *every box*, because the sofa doesn't walk in assembled.
>
> **[DO]** Point at the green **Verified by Senso** badge, scroll to the claims.
>
> Then **Senso** fact-checks every claim against our knowledge base: 102 product spec sheets
> plus our room rules. Width: verified. Wall rule: verified. Walkway rule: verified.
> Nothing goes into the cart without a verified Senso check, and here's the check ID, in the trail.
>
> **[DO]** Point at the Arcee explanation (if shown).
>
> And this line is written by an **Arcee** open model. We benchmarked six models on real picks.
> The winner costs **two hundredths of a cent per item**, in **2.4 seconds**, with **zero invented numbers**.

## 1:55 — The cart and the live check

**[DO]** The run finishes: *5 pieces, $887.97*. Click **Review the cart** → **Approve 5 pieces**.

> Five pieces, **$887.97**, twelve dollars under budget, every piece fits, every claim verified.
>
> When I hit approve, it doesn't trust its own catalog. It goes back to **IKEA's live pages**
> and re-reads every price. If anything moved, it stops and tells me.

## 2:10 — The real action

**[DO]** Operator runs `scripts/ikea_checkout.py <plan_id>`. A Chrome window opens and fills the IKEA bag.

> Now the part every shopping demo fakes. This is not a mock store.
> That's **ikea.com**. The agent is adding all five pieces to a **real IKEA bag**, right now.
>
> **[DO]** Wait for the window to land on the bag. Back to the app's cart.
>
> Then it reads the bag back and checks it against what it promised:
> **five items, IKEA's own total $887.97. Matches. To the cent.**
> And it stops right there. You're at checkout. You press pay. The agent never touches your money.

## 2:40 — Proof it can't be fooled (close)

> We didn't just test the happy path. We attacked it.
> A sofa too wide for the wall: blocked. A box too big for the door: blocked. Over budget: blocked.
> We fed Senso a **wrong width**, and it came back **conflict**.
> **Six for six**, from a real run, in the repo.
>
> And when our own checkout failed earlier today, adding three items out of five,
> **it said so**, in red, in the trail, then fixed it and passed.
>
> **Fits.** Scan your room. Get furniture that's *proven* to fit.
> The receipts for every decision. And a real bag waiting at checkout.

---

## 2:30 video voice-over (Kyle: record the screen to this)
Same beats, tighter. Cut the cold-open hand-raise; open on the scanned room.
1. (0:00) "Online furniture is bought blind. Fits proves it fits before you buy." Scanned room, header numbers.
2. (0:15) Style + $900 → Furnish. "No chatbot. The tools enforce the rules."
3. (0:30) Trail streams: Superlinked rank; red "Rejected: over budget".
4. (0:55) Sofa panel: wall math, box-through-door math, Senso verified, Arcee why + cost.
5. (1:30) Cart $887.97 → Approve → "live IKEA prices re-checked".
6. (1:45) Chrome fills the real IKEA bag → "IKEA's total $887.97 matches."
7. (2:10) "6/6 guardrails; a wrong width gets caught. Fits."

## 30-second version (hallway / judge walking by)
> Fits is a shopping agent for furniture that has to fit. Scan your room with an iPhone. The agent
> picks real IKEA pieces, proves each one fits the walls, the walkway and the door, down to the shipping box.
> Senso fact-checks every claim before it can enter the cart. Then it fills your real IKEA bag
> and confirms IKEA's total matches what it promised, to the cent. You just pay.

## Lines for specific judges
- **Senso:** "Senso is the gate, not decoration. `cart_add` refuses any item without a verified Senso check,
  and a wrong width comes back `conflict`. The check ID is in every audit record."
- **Superlinked (2 judges, incl. the founder):** "Two Superlinked signals, image-to-image SigLIP and the
  Qwen3-Reranker-4B on IKEA text, fused with reciprocal rank fusion, k=60. Ranks and scores are on every card.
  A swap reuses the cached ranking, so it costs zero extra calls."
- **Arcee (2 judges):** "We measured the Pareto frontier: six models on five real picks, cost, latency and
  grounding. glm-5.3-flash at $0.00023 per item, 0 invented numbers. It's in `contracts/arcee_pareto.json`."
- **Retail (GAP):** "IKEA's own total equals our cart. The live price check runs before approval."
- **Engineers (Cursor, Meta, Intuit):** "The model orders the steps; deterministic tools hold the rules.
  159 tests, plus a 6-scenario guardrail eval you can rerun: `scripts/eval_guardrails.py`."

## Don't say (it isn't true)
- "It buys it for you." → It fills the bag; **you** pay.
- "Any room." → **Living rooms** today; the bedroom catalog and rules are loaded, the mode is next.
- "Accurate from a photo." → A photo is rough (±18 in in our test); the **scan** is ±1 in.
- Any statistic about furniture returns unless someone has a source for it.

## Sources for every number
| Claim | Source |
|---|---|
| 190.6 × 139.7 in, door 32 ±1 in | `fit/scan.py` on `assets/room_scan_roomplan.glb` |
| 102 real IKEA products, every shipping box | `data/products.json` (`packages_in` on all 102) |
| SigLIP so400m + Qwen3-Reranker-4B, RRF k=60 | `data/sie.py`, `data/style_embeddings.json` |
| Senso KB: 104 docs (products + room rules) | `data/senso_index.json` |
| $887.97 cart, 45 claims verified, sofa 71.625 in, box 13.75 in | live plan `739e77ac7237` (15:50) |
| IKEA bag total $887.97 = cart, PASS (first try 3/5, FAIL) | live plan `739e77ac7237` audit, `docs/ikea-cart-browser.md` |
| 6/6 guardrails, wrong width → conflict | `contracts/eval.json` |
| Arcee: 6 models, $0.00023/item, 2.4 s, 0 invented numbers | `contracts/arcee_pareto.json` |
| 159 tests | `pytest server agent data fit scripts` on main |
