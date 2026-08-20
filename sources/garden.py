"""The garden calendar — zone 5b, Saratoga Springs.

Makes no network calls. The fortnight's task, the crops going in and the
reading are all decided by today's date, which makes this the only section
on the page that cannot fail.

Anchors, all conservative:
    last spring frost   mid-May (averages range 11–20 May)
    tender crops        after 25 May, soil above 60°
    frost risk opens    16 September
    average first frost 1 October

Two halves per month rather than weeks: garden timing isn't that precise,
and a fortnight is roughly how long a sowing window stays open.
"""

from __future__ import annotations

from datetime import date

ZONE = "Zone 5b"
FROST_OPENS = (9, 16)  # when the risk starts, not the 50% date — err early

MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")

# (month, half) -> the fortnight. half 0 is the 1st to the 15th.
#   task    the headline, an imperative
#   dek     one sentence of why or how
#   plant   list of (method, crops); method is direct | indoors | out
#   read    list of (source, title, url) — verified to resolve
CALENDAR: dict[tuple[int, int], dict] = {
    (1, 0): {
        "task": "Order seed.",
        "dek": "Catalogues are in and the good varieties sell out first. "
               "Order alliums ahead of everything else — they're sown before winter ends.",
        "plant": [],
        "read": [("Margaret Roach", "The January garden chores",
                  "https://awaytogarden.com/the-january-garden-chores/")],
    },
    (1, 1): {
        "task": "Start the alliums.",
        "dek": "Ten to twelve weeks ahead of an April planting out. "
               "The first sowing of the year.",
        "plant": [("indoors", "onions · shallots")],
        "read": [("Margaret Roach", "How to grow shallots, with Ken Greene",
                  "https://awaytogarden.com/how-to-grow-shallots-some-late-season-succession-tips-with-k-greene/")],
    },
    (2, 0): {
        "task": "Send a soil test off.",
        "dek": "Results take weeks, which is why now. A pH reading tells you what "
               "to amend before the beds are wet and full.",
        "plant": [("indoors", "artichoke")],
        "read": [("Margaret Roach", "The February garden chores",
                  "https://awaytogarden.com/the-february-garden-chores/")],
    },
    (2, 1): {
        "task": "Start peppers and eggplant.",
        "dek": "Eight to ten weeks before mid-May, on a heat mat. "
               "Started in late March they never catch up.",
        "plant": [("indoors", "hot peppers · eggplant")],
        "read": [],
    },
    (3, 0): {
        "task": "Start the brassicas.",
        "dek": "Six weeks before they go out under cover in mid-April.",
        "plant": [("indoors", "broccoli · cabbage · cauliflower · kale · head lettuce")],
        "read": [("Margaret Roach", "How to grow brassicas, with Steve Bellavia",
                  "https://awaytogarden.com/how-to-grow-brassicas-with-steve-bellavia/"),
                 ("Margaret Roach", "The March garden chores",
                  "https://awaytogarden.com/the-march-garden-chores/")],
    },
    (3, 1): {
        "task": "First sowing under cover.",
        "dek": "If the soil is workable and holding 40°. "
               "There's no prize for being early into cold mud.",
        "plant": [("direct", "spinach · arugula · radish"),
                  ("indoors", "more lettuce")],
        "read": [("Margaret Roach", "Growing under cover, with Paul Gallione",
                  "https://awaytogarden.com/growing-under-cover-tips-from-paul-gallione/"),
                 ("Margaret Roach", "Cold-frame 101, with Niki Jabbour",
                  "https://awaytogarden.com/cold-frame-101-with-niki-jabbour/")],
    },
    (4, 0): {
        "task": "Peas in, asparagus crowns down.",
        "dek": "Crowns go in a trench as soon as the ground is workable — then you "
               "leave them alone for two years, which is the whole discipline of asparagus.",
        "plant": [("direct", "peas · spinach · radish · fava beans"),
                  ("indoors", "tomatoes · tomatillos · zinnia"),
                  ("out", "onions · asparagus crowns")],
        "read": [("Margaret Roach", "Asparagus: an all-male cast",
                  "https://awaytogarden.com/asparagus-an-all-male-cast/")],
    },
    (4, 1): {
        "task": "The main cold sowing.",
        "dek": "Soil at 40–45°. Check it before you trust the date. Start Brussels now, "
               "not in March — sown too early they head up in September heat.",
        "plant": [("direct", "carrots · beets · chard · lettuce · kohlrabi · potatoes"),
                  ("indoors", "Brussels sprouts"),
                  ("out", "broccoli · cabbage · kale, under cover")],
        "read": [],
    },
    (5, 0): {
        "task": "Harden off, don't plant out.",
        "dek": "Nights still fall below 40°, and soil lags air by a good while. "
               "Cucurbits get three weeks in pots and no more.",
        "plant": [("direct", "more carrots · beets · lettuce · dill"),
                  ("indoors", "cucumber · summer squash · melon")],
        "read": [("Margaret Roach", "The May garden chores",
                  "https://awaytogarden.com/may-garden-chores2/")],
    },
    (5, 1): {
        "task": "Tender crops after the 25th.",
        "dek": "Tomatoes at 60°; hot peppers and eggplant want 65° and sulk below it. "
               "Sweetcorn wants a block rather than a row or it won't pollinate.",
        "plant": [("out", "tomatoes · hot peppers · eggplant · zinnia · sage · thyme · tarragon · rosemary"),
                  ("direct", "beans at 55° · sweetcorn · sunflowers")],
        "read": [],
    },
    (6, 0): {
        "task": "Squash and sweet potato into warm ground.",
        "dek": "Butternut and pumpkins in by the 10th — 110 days against an October frost. "
               "Sweet potato slips once soil holds 65°.",
        "plant": [("direct", "delicata · butternut · pumpkins · cucumbers · summer squash · melons · beans"),
                  ("out", "cucurbit starts · Brussels sprouts · sweet potato slips")],
        "read": [("Margaret Roach", "How to grow squash and other cucurbits, with Tom Stearns",
                  "https://awaytogarden.com/how-to-grow-squash-cucumbers-and-other-cucurbits-with-tom-stearns/"),
                 ("Margaret Roach", "The June garden chores",
                  "https://awaytogarden.com/june-garden-chores-2/")],
    },
    (6, 1): {
        "task": "Mulch, stake, and cover the squash.",
        "dek": "Cover goes on against vine borer and comes off the moment female "
               "flowers open, or nothing gets pollinated.",
        "plant": [("direct", "succession beans · heat-tolerant lettuce · carrots for autumn · dill")],
        "read": [("Margaret Roach", "Squash bugs and other squash problems, with Diane Alston",
                  "https://awaytogarden.com/squash-bugs-and-other-squash-problems-with-diane-alston-of-utah-state/")],
    },
    (7, 0): {
        "task": "Water deeply and sow the next round.",
        "dek": "An inch a week at the base, not a daily sprinkle — shallow watering "
               "grows shallow roots.",
        "plant": [("direct", "beans · a second summer squash · a second cucumber · beets · carrots"),
                  ("indoors", "fall broccoli · cabbage · kale · napa cabbage, somewhere cool")],
        "read": [("Margaret Roach", "Vegetable successions and edible cover crops, with Doug Muller",
                  "https://awaytogarden.com/vegetable-successions-and-edible-cover-crops-with-doug-muller/"),
                 ("Margaret Roach", "The July garden chores",
                  "https://awaytogarden.com/july-garden-chores-2/")],
    },
    (7, 1): {
        "task": "Last beans, first fall brassicas.",
        "dek": "Around the 20th is the last useful bush bean sowing — after that they "
               "flower into cold and set nothing.",
        "plant": [("direct", "bush beans until ~20th · fall carrots · beets · chard · bok choy"),
                  ("out", "fall broccoli · cabbage · kale")],
        "read": [("Margaret Roach", "What to plant now for a fall vegetable garden",
                  "https://awaytogarden.com/what-to-plant-now-for-a-fall-vegetable-garden/")],
    },
    (8, 0): {
        "task": "Watch the leaves, sow the greens.",
        "dek": "Late blight on tomatoes and powdery mildew on squash both arrive on "
               "humid nights. Strip lower leaves and water at the base.",
        "plant": [("direct", "spinach · lettuce · arugula · radish · mustard greens · bok choy · kale"),
                  ("out", "napa cabbage")],
        "read": [("Margaret Roach", "My August garden chores",
                  "https://awaytogarden.com/my-august-garden-chores/")],
    },
    (8, 1): {
        "task": "Last call for fall greens.",
        "dek": "Only the fast ones now — anything over 45 days won't finish. "
               "Order garlic for October planting.",
        "plant": [("direct", "spinach · arugula · radish · mustard greens · baby lettuce")],
        "read": [("Margaret Roach", "What to plant now for a fall vegetable garden",
                  "https://awaytogarden.com/what-to-plant-now-for-a-fall-vegetable-garden/"),
                 ("Margaret Roach", "Growing and storing a year of garlic",
                  "https://awaytogarden.com/growing-and-storing-a-year-of-garlic/")],
    },
    (9, 0): {
        "task": "Cover crops as beds empty.",
        "dek": "Oats and field peas winter-kill cleanly, so there's nothing to dig in "
               "come spring. Rye survives, but you'll be dealing with it in April.",
        "plant": [("direct", "oats · field peas · spinach under cover")],
        "read": [("Margaret Roach", "Cover crops: feeding the soil that feeds me",
                  "https://awaytogarden.com/cover-crops-feeding-the-soil-that-feeds-me/")],
    },
    (9, 1): {
        "task": "Frost risk opens — bring things in.",
        "dek": "Cut winter squash before the first frost, leave a few inches of stem, "
               "cure it warm for ten days. Lift sweet potato. Rosemary comes indoors.",
        "plant": [("direct", "winter rye · overwintering spinach under cover")],
        "read": [("Margaret Roach", "Winter squash, from garden to table, with Kevin West",
                  "https://awaytogarden.com/winter-squash-from-garden-to-table-with-kevin-west/")],
    },
    (10, 0): {
        "task": "Plant garlic.",
        "dek": "Cloves three inches deep, pointed end up, mulched once the soil is cold. "
               "Two to three weeks before the ground freezes.",
        "plant": [("direct", "garlic · shallot sets · last window for winter rye")],
        "read": [("Margaret Roach", "How to grow garlic, a Q&A with Filaree Farm",
                  "https://awaytogarden.com/how-to-grow-garlic-a-qa-with-filaree-farm-and-win-their-classic-book-on-my-favorite-allium/")],
    },
    (10, 1): {
        "task": "Put the beds to bed.",
        "dek": "Pull spent annuals, mulch anything left bare, and lift the row covers "
               "before snow takes the hoops down with them.",
        "plant": [],
        "read": [("Margaret Roach", "Fall garden tips, from cleanup to composting, with Lee Reich",
                  "https://awaytogarden.com/fall-garden-tips-from-cleanup-to-composting-to-fig-tree-storage-from-lee-reich/")],
    },
    (11, 0): {
        "task": "Mulch after the ground freezes.",
        "dek": "Not before. Mulch laid on warm soil is an invitation to voles, who will "
               "spend the winter eating the garlic.",
        "plant": [],
        "read": [("Margaret Roach", "Fall pest patrol: deer, cabbage worms, squash bugs, voles",
                  "https://awaytogarden.com/fall-pest-patrol-work-now-to-foil-deer-cabbage-worms-viburnum-beetle-squash-bugs-voles/")],
    },
    (11, 1): {
        "task": "Cut the asparagus down, turn the compost.",
        "dek": "Cut the ferns once they've yellowed and not before — they're feeding the "
               "crowns until then. Brussels are sweeter now; frost does that.",
        "plant": [],
        "read": [("Margaret Roach", "Growing, cooking and stashing asparagus: 12 don'ts",
                  "https://awaytogarden.com/growing-cooking-stashing-asparagus-12-donts/")],
    },
    (12, 0): {
        "task": "Check what's stored.",
        "dek": "Squash, onions, potatoes and sweet potato. Pull anything soft before it "
               "takes the crate with it.",
        "plant": [],
        "read": [("Margaret Roach", "How to store garden vegetables for winter",
                  "https://awaytogarden.com/how-to-store-garden-vegetables-for-winter/")],
    },
    (12, 1): {
        "task": "Plan the rotation.",
        "dek": "Brassicas off last year's brassica bed, alliums off the garlic, cucurbits "
               "somewhere new. Nothing to do outside, which is the point.",
        "plant": [],
        "read": [],
    },
}


