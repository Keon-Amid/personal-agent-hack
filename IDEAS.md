# Ideas (nothing decided until it's in CONTRACT.md)

The challenge says **shopping agent with an audit trail**: real context, a real action, and visible steps behind each decision. Past winners at this organizer and similar events share a few traits. They lead with **one specific person who isn't in SF**, an **action you can check** (an email sent, a claim filed, a cart built), and **a number** (dollars recovered, errors caught). They lose when they're a chat box with a recommendation at the end. Past tokens& winners we shouldn't copy: FDA recall alerts, scam-inbox shield, pharmacy price finder, senior check-in calls, wildfire family alerts.

## Real winners these ideas are based on
- **people-coming-over** (Creators Corner, the same organizers, Multimodal Agents Hack 2025, **grand prize + 4 awards**): photograph your room, get furniture suggestions, and the agent **completes the checkout**. It's the closest precedent to today's shopping brief: it ran the full loop to a real purchase and made a sponsor tool (AgentQL) the step that does the buying. https://www.agentql.com/blog/2025-multimodal-agents-hackathon
- **Dealwise** (ElevenLabs hackathon, SF 1st): phones local businesses for quotes and books the appointment. It came from the founders' own couch-cleaning hassle. **Procuro** (NYC 2nd) phones suppliers to chase late parts. A live call on stage is the most common winning demo moment.
- **Smooth Operator** (Berkeley LLM Agents, 1st): negotiates moving quotes over real voice calls.
- **CrossBeam** (Anthropic Opus 4.6 hackathon, 1st): permit corrections, pitched with a real number (90%+ of CA permits are rejected the first time) and a city considering using it.
- **MaestrIA** (Anthropic Opus 4.7, prize): a 20-year-old in Chiloé, Chile. Photo of a home-repair problem → cost estimate → tradespeople → drafted WhatsApp. It showed a measured eval going from 74% to 81% on 12 real cases. A "beyond SF" user plus numbers.
- **Digital Guardian** (Cursor Hamburg, 1st + fan favorite): blocks scam calls to elderly relatives, and can only ever neutralize, monitor or escalate. **CallFlow** and **Second Voice** also won with a visible approval step. Judges reward autonomy that has guardrails.
- **What lost:** do-anything concierges (the Retell "personal phone concierge" lost to a narrow property-maintenance dispatcher), trip planners, email and meeting summarizers, daily planners, job-application bots.

**Takeaways:** finish the job with a real transaction, use real data and show a number, pick a specific person outside SF, show a visible trust boundary, and make sponsor tools do the work that matters.

Each idea lists the person, what triggers it, the action it takes, what goes in the audit trail, which sponsors carry real weight, and the demo moment.

---

## 1. Clawback: the agent that gets your money back after you buy ⭐ my pick
- **Person:** a parent in Ohio who buys household stuff online and never claims price drops, missed return windows or "arrived damaged" refunds.
- **Trigger:** a receipt lands in email. No chat needed.
- **What it does:** reads the receipt, remembers the order, and checks the price and the store's policy every day. When money is owed (price-adjustment window, return window about to close, late-delivery credit) it **drafts and sends the claim** quoting the exact policy line.
- **Audit trail:** for each claim, the receipt line, the store-policy passage (Senso KB of real Target, Walmart, Best Buy and Amazon policies), Senso's `check_text` verdict on the claim email before it sends, and the dollar amount.
- **Sponsors:** Senso (policy KB + fact-check gate), Firedrill (run it against simulated Gmail first, then show the drill report), Cognee (memory of orders and preferences).
- **Demo moment:** forward 5 real receipts from our own inboxes, and the timeline shows "$47.18 recoverable, 3 claims drafted, 1 blocked because the policy doesn't support it." The blocked one is our negative control.
- **Why it can win:** money on screen, runs on its own, the audit trail is the core of it, and it's not an SF problem.

## 2. Right Part: buy the correct replacement part the first time
- **Person:** a homeowner in rural Georgia whose dryer died, or a handyman. Wrong parts mean a week of returns.
- **Trigger:** a photo of the appliance's model sticker.
- **What it does:** extracts the model number, matches the failing part against manufacturer compatibility data, ranks real listings (genuine vs. "fits", price, shipping), and **builds the cart**.
- **Audit trail:** the sticker crop, the compatibility evidence for each part, why each listing ranked where it did.
- **Sponsors:** Superlinked (extraction + reranking with scores shown), Senso (KB of parts compatibility), Arcee (cheap open model; fits "Pareto frontier").
- **Demo moment:** a photo of a real dishwasher label goes in, and the correct part number comes out, along with "this cheaper one does NOT fit, here's why."
- **Judge fit:** Broccoli (trades/HVAC) and GAP (retail).

## 3. WIC Cart: grocery shopping for a family on WIC/SNAP
- **Person:** a mom in Bakersfield on WIC. Each state has a strict approved-product list (brand, size, ounces) and cashiers reject items at checkout all the time.
- **Trigger:** her monthly benefit balance plus a meal plan or shopping list.
- **What it does:** builds a cart where every item is WIC-approved for her state and fits the benefit balance. It flags what to pay for separately and outputs a store pickup order.
- **Audit trail:** each item mapped to its line in the state's approved product list (a real public PDF in Senso), the benefit math, rejected substitutions.
- **Sponsors:** Senso, Cognee (household preferences, allergies), SingleStore (product/APL lookup).
- **Demo moment:** "Cheerios 18 oz — rejected, CA only allows 12 oz, swapped." That's very concrete and nobody in SF has thought about it.
- **Risk:** placing a real order needs a retailer account, so the action might stop at an exportable cart.

## 4. Proxy Shopper: an aging parent's purchases, with permission and receipts
- **Person:** an adult child managing a dad's supplies (meds, incontinence products, groceries) from another state.
- **What it does:** reorders on a schedule, but only within limits the family set (budget, approved items). Anything new or over $X goes to the dad, who confirms himself (the Persona-style "verify the human behind the agent" step).
- **Audit trail:** a weekly ledger the whole family can see: what was bought, why, and who approved it.
- **Sponsors:** Guild (credential policies + spend budgets + event log), Persona (mocked unless we get access, labeled), Cognee.
- **Risk:** the "senior check-in calls" project already won here once. Needs a sharp angle.

## 5. Trades restock agent (aimed at the Broccoli judges)
- **Person:** a solo plumber in Sacramento who loses an hour a day calling supply houses.
- **What it does:** from a job note ("50 gal gas water heater, 3/4 flex, expansion tank"), it sources from 3 supply houses, checks local code requirements, and places or holds the order against the job.
- **Audit trail:** the spec → code rule → part → price, tied to the job for invoicing.
- **Risk:** supply-house data is hard to get live. We'd need real catalogs.

---

## Twist: it picks up the phone
Several of the winners above won with a live call. If a store only gives price adjustments or refunds over the phone (Clawback) or a supply house won't quote online (Right Part, Trades), the agent calls, and the transcript goes into the audit trail. It's high risk and high reward: only add it after the main path works.

## Twist we can add to any of these
**The agent rehearses before it acts.** Every claim, order or email first runs in a Firedrill simulation. Only the actions that pass go live, and the drill report becomes part of the audit trail. That makes the Firedrill prize real and gives the demo a strong "safe autonomy" story.

## Quick pick
If we have real receipts in our inboxes (we all do), **Clawback** gives the fastest real demo with real numbers. **WIC Cart** has the strongest story but the action is harder to make real. Decide in the next 15 minutes, write it in CONTRACT.md, and go.
