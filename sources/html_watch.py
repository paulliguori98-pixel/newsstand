"""Selector-driven scraper for stores with no open feed.

Some brands run Shopify but switch off /products.json (Buck Mason), and some
aren't Shopify at all (Tracksmith, J.Crew). For those, this reads the
new-arrivals page and pulls product tiles using the CSS selectors in
config.yaml.

This is the most fragile source type in the project, and it's worth being
honest about why: retailers restyle their sites a few times a year. Prefer
selectors built on semantic markup or on href patterns, which tend to
survive a redesign, over CSS-module class names like
`img_grid-module--grid--304f7` — those carry a build hash and change every
time the site is redeployed.

When a store goes quiet in the build log, open the page, look at the markup,
and update the selector. That's the whole maintenance story.

Prices need care. Tracksmith renders "220" and draws the dollar sign in CSS,
so nothing in the text carries a currency. Buck Mason renders "$168" inside
an unclassed span. So: if `price_selector` is set, that element's text is
used; otherwise the tile's own text is searched for the first price-shaped
number. Either way `currency_symbol` is prepended when the text lacks one.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

PRICE = re.compile(r"[$£€]\s?\d[\d,]*(?:\.\d{2})?|\d[\d,]*(?:\.\d{2})?")


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


def _price(tile, selector: str, symbol: str) -> str | None:
    """Pull a price from the tile and make sure it carries a currency mark."""
    raw = _text(tile, selector) if selector else ""
    if not raw:
        # No selector, or it matched nothing — find the first price-shaped
        # run of digits anywhere in the tile. Works where the price sits in
        # an unclassed element.
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

    items = []
    for tile in soup.select(source["item_selector"]):
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
