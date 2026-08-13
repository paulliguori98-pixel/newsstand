"""RSS and Atom feeds — the backbone of the edition.

A note on Substack: publications served from a *.substack.com subdomain are
refused (HTTP 403) when the build runs on GitHub's servers, while the same
publication on its own custom domain answers fine — A Continuous Lean via
acl.news, One Useful Thing via oneusefulthing.org, Vittles via
vittlesmagazine.com. Prefer a custom domain whenever a publication has one.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import feedparser
import requests

TAG = re.compile(r"<[^>]+>")

# A browser sends more than a User-Agent. Bot filters in front of some
# publishers reject requests that carry a browser UA and nothing else.
BROWSER_HEADERS = {
    "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5",
    "Accept-Language": "en-US,en;q=0.9",
}


def _clean(text: str, limit: int = 180) -> str:
    text = TAG.sub("", text or "").replace("&nbsp;", " ")
    text = " ".join(text.split())
    return text[: limit - 1] + "…" if len(text) > limit else text


def _published(entry) -> str | None:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat()
    return None


def _image(entry) -> str | None:
    for media in (entry.get("media_content") or []) + (entry.get("media_thumbnail") or []):
        if media.get("url"):
            return media["url"]
    for link in entry.get("links", []):
        if str(link.get("type", "")).startswith("image/"):
            return link.get("href")
    body = entry.get("summary", "") or ""
    match = re.search(r'<img[^>]+src=["\']([^"\']+)', body)
    return match.group(1) if match else None


def _candidates(source: dict) -> list[str]:
    url = source["url"]
    return url if isinstance(url, list) else [url]


def fetch(source: dict, settings: dict) -> list[dict]:
    """Try each candidate URL in turn and keep the first that has entries.

    Publishers move and retire feed URLs constantly, so a source can list
    several addresses and let the run settle which one is alive. The winner
    is recorded on the source so --probe can print it.

    A source may set `limit` to cap how many of its items reach the section.
    This is what stops a wire service that publishes hourly from taking every
    slot and burying a newsletter that publishes weekly — sections sort by
    date, so without a cap the most prolific feed simply wins.
    """
    parsed, failures = None, []
    headers = {
        "User-Agent": settings.get("user_agent", "Newsstand/1.0"),
        **BROWSER_HEADERS,
    }

    for candidate in _candidates(source):
        try:
            response = requests.get(
                candidate,
                timeout=settings.get("timeout", 20),
                headers=headers,
            )
            response.raise_for_status()
            attempt = feedparser.parse(response.content)
            if attempt.entries:
                parsed = attempt
                source["_resolved"] = candidate
                break
            failures.append(f"{candidate} → no entries")
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            detail = f"HTTP {status}" if status else type(exc).__name__
            failures.append(f"{candidate} → {detail}")

    if parsed is None:
        raise RuntimeError("; ".join(failures))

    items = []
    for entry in parsed.entries[:25]:
        image = _image(entry)
        if source.get("images_only") and not image:
            continue
        items.append(
            {
                "title": (entry.get("title") or "").strip(),
                "url": entry.get("link"),
                "source": source.get("name") or parsed.feed.get("title", "Feed"),
                "summary": _clean(entry.get("summary", "")),
                "published": _published(entry),
                "image": image,
                "kind": "article",
            }
        )

    return items[: source.get("limit", 25)]
