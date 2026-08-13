"""Shopify storefronts.

Most direct-to-consumer brands run Shopify, which publishes product data as
JSON with no key and no scraping. That data carries the title, price, image,
and publish date — everything a "new in" card needs.

Two routes, in order:

1. **The whole store** at /products.json. Every Shopify storefront exposes it,
   and it is ordered newest-published first, which is precisely what "new in"
   means. No handle to guess, nothing to keep in sync when a brand renames a
   collection. This is the default and it is the reason this file was rewritten.

2. **A named collection** at /collections/<handle>/products.json, used only
   when the config explicitly sets `handle`. Useful for narrowing to one part
   of a store, but fragile: brands name these inconsistently, and some never
   expose a new-arrivals collection at all. Sid Mashburn, for instance,
   publishes 400+ collections and not one of them contains "new" in the handle.

Either route can be filtered by tag, which is how a store that sells both
menswear and womenswear gets narrowed to the half Paul actually wants.
"""

from __future__ import annotations

from datetime import datetime, timezone

import requests

STORE_PATH = "https://{domain}/products.json?limit={limit}"
JSON_PATH = "https://{domain}/collections/{handle}/products.json?limit={limit}"
ATOM_PATH = "https://{domain}/collections/{handle}.atom"


def _price(product: dict, symbol: str = "$") -> str | None:
    variants = product.get("variants") or []
    prices = [float(v["price"]) for v in variants if v.get("price")]
    if not prices:
        return None
    low = min(prices)
    return f"{symbol}{low:,.0f}" if low == int(low) else f"{symbol}{low:,.2f}"


def _image(product: dict) -> str | None:
    images = product.get("images") or []
    return images[0].get("src") if images else None


EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _published(product: dict) -> datetime:
    """Sort key. Anything unparseable sorts oldest rather than blowing up.

    Always returns an aware datetime. Shopify stamps most products with an
    offset but not all of them, and sorting a mixed list of aware and naive
    datetimes raises TypeError — which would take down the whole section.
    """
    raw = product.get("published_at") or product.get("created_at") or ""
    try:
        # Python 3.9's fromisoformat doesn't accept a trailing Z.
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return EPOCH
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _tags_ok(product: dict, require: list[str], exclude: list[str]) -> bool:
    """Tag matching is case-insensitive and substring-based.

    Stores use tags as an informal taxonomy — Mashburn marks menswear
    `LineDescr_Mens`, Drake's marks new items `Collection_New In` — so an exact
    match would be too brittle to be useful.
    """
    tags = [t.lower() for t in (product.get("tags") or [])]
    if require and not any(any(r.lower() in t for t in tags) for r in require):
        return False
    if exclude and any(any(e.lower() in t for t in tags) for e in exclude):
        return False
    return True


def _shape(products: list[dict], domain: str, name: str, source: dict) -> list[dict]:
    require = source.get("require_tags") or []
    exclude = source.get("exclude_tags") or []
    symbol = source.get("currency_symbol", "$")
    limit = source.get("limit", 12)

    kept = [p for p in products if _tags_ok(p, require, exclude)]
    kept.sort(key=_published, reverse=True)

    return [
        {
            "title": product.get("title", "").strip(),
            "url": f"https://{domain}/products/{product.get('handle')}",
            "source": name,
            "summary": product.get("product_type") or "",
            "published": product.get("published_at"),
            "image": _image(product),
            "price": _price(product, symbol),
            "kind": "product",
        }
        for product in kept[:limit]
    ]


def _get_json(url: str, settings: dict) -> dict | None:
    response = requests.get(
        url,
        timeout=settings.get("timeout", 20),
        headers={"User-Agent": settings.get("user_agent", "Newsstand/1.0")},
    )
    if response.status_code == 200 and "json" in response.headers.get("content-type", ""):
        return response.json()
    return None


def _from_store(domain: str, source: dict, settings: dict) -> list[dict]:
    """The whole catalogue, newest first. Works without knowing any handle."""
    payload = _get_json(STORE_PATH.format(domain=domain, limit=250), settings)
    if not payload:
        return []
    return _shape(payload.get("products", []), domain, source["name"], source)


def _from_collection(domain: str, handle: str, source: dict, settings: dict) -> list[dict]:
    payload = _get_json(JSON_PATH.format(domain=domain, handle=handle, limit=50), settings)
    if payload is not None:
        return _shape(payload.get("products", []), domain, source["name"], source)

    from . import rss
    return [
        {**item, "kind": "product", "source": source["name"]}
        for item in rss.fetch(
            {"url": ATOM_PATH.format(domain=domain, handle=handle), "name": source["name"]},
            settings,
        )
    ]


def fetch(source: dict, settings: dict) -> list[dict]:
    """Newest products from a store, by whichever route answers.

    With no `handle` set this reads the whole store and takes the most recently
    published items — the approach that actually works across brands. A
    `handle` narrows to a named collection, with the store-wide read kept as a
    fallback so a renamed collection degrades instead of going dark.
    """
    domain = source["domain"].replace("https://", "").strip("/")
    failures = []

    handles = source.get("handle") or []
    handles = handles if isinstance(handles, list) else [handles]

    for handle in handles:
        try:
            items = _from_collection(domain, handle, source, settings)
        except Exception as exc:
            failures.append(f"/collections/{handle} → {type(exc).__name__}")
            continue
        if items:
            source["_resolved"] = f"/collections/{handle}"
            return items
        failures.append(f"/collections/{handle} → empty")

    try:
        items = _from_store(domain, source, settings)
    except Exception as exc:
        failures.append(f"/products.json → {type(exc).__name__}: {exc}")
    else:
        if items:
            source["_resolved"] = "/products.json (whole store, newest first)"
            return items
        failures.append("/products.json → empty")

    raise RuntimeError(
        "; ".join(failures)
        + f" — this store may not be Shopify (check https://{domain}/products.json in a browser)"
    )


def list_collections(domain: str, settings: dict) -> list[tuple[str, str]]:
    """Every Shopify store publishes its collection list openly.

    Paginated: stores with heavy made-to-order catalogues run past the 250-item
    cap, and the interesting collection is often on the far side of it.
    """
    domain = domain.replace("https://", "").strip("/")
    found: list[tuple[str, str]] = []
    for page in range(1, 6):
        payload = _get_json(
            f"https://{domain}/collections.json?limit=250&page={page}", settings
        )
        batch = (payload or {}).get("collections", [])
        if not batch:
            break
        found.extend((c.get("handle", ""), c.get("title", "")) for c in batch)
    return found
