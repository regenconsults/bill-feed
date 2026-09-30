"""
Environmental bill feed for regenconsults.com.

Pulls environment-related state bills from the Bill Commons public API,
keeps the movement status (status + latest action), flags bills that moved
since the last run, and writes a static JSON file your site can read.

Run twice a day by .github/workflows/refresh-bills.yml.
No API key needed (anonymous tier: 60 requests/minute per IP).
"""

import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone

import requests

# ---------------------------------------------------------------- settings --

API = "https://api.billcommons.org/api/v1/search"

# Search terms. Each one costs 1-2 API calls per state per run.
KEYWORDS = [
    "renewable energy",
    "climate",
    "emissions",
    "conservation",
    "clean energy",
    "solar",
    "stormwater",
    "green building",
    "energy efficiency",
    "environmental justice",
]

# Two-letter state codes, e.g. ["NC", "SC", "VA"]. Empty list = all 50 states + DC.
JURISDICTIONS = [s for s in os.getenv("BILL_STATES", "").split(",") if s.strip()]

# Only keep bills whose TITLE contains one of the keywords. Full-text search
# otherwise pulls in unrelated bills that mention a term once in the body
# (e.g. a consumer-protection act that matches "renewable energy").
REQUIRE_TITLE_MATCH = True

# Drop bills with no movement in this many days.
MAX_AGE_DAYS = 180

# How many bills end up in the feed.
FEED_SIZE = 40

PAGES_PER_QUERY = 4      # 50 results per page; deeper paging for nationwide coverage
PAUSE_SECONDS = 1.1      # stays under 60 requests/minute

OUTPUT = os.getenv("BILL_FEED_OUT", "docs/bills.json")

STATUS_LABELS = {
    "introduced": "Introduced",
    "in_committee": "In committee",
    "passed_chamber": "Passed one chamber",
    "passed_legislature": "Passed legislature",
    "sent_to_governor": "Sent to governor",
    "enacted": "Enacted",
    "vetoed": "Vetoed",
    "killed": "Failed",
    "died_on_adjournment": "Died on adjournment",
}

# ------------------------------------------------------------------ fetch --