def _fortnight(today: date) -> tuple[int, int]:
    return (today.month, 0 if today.day <= 15 else 1)


def _label(key: tuple[int, int]) -> str:
    month, half = key
    return f"{'1–15' if half == 0 else '16–' + ('30' if month in (4, 6, 9, 11) else '28' if month == 2 else '31')} {MONTHS[month - 1]}"


def _days_to_frost(today: date) -> int | None:
    """Days until frost risk opens, or None when it's too far off to matter."""
    year = today.year if (today.month, today.day) <= FROST_OPENS else today.year + 1
    days = (date(year, *FROST_OPENS) - today).days
    return days if 0 < days <= 60 else None


def fetch(source: dict, settings: dict) -> list[dict]:
    today = date.today()
    key = _fortnight(today)
    entry = CALENDAR.get(key)
    if not entry:
        return []

    kicker = f"{source.get('zone', ZONE)} · {_label(key)}"
    days = _days_to_frost(today)
    if days is not None:
        kicker += f" · {days} days to first frost"

    read = [{"source": s, "title": t, "url": u} for s, t, u in entry["read"]]

    return [{
        "title": entry["task"],
        "summary": entry["dek"],
        "kicker": kicker,
        "plantings": [{"method": m, "crops": c} for m, c in entry["plant"]],
        "reading": read,
        # The first piece of reading is where the block links, if anywhere.
        "url": read[0]["url"] if read else "",
        "source": source.get("zone", ZONE),
        "kind": "garden",
    }]
