# Catalog QA for the demo room (D2)

Demo room from `docs/ROADMAP.md`: wall 88 in, depth 150 in ±6 (estimated), door 30 × 80 in. 48 real IKEA products.
Reproduce: `fit.options(products, slot, fit.options.room(...))` per slot. Generated 2026-11-20 ~14:00 PT.

| Slot | Wall estimated (88 ±4 in) | Wall measured exactly (88 in) | Real rejections |
|---|---|---|---|
| sofa | 3 fit, **4 unsure** | 3 fit, **4 no_fit** | KIVIK ×2 (89.75 / 89.375 in), UPPLAND 88.25 in, HYLTARP 91.375 in: wider than the wall |
| armchair | 3 fit, 1 no_fit | same | ARNÄSVALL: its 32.5 in box won't fit through the 30 in door |
| coffee_table | 4 fit | same | none (all small enough) |
| rug | 4 fit, 1 unsure, 2 no_fit | 4 fit, 3 no_fit | JÄRNVÄG and ONSEVIG 7'10"×9'10" (need 106 in with 6 in margins); LOHALS 6'7"×9'10" needs 91 in |
| floor_lamp | 3 fit | same | none |

## What this means for the demo

- **With an estimated wall, the too-wide sofas are `unsure`, not `no_fit`.** That's the "measure this one wall"
  moment: the agent asks for the wall, the person types 88, and KIVIK flips to `no_fit` and gets swapped out.
  If the demo should go straight to a rejection, use an exactly measured wall (or a smaller error, e.g. ±1 in).
- Every slot has at least one product that fits. Sofa, armchair and rug have real rejections; coffee table and
  floor lamp don't (nothing in the catalog is too big for this room), so their audit trail shows no rejections.
- No numbers were changed to stage this: the four rugs added for this check are real IKEA sizes.
