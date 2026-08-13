"""Selector-driven scraper for stores with no open feed.

J.Crew runs Salesforce Commerce Cloud, not Shopify, so there is no products.json
to ask. This reads the new-arrivals page and pulls tiles using the CSS selectors
in config.yaml.

Retailers change their markup a few times a year. When J.Crew goes quiet in
`--probe`, open the page, copy the current tile class, and update the selector —
that's the whole maintenance story. Pages rendered entirely by JavaScript return
nothing here; for those, use the brand's own email or a category RSS if they
offer one.
"""

from __future__ import annotations

from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


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


def fetch(source: dict, settings: dict) -> list[dict]:
    response = requests.get(
        source["url"],
        timeout=settings.get("timeout", 20),
        headers={
            "User-Agent": settings.get("user_agent", "Newsstand/1.0"),
            "Accept": "text/html",
        },
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    items = []
    for tile in soup.select(source["item_selector"])[:24]:
        title = _text(tile, source.get("title_selector", "")) or tile.get("aria-label", "")
        if not title:
            continue

        link = _first(tile, source.get("link_selector", "a"))
        href = link.get("href") if link else None

        image = _first(tile, source.get("image_selector", "img"))
        src = None
        if image:
            src = image.get("src") or image.get("data-src") or image.get("srcset", "").split()[0]

        items.append(
            {
                "title": title,
                "url": urljoin(source["url"], href) if href else source["url"],
                "source": source["name"],
                "summary": "",
                "published": None,
                "image": urljoin(source["url"], src) if src else None,
                "price": _text(tile, source.get("price_selector", "")) or None,
                "kind": "product",
            }
        )
    return items
