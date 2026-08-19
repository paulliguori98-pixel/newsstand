"""Buck Mason — the JSON behind their collection pages.

Their storefront is headless Shopify: /products.json 404s, and the tiles in
the HTML carry only an id and a handle. Prices are written in by JavaScript
after the page loads, so no CSS selector can ever reach one — which is why
every Buck Mason tile has had a blank price line. There is exactly one
dollar sign in the raw HTML of their new-arrivals page, and it belongs to a
shipping threshold.

Gatsby leaves each page's own data at /page-data/<path>/page-data.json, and
the collection's copy holds all 195 products with a real title, a price, a
publish date and their images. One request, no scraping, and no guessing at
product names from URL slugs.

Two details worth keeping:
  · `flat` marks the product shot on white rather than the model shot.
    37 of 152 products don't have one, so fall back to the first image.
  · `cdnf:/` is their shorthand for the Shopify CDN folder. Expanding it is
    the whole trick to getting a usable image URL.
"""

from __future__ import annotations

from datetime import datetime, timezone

import requests

CDN = "https://cdn.shopify.com/s/files/1/0123/5065/2473/files/"
SITE = "https://www.buckmason.com"


def _image(product: dict, cdn: str) -> str | None:
    media = product.get("media") or []
    shot = (next((m for m in media if m.get("flat")), None)
            or next((m for m in media if not m.get("face")), None)
            or (media[0] if media else None))
    src = str((shot or {}).get("src") or "")
    if not src:
        return None
    return src.replace("cdnf:/", cdn, 1) if src.startswith("cdnf:/") else src


def fetch(source: dict, settings: dict) -> list[dict]:
    reply = requests.get(
        source["url"],
        headers={"User-Agent": settings.get("user_agent", "newsstand")},
        timeout=settings.get("timeout", 20),
    )
    reply.raise_for_status()

    try:
        products = reply.json()["result"]["data"]["collection"]["products"]
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"unexpected page-data shape: {exc}") from exc

    cdn = source.get("cdn", CDN)
    site = source.get("site", SITE)
    symbol = source.get("currency_symbol", "$")

    # `broken` is their own flag for a product that shouldn't be shown.
    live = [p for p in products if p.get("available") and not p.get("broken")]
    live.sort(key=lambda p: p.get("pub") or 0, reverse=True)

    items = []
    for product in live[: source.get("limit", 12)]:
        price = product.get("first_product_price")
        pub = product.get("pub")
        items.append({
            "title": product.get("title") or product.get("handle", ""),
            "url": f"{site}/products/{product.get('handle', '')}",
            "source": source.get("name", "Buck Mason"),
            "image": _image(product, cdn),
            "price": f"{symbol}{price:,}" if price else None,
            "published": (datetime.fromtimestamp(pub, timezone.utc).isoformat()
                          if pub else None),
            "kind": "product",
        })
    return items
