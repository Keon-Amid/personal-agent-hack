// Page scripts for a real IKEA bag, run in a browser tab on ikea.com/us/en
// (Playwright page.evaluate, or Claude in Chrome's javascript tool).
// Tested live 2026-11-20 with KALLAX x2, LACK x3, BILLY x1: see docs/ikea-cart-browser.md.
//
// Flow per item:  navigate https://www.ikea.com/us/en/p/-<itemNo>/  (redirects to the product page)
//                 -> await addToBag(qty)
// Then:           navigate https://www.ikea.com/us/en/shoppingcart/ -> await readBag()
//                 -> agent/bag_reconcile.py reconcile(selection, bag)
// Adding an item already in the bag INCREASES its quantity: use bag_reconcile.add_plan first.

async function addToBag(qty) {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  let inc, add;
  for (let i = 0; i < 20 && !(inc && add); i++) {
    inc = document.querySelector('button[aria-label="Increase quantity"]');
    // A page with a "Complete with" add-on has two "Add to bag" buttons and the add-on's comes first.
    // The product's own button is the full-width one (pipf-btn--fluid); else take the last.
    const adds = [...document.querySelectorAll("button")].filter((b) => b.innerText.trim() === "Add to bag");
    add = adds.find((b) => /fluid/.test(b.className)) || adds[adds.length - 1];
    if (!(inc && add)) await sleep(500);
  }
  if (!add) return { ok: false, error: "add button not found (out of stock or page changed)", url: location.href };
  for (let i = 1; i < qty; i++) { inc.click(); await sleep(250); }
  const qIn = document.querySelector('input[aria-label="Quantity input value"]');
  const qtySet = qIn ? Number(qIn.value) : null;
  if (qtySet !== qty) return { ok: false, error: `quantity box shows ${qtySet}, wanted ${qty}`, url: location.pathname };
  add.click();
  await sleep(2500);
  const badge = (document.querySelector('a[href*="shoppingcart"]') || {}).innerText || "";
  return { ok: true, url: location.pathname, qtySet, bagBadge: badge };
}

async function readBag() {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  for (let i = 0; i < 20 && !document.querySelector('input[aria-label^="Enter quantity of"]'); i++) await sleep(500);
  await sleep(800);
  const lines = [...document.querySelectorAll('input[aria-label^="Enter quantity of"]')].map((inp) => {
    let el = inp;
    while (el && !(el.innerText || "").match(/\d{3}\.\d{3}\.\d{2}/)) el = el.parentElement;
    const itemNo = ((el && el.innerText.match(/(\d{3}\.\d{3}\.\d{2})/)) || [])[1] || null;
    let box = inp;
    for (let i = 0; i < 8; i++) { box = box.parentElement; if ((box.innerText.match(/\$/g) || []).length >= 2) break; }
    const lineTotal = ((box.innerText.match(/\$\s?([\d,]+\.\d{2})/)) || [])[1] || null; // first $ on the line = line total
    return { itemNo, name: inp.getAttribute("aria-label").replace("Enter quantity of ", ""), qty: Number(inp.value), lineTotal };
  });
  const productsTotal = (document.body.innerText.match(/Products\s*\n?\s*\$([\d,.]+)/) || [])[1] || null;
  return { lines, productsTotal };
}
