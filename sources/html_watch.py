"""Selector-driven scraper for stores with no open feed.

Some brands run Shopify but switch off /products.json (Buck Mason), and some
aren't Shopify at all (Tracksmith, J.Crew). For those, this reads the
new-arrivals page and pulls product tiles using the CSS selectors in
config.yaml.

This is the most fragile source type in the project. Retailers restyle a few
times a year, so prefer selectors built on semantic markup or href patterns —
`article[handle]`, `a[href*="/products/m-"]` — over CSS-module class names
like `img_grid-module--grid--304f7`, which carry a build hash and change on
every deploy. When a store goes quiet in the build log, open the page, look
at the markup, update the selector. That's the whole maintenance story.

Two wrinkles worth knowing, both learned the hard way:

Prices differ per site. Tracksmith renders "220" and draws the dollar sign in
CSS; Buck Mason doesn't render a price server-side at all. So if
`price_selector` is set that element's text is used, otherwise the tile text
is searched for a price-shaped number, and `currency_symbol` is prepended
when nothing carries one. A card with no price is fine — it just omits it.

Titles differ too. Buck Mason's tiles are empty shells server-side: no name,
no price, just an image and a link, with everything painted in by JavaScript
afterwards. But the tile carries a `handle` attribute holding the product
slug. `title_attr: handle` turns that slug into a readable name, which is the
only way to read a site that renders its text client-side.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

PRICE = re.compile(r"[$£€]\s?\d[\d,]*(?:\.\d{2})?|\d[\d,]*(?:\.\d{2})?")
# Leading style codes on Buck Mason handles: b015-, m090-.
STYLE_CODE = re.compile(r"^[a-z]\d{2,4}-")
LOWER_WORDS = {"a", "an", "and", "the", "of", "in", "with", "for"}


def _first(node, selector: str):
    if not selector:
        return None
    for part in selector.split(","):
        found = node.select_one(part.strip())
        if found:
            return found
    return None


def _text(node, selector: str) -> str:
    found = _first(node, selector)
    return found.get_text(strip=True) if found else ""


def _from_slug(slug: str) -> str:
    """Turn a product handle into something readable.

    "b015-japanese-chambray-station-shirt" → "Japanese Chambray Station Shirt"
    """
    slug = STYLE_CODE.sub("", (slug or "").strip().lower())
    words = [w for w in slug.split("-") if w]
    if not words:
        return ""
    titled = [
        w if w in LOWER_WORDS and i else w.capitalize()
        for i, w in enumerate(words)
    ]
    return " ".join(titled)


def _price(tile, selector: str, symbol: str) -> str | None:
    raw = _text(tile, selector) if selector else ""
    if not raw:
        match = PRICE.search(tile.get_text(" ", strip=True))
        raw = match.group(0) if match else ""
    if not raw:
        return None
    match = PRICE.search(raw)
    if not match:
        return None
    found = match.group(0).strip()
    return found if found[0] in "$£€" else f"{symbol}{found}"


def fetch(source: dict, settings: dict) -> list[dict]:
    response = requests.get(
        source["url"],
        timeout=settings.get("timeout", 20),
        headers={
            "User-Agent": settings.get("user_agent", "Newsstand/1.0"),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    symbol = source.get("currency_symbol", "$")
    limit = source.get("limit", 24)
    title_attr = source.get("title_attr")

    items = []
    for tile in soup.select(source["item_selector"]):
        if title_attr:
            title = _from_slug(tile.get(title_attr, ""))
        else:
            title = _text(tile, source.get("title_selector", "")) or tile.get("aria-label", "")
        if not title:
            continue

        link = _first(tile, source.get("link_selector", "a"))
        href = link.get("href") if link else None

        image = _first(tile, source.get("image_selector", "img"))
        src = None
        if image:
            src = image.get("src") or image.get("data-src") or ""
            if not src:
                srcset = image.get("srcset", "")
                src = srcset.split()[0] if srcset else None

        items.append(
            {
                "title": title,
                "url": urljoin(source["url"], href) if href else source["url"],
                "source": source["name"],
                "summary": "",
                "published": None,
                "image": urljoin(source["url"], src) if src else None,
                "price": _price(tile, source.get("price_selector", ""), symbol),
                "kind": "product",
            }
        )
        if len(items) >= limit:
            break

    return items
