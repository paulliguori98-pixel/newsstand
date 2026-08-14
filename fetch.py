#!/usr/bin/env python3
"""Newsstand — build data/feed.json from the sources in config.yaml.

  python fetch.py            build the edition
  python fetch.py --probe    test every source, print what answers, write nothing

No source can break the build. Anything that fails is recorded and the rest
of the edition goes out without it.

── Collecting vs showing ─────────────────────────────────────────────────
  limit:  on a source — how many items to COLLECT each run
  show:   on a source — how many of those reach the front page
  limit:  on a section — the cap for the whole section

Everything collected from a `goods` section is merged into data/archive.json
and shown on all.html. That file only grows: retailers don't publish
backdated arrivals, so a record can only be built forward.

── How headlines are ranked ──────────────────────────────────────────────
Every `headlines` section groups items describing the same event, then:

    score = number of outlets that ran it  (+3 if it hits a boost keyword)

`min_outlets` then drops anything below a corroboration floor — the idea
being that a story only one newsroom carried is that newsroom's editorial
choice rather than an event. A boosted story survives the floor regardless,
because the keywords exist precisely to rescue quietly important news that
hasn't been widely picked up yet.

Set the floor per section, not globally: World & Nation draws on five
outlets that overlap constantly, while Business has three that rarely run
the same story, so the same floor would empty it most mornings.

Each surviving story keeps `also_in` — the other outlets that ran it — so
the page can print "WSJ · NYT · CNBC" as a citation line.

Two honest limits. Corroboration measures coverage, not importance, and the
two diverge whenever the press is collectively excited. And keywords match
literal substrings, so "rate" also matches "accurate".
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from sources import html_watch, notes, pinterest, rss, shopify

VERSION = "1.0"
ROOT = Path(__file__).parent
DATA = ROOT / "data"
ADAPTERS = {
    "rss": rss.fetch,
    "shopify": shopify.fetch,
    "html": html_watch.fetch,
    "notes": notes.fetch,
    "pinterest": pinterest.fetch,
}

WORD = re.compile(r"[a-z0-9']+")
BOOST_POINTS = 3
STOP = {
    "a", "an", "the", "and", "or", "but", "of", "in", "on", "at", "to", "for",
    "from", "by", "with", "as", "is", "are", "was", "were", "be", "been",
    "it", "its", "this", "that", "these", "those", "he", "she", "they",
    "his", "her", "their", "you", "your", "we", "our", "us", "not", "no",
    "new", "says", "say", "said", "after", "before", "over", "into", "amid",
    "about", "more", "most", "how", "why", "what", "who", "will", "would",
    "can", "could", "may", "might", "has", "have", "had", "up", "down",
    "out", "off", "than", "then", "them", "there", "here", "first", "last",
}


def load_config() -> dict:
    with open(ROOT / "config.yaml") as fh:
        return yaml.safe_load(fh)


def load_json(name: str) -> dict:
    path = DATA / name
    if path.exists():
        try:
            return json.loads(path.read_text())
        except ValueError:
            return {}
    return {}


def item_id(item: dict) -> str:
    basis = item.get("url") or (item.get("source", "") + item.get("title", ""))
    return hashlib.sha1(basis.encode()).hexdigest()[:16]


def muted(title: str, patterns: list[str]) -> bool:
    low = (title or "").lower()
    return any(p.lower() in low for p in patterns or [])


def published_at(item: dict) -> datetime | None:
    raw = item.get("published")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def too_old(item: dict, max_age_hours: int | None, now: datetime) -> bool:
    if not max_age_hours:
        return False
    when = published_at(item)
    if when is None:
        return False
    return when < now - timedelta(hours=max_age_hours)


def sort_key(item: dict) -> str:
    return item.get("published") or item.get("first_seen") or ""


def keywords(title: str) -> set[str]:
    return {w for w in WORD.findall((title or "").lower()) if w not in STOP and len(w) > 2}


def same_story(a: set[str], b: set[str]) -> bool:
    """Overlap coefficient, not Jaccard — headlines vary wildly in length
    and Jaccard punishes that, so real matches score too low to group."""
    if not a or not b:
        return False
    shared = len(a & b)
    return shared >= 2 and shared / min(len(a), len(b)) >= 0.5


def ranked_stories(items: list[dict], boost: list[str], min_outlets: int) -> list[dict]:
    """One entry per story, best first, below-floor stories removed.

    The representative is the earliest-listed source in config order, which
    makes source order an editorial preference rather than a roster.
    """
    boost = [b.lower() for b in boost or []]
    clusters: list[dict] = []
    for item in items:
        keys = keywords(item.get("title", ""))
        for cluster in clusters:
            if same_story(keys, cluster["keys"]):
                cluster["items"].append(item)
                cluster["keys"] |= keys
                break
        else:
            clusters.append({"keys": keys, "items": [item]})

    out = []
    for cluster in clusters:
        outlets = {i.get("source", "") for i in cluster["items"] if i.get("source")}
        lead = cluster["items"][0]
        title = (lead.get("title") or "").lower()
        boosted = any(b in title for b in boost)

        if len(outlets) < min_outlets and not boosted:
            continue

        lead["corroboration"] = len(outlets)
        lead["also_in"] = sorted(o for o in outlets if o != lead.get("source"))
        lead["boosted"] = boosted
        lead["score"] = len(outlets) + (BOOST_POINTS if boosted else 0)
        out.append(lead)

    out.sort(key=lambda i: (i.get("score", 1), sort_key(i)), reverse=True)
    return out


def build(config: dict, probe: bool = False) -> dict:
    settings = config.get("settings", {})
    now = datetime.now(timezone.utc)
    seen = {} if probe else load_json("seen.json")
    archive = {} if probe else load_json("archive.json")
    new_cutoff = now - timedelta(days=settings.get("new_window_days", 4))
    default_limit = settings.get("per_section_limit", 12)
    global_boost = settings.get("boost", [])

    sections, errors, probe_report = [], [], []

    for section in config.get("sections", []):
        collected = []
        max_age = section.get("max_age_hours")
        limit = section.get("limit", default_limit)
        kind = section.get("kind", "headlines")
        boost = section.get("boost", global_boost)
        min_outlets = section.get("min_outlets", 1)

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
            for item in fresh:
                item["_show"] = source.get("show", limit)

            detail = f"{len(fresh)} collected"
            if len(fresh) != len(got):
                detail += f" ({len(got) - len(fresh)} too old)"
            if source.get("_resolved"):
                detail += f"  ← {source['_resolved']}"
            probe_report.append((source.get("name", "?"), "ok" if fresh else "empty", detail))
            collected.extend(fresh)

        deduped: dict[str, dict] = {}
        for item in collected:
            if muted(item.get("title", ""), section.get("mute")):
                continue
            iid = item_id(item)
            item["id"] = iid
            first_seen = seen.get(iid) or now.isoformat()
            seen[iid] = first_seen
            item["first_seen"] = first_seen
            item["is_new"] = datetime.fromisoformat(first_seen) > new_cutoff
            deduped.setdefault(iid, item)

        everything = sorted(deduped.values(), key=sort_key, reverse=True)

        if kind == "goods" and not probe:
            for item in everything:
                archive[item["id"]] = {
                    k: item.get(k)
                    for k in ("title", "url", "source", "image", "price", "published", "first_seen")
                }

        if kind == "headlines":
            candidates = ranked_stories(everything, boost, min_outlets)
        else:
            candidates = everything

        per_source: dict[str, int] = {}
        shown = []
        for item in candidates:
            name = item.get("source", "")
            cap = item.get("_show", limit)
            if per_source.get(name, 0) >= cap:
                continue
            per_source[name] = per_source.get(name, 0) + 1
            shown.append(item)
            if len(shown) >= limit:
                break

        for item in everything:
            item.pop("_show", None)

        sections.append(
            {
                "id": section["id"],
                "title": section["title"],
                "kind": kind,
                "items": shown,
            }
        )

    return {
        "generated_at": now.isoformat(),
        "sections": sections,
        "errors": errors,
        "_seen": seen,
        "_archive": archive,
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
    archive = edition.pop("_archive")
    edition.pop("_probe")
    DATA.mkdir(exist_ok=True)
    (DATA / "feed.json").write_text(json.dumps(edition, indent=1))
    (DATA / "seen.json").write_text(json.dumps(seen))
    (DATA / "archive.json").write_text(json.dumps(archive, indent=1))
    (DATA / "feed.js").write_text("window.__EDITION__ = " + json.dumps(edition) + ";")
    (DATA / "archive.js").write_text("window.__ARCHIVE__ = " + json.dumps(archive) + ";")

    total = sum(len(s["items"]) for s in edition["sections"])
    print(f"Built {total} items across {len(edition['sections'])} sections.")
    print(f"Archive holds {len(archive)} products.")
    for err in edition["errors"]:
        print(f"  ! {err}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
