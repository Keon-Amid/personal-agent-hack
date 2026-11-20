"""Price vs. quality options for one category in one room.

For each product: price, IKEA customer rating, review count, the fit checks, and whether it's a
"best value" pick. Best value = it fits, has enough reviews to trust the rating, and no other trusted
product that fits is both cheaper (or equal) and rated higher (or equal). That's the price/quality
Pareto frontier among things that actually fit.

The UI draws price on x, rating on y, dot size = review count, colour = fit verdict, frontier = line.
"""
from __future__ import annotations

from .checks import FITS, check_doorway, check_floor, check_rug, check_wall, overall

MIN_REVIEWS = 10  # below this the average rating is too noisy to rank on


def room(wall: dict, depth: dict, door_width: dict, door_height: dict) -> dict:
    """The room as the fit checks need it. Each value is a fit.measurement(...)."""
    return {"wall": wall, "depth": depth, "door_width": door_width, "door_height": door_height}


def check_all(product: dict, rm: dict) -> list[dict]:
    door = check_doorway(product, rm["door_width"], rm["door_height"])
    if product["category"] == "rug":  # rugs lie in the room, not against a wall
        return check_rug(product, rm["wall"], rm["depth"]) + door
    return [check_wall(product, rm["wall"]), check_floor(product, rm["depth"])] + door


def _trusted(o: dict) -> bool:
    return o["rating"] is not None and o["review_count"] >= MIN_REVIEWS and o["price_usd"] is not None


def options(products: list[dict], category: str, rm: dict) -> list[dict]:
    out = []
    for p in products:
        if p["category"] != category:
            continue
        results = check_all(p, rm)
        out.append({
            "id": p["id"], "name": p["name"], "price_usd": p["price_usd"],
            "rating": p.get("rating"), "review_count": p.get("review_count", 0),
            "image_url": p.get("image_url"), "source_url": p["source_url"],
            "fit": overall(results), "fit_results": results,
            "best_value": False, "why": "",
        })
    pool = [o for o in out if o["fit"] == FITS and _trusted(o)]
    for o in out:
        if o["fit"] != FITS:
            bad = next(r for r in o["fit_results"] if r["verdict"] == o["fit"])
            o["why"] = f'{o["fit"]}: {bad["math"]}'
        elif not _trusted(o):
            o["why"] = (f'not ranked: {o["review_count"]} reviews (need {MIN_REVIEWS})'
                        if o["price_usd"] is not None else "not ranked: no price on the page")
        else:
            beaten_by = [q for q in pool if q is not o
                         and q["price_usd"] <= o["price_usd"] and q["rating"] >= o["rating"]
                         and (q["price_usd"], -q["rating"]) != (o["price_usd"], -o["rating"])]
            o["best_value"] = not beaten_by
            o["why"] = ("best value: nothing that fits is cheaper and better rated" if not beaten_by else
                        f'{beaten_by[0]["name"].split(" - ")[0]} is ${beaten_by[0]["price_usd"]:g} '
                        f'and rated {beaten_by[0]["rating"]:g}')
    return sorted(out, key=lambda o: (o["price_usd"] is None, o["price_usd"] or 0))
