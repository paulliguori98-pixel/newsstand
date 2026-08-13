"""Pinterest — the one source that can't be read anonymously.

Pinterest retired public board RSS feeds, and boards are rendered by JavaScript,
so scraping returns an empty shell. The only supported route is the v5 API with
a token tied to your own account:

  1. developers.pinterest.com → create an app (a personal one is fine; the
     "trial access" tier covers reading your own boards).
  2. Generate an access token with the boards:read and pins:read scopes.
  3. Store it as a GitHub Actions secret named PINTEREST_TOKEN.
  4. Hit /v5/boards to find your board id, put it in config.yaml, and flip
     `enabled: true`.

Tokens expire — the trial tier's last 30 days — so this section will go quiet
periodically and need a refresh. That's the real cost of the Pinterest piece,
and it's why it ships disabled. The `rss` fallback in the same section keeps
Vibes populated in the meantime.
"""

from __future__ import annotations

import os

import requests

API = "https://api.pinterest.com/v5/boards/{board_id}/pins"


def fetch(source: dict, settings: dict) -> list[dict]:
    token = os.environ.get(source.get("access_token_env", "PINTEREST_TOKEN"))
    if not token:
        raise RuntimeError(
            "no Pinterest token in the environment — set it or leave enabled: false"
        )
    if not source.get("board_id"):
        raise RuntimeError("no board_id set in config.yaml")

    response = requests.get(
        API.format(board_id=source["board_id"]),
        headers={"Authorization": f"Bearer {token}"},
        params={"page_size": 24},
        timeout=settings.get("timeout", 20),
    )
    response.raise_for_status()

    items = []
    for pin in response.json().get("items", []):
        images = (pin.get("media") or {}).get("images") or {}
        best = images.get("1200x") or images.get("600x") or next(iter(images.values()), {})
        items.append(
            {
                "title": pin.get("title") or pin.get("alt_text") or "",
                "url": pin.get("link") or f"https://pinterest.com/pin/{pin.get('id')}",
                "source": source.get("name", "Pinterest"),
                "summary": pin.get("description", ""),
                "published": pin.get("created_at"),
                "image": best.get("url"),
                "kind": "pin",
            }
        )
    return items
