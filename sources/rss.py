"""RSS and Atom feeds — the backbone of the edition.

A note on Substack: publications served from a *.substack.com subdomain are
refused (HTTP 403) when the build runs on GitHub's servers, while the same
publication on its own custom domain answers fine — A Continuous Lean via
acl.news, One Useful Thing via oneusefulthing.org, Vittles via
vittlesmagazine.com. Prefer a custom domain whenever a publication has one.
"""

from __future__ import annotations

import html
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
    # Strip tags first, then decode entities — the other order would turn an
    # escaped &lt;script&gt; back into a live tag.
    text = html.unescape(TAG.sub("", text or ""))
    text = " ".join(text.split())
    return text[: limit - 1] + "…" if len(text) > limit else text


def _published(entry) -> str | None:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat()
    return None

# WordPress serves resized derivatives — foo-150x150.jpg — and feeds often
# carry the thumbnail rather than the original at foo.jpg. Left alone, a
# 150px square gets blown up to 655px in a hero slot.
WP_SIZE = re.compile(r"-\d{2,4}x\d{2,4}(?=\.(?:jpe?g|png|webp|gif)(?:\?|$))", re.I)


def _full_size(url: str) -> str:
    return WP_SIZE.sub("", url or "")


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

def _categories(entry) -> list[str]:
    """feedparser exposes RSS <category> elements as entry.tags.

    Hackaday files reader projects under a category ending in "hacks" and
    its own writing under "Hackaday Columns", so the two are separable
    without guessing from the headline.
    """
    return [str(t.get("term") or "").lower() for t in (entry.get("tags") or [])]
    
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

    require_cats = [c.lower() for c in (source.get("require_categories") or [])]
    exclude_cats = [c.lower() for c in (source.get("exclude_categories") or [])]   
    
    items = []
    for entry in parsed.entries[:25]:
        cats = _categories(entry)
        if require_cats and not any(r in c for c in cats for r in require_cats):
            continue
        if exclude_cats and any(e in c for c in cats for e in exclude_cats):
            continue

        image = _image(entry)
        if source.get("images_only") and not image:
            continue
        items.append(
            {
                "title": html.unescape((entry.get("title") or "").strip()),
                "url": entry.get("link"),
                "source": source.get("name") or parsed.feed.get("title", "Feed"),
                "summary": _clean(entry.get("summary", "")),
                "published": _published(entry),
                "image": image,
                "kind": "article",
            }
        )

        return _full_size(found) if found else None
