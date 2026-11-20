"""Fetch real IKEA US product data (name, price, dimensions, packages) from product pages.

Stdlib only. Every number comes from the page's embedded data; nothing is typed by hand.

    python3 data/fetch_ikea.py <category> <product-url> [<category> <product-url> ...] > new.json
    python3 data/fetch_ikea.py --links <category-page-url>     # list product URLs on a category page
"""
from __future__ import annotations

import html as htmllib
import json
import re
import sys
import unicodedata
import urllib.request
from datetime import datetime, timezone

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
FRAC = {"½": .5, "¼": .25, "¾": .75, "⅛": .125, "⅜": .375, "⅝": .625, "⅞": .875}


def get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def inches(text: str) -> float | None:
    """'89 3/4 "', '37 ½ "' or "5 ' 7 \"" (feet) -> 89.75 / 37.5 / 67. None if not a length."""
    t = htmllib.unescape(text).replace('"', "").strip()
    m = re.fullmatch(r"(?:(\d+)\s*'\s*)?(\d+)?\s*(?:(\d+)/(\d+)|([½¼¾⅛⅜⅝⅞]))?", t)
    if not m or not any(m.group(k) for k in (1, 2, 3, 5)):
        return None
    feet = int(m.group(1) or 0)
    m = re.fullmatch(r"(\d+)?\s*(?:(\d+)/(\d+)|([½¼¾⅛⅜⅝⅞]))?", re.sub(r"^\d+\s*'\s*", "", t))
    v = 12.0 * feet + float(m.group(1) or 0)
    if m.group(2):
        v += int(m.group(2)) / int(m.group(3))
    if m.group(4):
        v += FRAC[m.group(4)]
    return round(v, 3)


def _json_after(h: str, key: str):
    """Parse the JSON value that follows the first occurrence of `key` in the page."""
    i = h.find(key)
    if i < 0:
        return None
    return json.JSONDecoder().raw_decode(h[i + len(key):])[0]


def product(url: str, category: str) -> dict:
    h = get(url)
    ld = None
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', h, re.S):
        try:
            d = json.loads(m.group(1), strict=False)
        except json.JSONDecodeError:
            continue
        if isinstance(d, dict) and d.get("@type") == "Product":
            ld = d
            break
    if ld is None:
        raise ValueError(f"no Product data on {url}")
    offers = ld.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0]
    price = offers.get("price") or offers.get("lowPrice")

    # The page also embeds measurements for related products. Use the block that sits next to this
    # product's own images (its URL slug), then cross-check against the Product data's width/height.
    img_slug = re.sub(r"-s?\d{8}/?$", "", url.rstrip("/").rsplit("/", 1)[1])
    block_at, dims = -1, {}
    for m in re.finditer(r'"measurements":\[\{"measure"', h):
        if f"/{img_slug}__" in h[max(0, m.start() - 3000):m.start()]:
            block_at = m.start()
            for meas in json.JSONDecoder().raw_decode(h, m.start() + len('"measurements":'))[0]:
                dims.setdefault(meas["name"].lower(), inches(meas["measure"]))
            break
    for k in ("width", "depth", "height", "length"):  # Product data wins where present
        if ld.get(k) and inches(ld[k]) is not None:
            if dims.get(k) not in (None, inches(ld[k])):
                raise ValueError(f"{k}: block {dims.get(k)} != product data {inches(ld[k])} on {url}")
            dims[k] = inches(ld[k])
    if block_at < 0 and not dims:
        raise ValueError(f"no measurements for this product on {url}")
    if "diameter" in dims and "width" not in dims:  # round tables: footprint is the diameter
        dims["width"] = dims["depth"] = dims["diameter"]
    if "base diameter" in dims and "width" not in dims:  # lamps: widest of base and shade
        dims["width"] = dims["depth"] = max(dims["base diameter"], dims.get("shade diameter") or 0)
    w = dims.get("width") or dims.get("max. width")
    d = (dims.get("depth") or dims.get("length")
         or dims.get("min. length")        # extendable tables: closed length
         or dims.get("base diameter"))     # arc lamps: width given, depth is the base
    hh = (dims.get("height") or dims.get("height including back cushions") or dims.get("max. height")
          or dims.get("backrest height")
          or (dims.get("pile length") or dims.get("thickness") if category == "rug" else None))

    pk_key = '"packaging":{"id":"measurements-packaging","title":"Packaging","contentProps":'
    j = h.find(pk_key, max(block_at, 0))  # this product's packaging follows its measurements
    pk = json.JSONDecoder().raw_decode(h, j + len(pk_key))[0] if j >= 0 and block_at >= 0 else None
    packages = []
    for p in (pk or {}).get("packages", []):
        qty = int((p.get("quantity") or {}).get("value") or 1)
        for g in p.get("measurementGroups", []):
            # the displayed text is authoritative; IKEA's numeric "value" is sometimes truncated (9 ¾ -> 9)
            ms = {x["type"]: inches(x.get("text", "")) or x.get("value") for x in g["measurements"]}
            if "diameter" in ms and "width" not in ms:  # rolls: bounding box
                ms["width"] = ms["height"] = ms["diameter"]
            box = {"w": ms.get("width"), "d": ms.get("length"), "h": ms.get("height")}
            packages += [box] * qty

    ar = ld.get("aggregateRating") or {}
    imgs = ld.get("image") or []
    imgs = imgs if isinstance(imgs, list) else [imgs]
    images = [i.get("contentUrl") if isinstance(i, dict) else i for i in imgs]
    images = [i for i in images if i]

    name = htmllib.unescape(ld.get("name", ""))
    sku = ld.get("sku") or ""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower().split(",")[0]).strip("-")
    return {
        "id": f"ikea-{slug}-{sku.replace('.', '')}",
        "retailer": "IKEA",
        "name": name,
        "article_number": sku,
        "category": category,
        "price_usd": float(price) if price is not None else None,
        "price_note": None,
        "dims_in": {"w": w, "d": d, "h": hh},
        "dims_raw": dims,
        "packages_in": packages or None,
        "rating": float(ar["ratingValue"]) if ar.get("ratingValue") else None,  # IKEA customer rating, 1-5
        "review_count": int(ar["reviewCount"]) if ar.get("reviewCount") else 0,
        "description": htmllib.unescape(ld.get("description") or "") or None,  # IKEA's own product text
        "color": htmllib.unescape(ld.get("color") or "") or None,
        "material": htmllib.unescape(ld.get("material") or "") or None,
        "image_url": images[0] if images else None,  # IKEA's main product shot
        "image_urls": images,
        "source_url": url,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def links(cat_url: str) -> list[str]:
    h = get(cat_url)
    return sorted(set(re.findall(r'https://www\.ikea\.com/us/en/p/[a-z0-9\-]+/', h)))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["--links"]:
        print("\n".join(links(a[1])))
        sys.exit()
    out, failed = [], []
    for cat, url in zip(a[::2], a[1::2]):
        try:
            out.append(product(url, cat))
        except Exception as e:  # report and keep going
            failed.append({"url": url, "error": str(e)})
    json.dump({"products": out, "failed": failed}, sys.stdout, indent=1, ensure_ascii=False)
