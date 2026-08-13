#!/usr/bin/env python3
"""Newsstand — build data/feed.json from the sources in config.yaml.

  python fetch.py            build the edition
  python fetch.py --probe    test every source, print what answers, write nothing

No source can break the build. Anything that fails is recorded and the rest
of the edition goes out without it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from sources import html_watch, pinterest, rss, shopify

VERSION = "0.4"
ROOT = Path(__file__).parent
DATA = ROOT / "data"
ADAPTERS = {
    "rss": rss.fetch,
    "shopify": shopify.fetch,
    "html": html_watch.fetch,
    "pinterest": pinterest.fetch,
}


def load_config() -> dict:
    with open(ROOT / "config.yaml") as fh:
        return yaml.safe_load(fh)


def load_seen() -> dict:
    path = DATA / "seen.json"
    if path.exists():
        return json.loads(path.read_text())
    return {}


def item_id(item: dict) -> str:
    basis = item.get("url") or (item.get("source", "") + item.get("title", ""))
    return hashlib.sha1(basis.encode()).hexdigest()[:16]


def muted(title: str, patterns: list[str]) -> bool:
    low = (title or "").lower()
    return any(p.lower() in low for p in patterns or [])


def published_at(item: dict) -> datetime | None:
    """The item's own publish time, as an aware datetime, or None."""
    raw = item.get("published")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def too_old(item: dict, max_age_hours: int | None, now: datetime) -> bool:
    """Whether an item falls outside a section's freshness window.

    This is how news gets separated from everything else. Reported news is
    hours old; service journalism ("Should I pay off my car loan?") and
    evergreen features sit in the same feed for weeks and would otherwise
    keep resurfacing. A section with `max_age_hours` set drops anything
    older, which removes that genre without having to guess at its wording.

    Items with no publish date are kept — a missing timestamp shouldn't be
    treated as evidence of staleness.
    """
    if not max_age_hours:
        return False
    when = published_at(item)
    if when is None:
        return False
    return when < now - timedelta(hours=max_age_hours)


def build(config: dict, probe: bool = False) -> dict:
    settings = config.get("settings", {})
    now = datetime.now(timezone.utc)
    seen = {} if probe else load_seen()
    new_cutoff = now - timedelta(days=settings.get("new_window_days", 4))
    limit = settings.get("per_section_limit", 12)

    sections, errors, probe_report = [], [], []

    for section in config.get("sections", []):
        items = []
        max_age = section.get("max_age_hours")

        for source in section.get("sources", []):
            if source.get("enabled") is False:
                probe_report.append((source.get("name", "?"), "skipped", "disabled in config"))
                continue

            adapter = ADAPTERS.get(source.get("type"))
            if adapter is None:
                errors.append(f"{source.get('name')}: unknown source type {source.get('type')!r}")
                continue

            try:
                got = adapter(source, settings)
            except Exception as exc:  # a bad source never takes down the edition
                errors.append(f"{source.get('name', '?')}: {type(exc).__name__} — {exc}")
                probe_report.append((source.get("name", "?"), "FAILED", f"{type(exc).__name__}: {exc}"))
                continue

            fresh = [i for i in got if not too_old(i, max_age, now)]
            detail = f"{len(fresh)} items"
            if len(fresh) != len(got):
                detail += f" ({len(got) - len(fresh)} too old)"
            if source.get("_resolved"):
                detail += f"  ← {source['_resolved']}"
            probe_report.append((source.get("name", "?"), "ok" if fresh else "empty", detail))
            items.extend(fresh)

        # Dedupe, mute, stamp first-seen, sort.
        deduped: dict[str, dict] = {}
        for item in items:
            if muted(item.get("title", ""), section.get("mute")):
                continue
            iid = item_id(item)
            item["id"] = iid
            first_seen = seen.get(iid) or now.isoformat()
            seen[iid] = first_seen
            item["first_seen"] = first_seen
            item["is_new"] = datetime.fromisoformat(first_seen) > new_cutoff
            deduped.setdefault(iid, item)

        ordered = sorted(
            deduped.values(),
            key=lambda i: i.get("published") or i.get("first_seen") or "",
            reverse=True,
        )[:limit]

        sections.append(
            {
                "id": section["id"],
                "title": section["title"],
                "kind": section.get("kind", "headlines"),
                "items": ordered,
            }
        )

    return {
        "generated_at": now.isoformat(),
        "sections": sections,
        "errors": errors,
        "_seen": seen,
        "_probe": probe_report,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", action="store_true", help="test sources, write nothing")
    parser.add_argument("--collections", metavar="DOMAIN",
                        help="list a Shopify store's collection handles, e.g. shopmashburn.com")
    args = parser.parse_args()

    if args.collections:
        config = load_config()
        for handle, title in shopify.list_collections(args.collections, config.get("settings", {})):
            print(f"  {handle.ljust(34)} {title}")
        return 0

    edition = build(load_config(), probe=args.probe)

    if args.probe:
        print(f"Newsstand {VERSION} — {len(edition['_probe'])} sources\n")
        width = max(len(n) for n, _, _ in edition["_probe"]) if edition["_probe"] else 10
        for name, status, detail in edition["_probe"]:
            mark = {"ok": "  ✓", "empty": "  ·", "skipped": "  –"}.get(status, "  ✗")
            print(f"{mark} {name.ljust(width)}  {detail}")
        failed = sum(1 for _, s, _ in edition["_probe"] if s == "FAILED")
        print(f"\n{len(edition['_probe'])} sources checked, {failed} failed.")
        return 1 if failed else 0

    seen = edition.pop("_seen")
    edition.pop("_probe")
    DATA.mkdir(exist_ok=True)
    (DATA / "feed.json").write_text(json.dumps(edition, indent=1))
    (DATA / "seen.json").write_text(json.dumps(seen))
    # Also emit as a script so index.html opens by double-click, not just
    # over http — a bare file:// page can't fetch() a sibling .json.
    (DATA / "feed.js").write_text(
        "window.__EDITION__ = " + json.dumps(edition) + ";"
    )

    total = sum(len(s["items"]) for s in edition["sections"])
    print(f"Built {total} items across {len(edition['sections'])} sections.")
    for err in edition["errors"]:
        print(f"  ! {err}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
