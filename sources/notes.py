"""Substack Notes.

Notes are the short posts people write on Substack itself rather than in a
publication — closer to a timeline than a newsletter. There's no RSS for
them, but there is an unauthenticated JSON endpoint behind the profile page,
and it answers without a login:

    /api/v1/reader/feed/profile/<user_id>?types[]=note

The config lists handles, not numeric ids, because handles are readable and
stable while ids are neither. Each handle is resolved once per run via
/api/v1/user/<handle>/public_profile.

── The thing to know before trusting this ────────────────────────────────
Substack returns HTTP 403 to GitHub's servers for every *.substack.com
SUBDOMAIN — importai, iknow, aprivatechef all fail that way, which is why
those publications aren't in this project. Notes live on the APEX domain,
substack.com, which was never tested until now. If the apex is blocked too,
this adapter will fail exactly like the others and the probe log will say
so. If it isn't, Notes work. There was no way to find out except by asking
the build.

Notes are also unlike everything else here: no headline, no dek, just a body
of text. So the first line becomes the title and the rest is dropped, which
suits a feed of short posts and would suit nothing longer.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import requests

PROFILE = "https://substack.com/api/v1/user/{handle}/public_profile"
NOTES = "https://substack.com/api/v1/reader/feed/profile/{user_id}?types%5B%5D=note"
TAG = re.compile(r"<[^>]+>")


def _headers(settings: dict) -> dict:
    return {
        "User-Agent": settings.get("user_agent", "Newsstand/1.0"),
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    }


def _clean(text: str) -> str:
    text = TAG.sub(" ", text or "")
    return " ".join(text.split())


def _first_line(body: str, limit: int = 140) -> str:
    """Notes have no title, so the opening sentence becomes one."""
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


def _resolve(handle: str, settings: dict) -> tuple[int, str] | None:
    response = requests.get(
        PROFILE.format(handle=handle),
        timeout=settings.get("timeout", 20),
        headers=_headers(settings),
    )
    if response.status_code != 200:
        raise RuntimeError(f"@{handle} → HTTP {response.status_code}")
    data = response.json()
    return data.get("id"), data.get("name") or handle


def fetch(source: dict, settings: dict) -> list[dict]:
    """Notes from every handle listed, newest first."""
    handles = source.get("handles") or []
    handles = handles if isinstance(handles, list) else [handles]
    per_person = source.get("per_person", 3)

    items: list[dict] = []
    failures: list[str] = []

    for handle in handles:
        try:
            user_id, name = _resolve(handle, settings)
            response = requests.get(
                NOTES.format(user_id=user_id),
                timeout=settings.get("timeout", 20),
                headers=_headers(settings),
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            failures.append(f"@{handle} → {f'HTTP {status}' if status else type(exc).__name__}")
            continue

        taken = 0
        for entry in payload.get("items", []):
            comment = entry.get("comment") or {}
            body = comment.get("body")
            title = _first_line(body)
            if not title:
                continue
            items.append(
                {
                    "title": title,
                    "url": f"https://substack.com/@{handle}/note/c-{comment.get('id')}",
                    "source": source.get("name") or name,
                    "summary": "",
                    "published": _published(comment.get("date")),
                    "image": comment.get("photo_url"),
                    "kind": "note",
                }
            )
            taken += 1
            if taken >= per_person:
                break

    if not items and failures:
        raise RuntimeError("; ".join(failures))

    source["_resolved"] = f"{len(handles) - len(failures)}/{len(handles)} handles"
    return items