def search(session, q, jurisdiction, page):
    params = {"q": q, "per_page": 50, "page": page}
    if jurisdiction:
        params["jurisdiction"] = jurisdiction
    r = session.get(API, params=params, timeout=20)
    if r.status_code == 429:  # rate limited: wait and retry once
        time.sleep(int(r.headers.get("Retry-After", "30")))
        r = session.get(API, params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def collect(session):
    found, errors, calls = {}, 0, 0
    for state in JURISDICTIONS or [None]:
        for kw in KEYWORDS:
            for page in range(1, PAGES_PER_QUERY + 1):
                try:
                    payload = search(session, kw, state, page)
                except requests.RequestException as e:
                    errors += 1
                    print(f"  ! {state or 'ALL'} '{kw}' p{page}: {e}", file=sys.stderr)
                    break
                finally:
                    calls += 1
                    time.sleep(PAUSE_SECONDS)

                for bill in payload.get("data", []):
                    # "browse" means the API ignored the query; skip those rows.
                    if bill.get("match_type") == "browse":
                        continue
                    if REQUIRE_TITLE_MATCH and kw.lower() not in (bill.get("title") or "").lower():
                        continue
                    entry = found.setdefault(bill["id"], {"bill": bill, "topics": set()})
                    entry["topics"].add(kw)

                pg = payload.get("pagination", {})
                if pg.get("page", 1) >= pg.get("total_pages", 1):
                    break
    return found, errors, calls


# ---------------------------------------------------------------- shaping --


def parse_date(s):
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def status_label(bill):
    s = bill.get("status")
    if s:
        return STATUS_LABELS.get(s, s.replace("_", " ").capitalize())
    return "In progress"


def shape(entry, today):
    b = entry["bill"]
    action_date = parse_date(b.get("latest_action_date"))
    return {
        "id": b["id"],
        "state": b.get("jurisdiction_abbreviation"),
        "bill": b.get("identifier"),
        "title": b.get("short_title") or b.get("title"),
        "session": b.get("session_identifier"),
        "status": b.get("status"),
        "status_label": status_label(b),
        "latest_action": b.get("latest_action_text"),
        "latest_action_date": b.get("latest_action_date"),
        # Some actions carry future dates (hearings, effective dates).
        "upcoming": bool(action_date and action_date > today),
        "introduced": b.get("introduced_date"),
        "url": b.get("source_url"),  # official legislature page
        "topics": sorted(entry["topics"]),
    }


def load_previous(path):
    try:
        with open(path, encoding="utf-8") as f:
            return {b["id"]: b for b in json.load(f).get("bills", [])}
    except (OSError, ValueError, KeyError):
        return {}


BADGE_DAYS = 3  # how long a "New" / "Moved" badge stays on a bill


def mark_movement(item, prev, today):
    """Tag each bill as new, moved since the last run, or unchanged."""
    old = prev.get(item["id"])
    if old is None:
        item.update(change="new", changed_on=today.isoformat(), first_seen=today.isoformat())
        return item

    item["first_seen"] = old.get("first_seen") or today.isoformat()
    moved = (old.get("status"), old.get("latest_action"), old.get("latest_action_date")) != (
        item["status"], item["latest_action"], item["latest_action_date"]
    )
    if moved:
        item.update(change="moved", changed_on=today.isoformat(),
                    previous_status_label=old.get("status_label"))
        return item

    # Unchanged since last run: keep a recent badge for a few days, then drop it.
    changed_on = parse_date(old.get("changed_on"))
    item["changed_on"] = old.get("changed_on")
    if changed_on and (today - changed_on).days < BADGE_DAYS:
        item["change"] = old.get("change")
        if old.get("previous_status_label"):
            item["previous_status_label"] = old["previous_status_label"]
    else:
        item["change"] = None
    return item


def build_feed(found, prev, today):
    cutoff = today - timedelta(days=MAX_AGE_DAYS)
    items = []
    for entry in found.values():
        item = shape(entry, today)
        d = parse_date(item["latest_action_date"])
        if d is None or d < cutoff:
            continue
        items.append(mark_movement(item, prev, today))

    # First ever run: don't badge everything as "New".
    if not prev:
        for i in items:
            i["change"] = None

    # Newest movement first; future-dated actions sort as "today" so an
    # effective date in 2028 doesn't pin itself to the top forever.
    def key(i):
        d = parse_date(i["latest_action_date"])
        return (min(d, today), i["change"] is not None)

    items.sort(key=key, reverse=True)
    return items[:FEED_SIZE]


# ------------------------------------------------------------------- main --


def main():
    today = datetime.now(timezone.utc).date()
    prev = load_previous(OUTPUT)

    with requests.Session() as s:
        s.headers["User-Agent"] = "regenconsults-bill-feed/1.0 (+https://www.regenconsults.com)"
        found, errors, calls = collect(s)

    print(f"{calls} API calls, {errors} errors, {len(found)} matching bills")

    # If the API was down, keep yesterday's feed rather than publishing an empty one.
    if not found:
        print("No results; leaving the existing feed in place.", file=sys.stderr)
        return 1 if errors else 0

    feed = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "states": JURISDICTIONS or "all",
        "keywords": KEYWORDS,
        "attribution": "Bill data via Bill Commons (billcommons.org), sourced from official state legislative records and Open States.",
        "bills": build_feed(found, prev, today),
    }

    os.makedirs(os.path.dirname(OUTPUT) or ".", exist_ok=True)
    tmp = OUTPUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(feed, f, indent=1, ensure_ascii=False)
    os.replace(tmp, OUTPUT)
    print(f"Wrote {len(feed['bills'])} bills to {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
