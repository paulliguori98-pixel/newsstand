"""Substack Notes.

Notes are the short posts people write on Substack itself rather than in a
publication. There's no RSS for them, but there is an unauthenticated JSON
endpoint behind the profile page:

    /api/v1/reader/feed/profile/<user_id>?types[]=note

It answers instantly from a browser and returns 403 to a plain Python
request from GitHub's servers.

── Why this file uses curl_cffi ──────────────────────────────────────────
The first assumption was that Substack blocks datacenter IPs. Probably
wrong. Cloudflare's usual defence is TLS fingerprinting: the handshake that
Python's `requests` performs looks nothing like a browser's, and no amount
of setting a Chrome User-Agent changes that, because the tell is a layer
below the headers.

curl_cffi performs a handshake that matches real Chrome, which is the one
thing a header can't fake. If Notes start working, that was the block. If
they still 403, the block is something else — probably the IP after all —
and this adapter can't win from a datacenter.

The import is optional on purpose. If curl_cffi isn't installed the module
still loads and falls back to plain requests, so a missing dependency
degrades to "Notes don't work" rather than taking down the whole build.

── What this is and isn't ────────────────────────────────────────────────
This reads public, unauthenticated data — the same notes anyone sees on a
public profile, from people Paul follows, for his own reading. It isn't
getting past a login or a paywall. It is deliberately making an automated
request look like a browser, which Substack may not want, so it's fair to
expect it could stop working without notice.

Notes have no headline — just a body of text — so the first sentence becomes
the title. That suits short posts and nothing longer.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import requests

try:  # optional: absent locally, present on the build
    from curl_cffi import requests as browser
    IMPERSONATE = "chrome"
except ImportError:  # pragma: no cover
    browser = None
    IMPERSONATE = None

PROFILE = "https://substack.com/api/v1/user/{handle}/public_profile"
NOTES = "https://substack.com/api/v1/reader/feed/profile/{user_id}?types%5B%5D=note"
TAG = re.compile(r"<[^>]+>")


def _headers(settings: dict) -> dict:
    return {
        "User-Agent": settings.get("user_agent", "Newsstand/1.0"),
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://substack.com/",
    }


def _get(url: str, settings: dict):
    """Chrome's TLS handshake if available, plain requests if not."""
    timeout = settings.get("timeout", 20)
    if browser is not None:
        return browser.get(url, timeout=timeout, headers=_headers(settings),
                           impersonate=IMPERSONATE)
    return requests.get(url, timeout=timeout, headers=_headers(settings))


def _clean(text: str) -> str:
    return " ".join(TAG.sub(" ", text or "").split())


def _first_line(body: str, limit: int = 140) -> str:
    text = _clean(body)
    if not text:
        return ""
    cut = re.split(r"(?<=[.!?])\s+", text)[0]
    if len(cut) > limit:
        cut = cut[: limit - 1].rsplit(" ", 1)[0] + "…"
    return cut


def _published(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if not parsed.tzinfo:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def _notes_for(handle: str, settings: dict, per_person: int, label: str | None) -> list[dict]:
    profile = _get(PROFILE.format(handle=handle), settings)
    if profile.status_code != 200:
        raise RuntimeError(f"profile HTTP {profile.status_code}")

    data = profile.json()
    user_id = data.get("id")
    if not user_id:
        raise RuntimeError("profile had no id")

    feed = _get(NOTES.format(user_id=user_id), settings)
    if feed.status_code != 200:
        raise RuntimeError(f"notes HTTP {feed.status_code}")

    items = []
    for entry in feed.json().get("items", []):
        comment = entry.get("comment") or {}
        title = _first_line(comment.get("body"))
        if not title:
            continue
        items.append(
            {
                "title": title,
                "url": f"https://substack.com/@{handle}/note/c-{comment.get('id')}",
                "source": label or data.get("name") or handle,
                "summary": "",
                "published": _published(comment.get("date")),
                "image": comment.get("photo_url"),
                "kind": "note",
            }
        )
        if len(items) >= per_person:
            break
    return items


def fetch(source: dict, settings: dict) -> list[dict]:
    """Notes from every handle listed, newest first.

    One person failing doesn't lose the others; every handle failing raises,
    with each status code intact so the build log can say what happened.
    """
    handles = source.get("handles") or []
    handles = handles if isinstance(handles, list) else [handles]
    per_person = source.get("per_person", 3)
    label = source.get("name")

    items: list[dict] = []
    failures: list[str] = []

    for handle in handles:
        try:
            items.extend(_notes_for(handle, settings, per_person, label))
        except Exception as exc:
            failures.append(f"@{handle} → {exc}")

    if not items:
        how = "curl_cffi" if browser is not None else "plain requests (curl_cffi missing)"
        raise RuntimeError(f"[{how}] " + ("; ".join(failures) or "no notes returned"))

    source["_resolved"] = f"{len(handles) - len(failures)}/{len(handles)} handles"
    return items
