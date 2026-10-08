"""
Environmental bill feed for regenconsults.com  (v2: categorized)

Pulls environment-related state bills from the Bill Commons public API,
sorts them into eight umbrella categories, keeps the movement status
(status + latest action), flags bills that moved since the last run, and
writes a static JSON file the site's tracker reads.

Run twice a day by .github/workflows/refresh-bills.yml.
No API key needed (anonymous tier). All 50 states + DC by default.
"""

import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone

import requests

# ---------------------------------------------------------------- settings --

API = "https://api.billcommons.org/api/v1/bills"   # q= searches title/description

# Optional comma-separated state codes; empty = all 50 states + DC.
JURISDICTIONS = [s.strip() for s in os.getenv("BILL_STATES", "").split(",") if s.strip()]

MAX_AGE_DAYS = 180          # drop bills with no movement in this many days
PER_CATEGORY = 6            # bills shown per category
PER_STATE_IN_CATEGORY = 2   # spread each category across states when possible
PAGES_PER_QUERY = 2         # 50 results per page
PAUSE_SECONDS = 2.0         # pacing between API calls (anonymous rate limit)
MAX_RETRIES = 3

OUTPUT = os.getenv("BILL_FEED_OUT", "docs/bills.json")

# Each category has:
#   queries  - search terms sent to the API
#   patterns - regexes; a bill joins the category only if its TITLE matches one
#   exclude  - regexes that disqualify a title for this category only
# Order matters only for ties: a bill matching two categories equally goes to
# the one listed first.
CATEGORIES = [
    {
        "slug": "clean-energy",
        "name": "Clean Energy",
        "queries": ["renewable energy", "clean energy", "solar", "wind energy",
                    "energy storage", "net metering"],
        "patterns": [r"renewable energ", r"clean energy", r"\bsolar\b", r"photovoltaic",
                     r"\bwind (energy|power|turbine|farm|facilit|project|generation)",
                     r"offshore wind", r"energy storage", r"battery storage",
                     r"net metering", r"geothermal", r"distributed (generation|energy)",
                     r"zero[- ]carbon (electric|energy|resource)"],
        "exclude": [],
    },
    {
        "slug": "grid",
        "name": "Grid & Energy Affordability",
        "queries": ["electric grid", "transmission", "ratepayer", "utility rates",
                    "interconnection"],
        "patterns": [r"\bgrid\b", r"\btransmission (line|infrastructure|facilit|project|siting|planning|system)",
                     r"\bratepayer", r"\b(utility|electric|electricity|energy) (rate|bill|cost)s?\b",
                     r"energy affordab", r"energy burden", r"load forecast",
                     r"\binterconnection\b", r"resource adequacy", r"\bmicrogrid"],
        "exclude": [],
    },
    {
        "slug": "buildings",
        "name": "Green & Healthy Buildings",
        "queries": ["green building", "energy efficiency", "energy code", "heat pump",
                    "building electrification", "embodied carbon", "weatherization"],
        "patterns": [r"green building", r"energy efficien", r"energy (conservation )?code",
                     r"building energy", r"heat pump", r"building electrification",
                     r"\belectrification\b", r"embodied carbon", r"building performance",
                     r"weatheriz", r"healthy (building|home|housing)",
                     r"low[- ]carbon (concrete|cement|material|building)",
                     r"(building|construction) material.*(carbon|toxic|healthy|sustainab)",
                     r"\bnet[- ]zero (building|home|energy)"],
        "exclude": [r"tax: exemptions?; exemption for building materials"],
    },
    {
        "slug": "transportation",
        "name": "Clean Transportation",
        "queries": ["electric vehicle", "zero-emission vehicle", "public transit",
                    "transit", "electric bus"],
        "patterns": [r"electric vehicle", r"\bEVs?\b", r"charging station",
                     r"zero[- ]emission [a-z ]{0,20}(vehicle|bus|truck|fleet)", r"electric (school )?bus",
                     r"public transit", r"mass transit", r"public transportation",
                     r"\btransit (authority|agency|district|system|service|fund|capital|operat)",
                     r"transit[- ]oriented", r"bus rapid transit", r"passenger rail",
                     r"vehicle electrification"],
        "exclude": [r"employee", r"\blabor\b", r"collective bargaining", r"\bpolice\b",
                    r"commercial code"],
    },
    {
        "slug": "climate",
        "name": "Climate & Emissions",
        "queries": ["climate", "emissions", "greenhouse gas", "air quality", "methane"],
        "patterns": [r"\bclimate\b", r"\bemissions?\b", r"greenhouse gas",
                     r"\bcarbon (dioxide|capture|pollution|reduction|neutral|free|sequestration|intensity)",
                     r"air quality", r"air pollut", r"\bmethane\b", r"cap[- ]and[- ](trade|invest)",
                     r"short[- ]lived climate"],
        "exclude": [r"climate[- ]controlled", r"(campus|school|workplace|business|investment) climate",
                    r"climate survey"],
    },
    {
        "slug": "waste",
        "name": "Waste & Circular Economy",
        "queries": ["solid waste", "recycling", "waste management",
                    "producer responsibility", "packaging", "compost"],
        "patterns": [r"solid waste", r"recycl", r"waste (management|reduction|diversion|disposal|hauling)",
                     r"\blandfill", r"compost", r"producer responsibility",
                     r"packaging (waste|reduction|material|producer|recycl|stewardship)",
                     r"(plastic|sustainable|reusable|compostable) packaging",
                     r"single[- ]use plastic", r"plastic (bag|waste|pollution|product)",
                     r"organic waste", r"food waste", r"hazardous waste", r"circular economy"],
        "exclude": [r"labor dispute"],
    },
    {
        "slug": "water-land",
        "name": "Water & Land",
        "queries": ["conservation", "stormwater", "water quality", "wetlands",
                    "drinking water"],
        "patterns": [r"\bconservation\b", r"stormwater", r"water quality", r"wetland",
                     r"watershed", r"clean water", r"drinking water", r"groundwater",
                     r"\bPFAS\b", r"\bhabitat\b", r"open space", r"land trust",
                     r"\bforest (health|management|conservation|carbon)"],
        "exclude": [],
    },
    {
        "slug": "equity",
        "name": "Environmental Equity",
        "queries": ["environmental justice", "environmental equity", "energy equity",
                    "overburdened communities", "disadvantaged communities"],
        "patterns": [r"environmental justice", r"environmental equity", r"energy equity",
                     r"clean energy equity", r"overburdened", r"disadvantaged communit",
                     r"frontline communit", r"climate justice", r"energy justice"],
        "exclude": [],
    },
]

# Agency and commission names that contain topic words but say nothing about
# the bill's subject. Removed from the title before matching, so "Department
# of Environmental Conservation" doesn't make a bill a conservation bill, while
# "Requires DEC to regulate recycling facilities" still counts as waste.
AGENCY_NAMES = [
    r"department of environmental conservation",
    r"energy resources conservation and development commission",
    r"conservation commission",
    r"department of (natural resources and )?conservation( and recreation)?",
    r"conservation use (property|assessment|valuation)",
    r"massachusetts clean energy center",
    r"clean energy center",
    r"greenhouse gas reduction fund",
]

# Items that aren't policy bills at all.
GLOBAL_EXCLUDE = [
    r"^\s*(a )?communication from",
    r"\bcommunication from the\b",
    r"specialty license plate",
    r"financial statements?",
    r"emissions? reduction statement",
    r"sick leave bank",
    r"^\s*(annual |quarterly )?report (of|on|from)\b",
    r"reimbursable agreement",            # e.g. DC WMATA station/funding agreements
    r"funding grant agreement",
]

STATUS_LABELS = {
    "introduced": "Introduced",
    "in_committee": "In committee",
    "passed_chamber": "Passed one chamber",
    "passed_one_chamber": "Passed one chamber",
    "passed_both": "Passed legislature",
    "passed_legislature": "Passed legislature",
    "sent_to_governor": "Sent to governor",
    "enacted": "Enacted",
    "vetoed": "Vetoed",
    "killed": "Failed",
    "dead": "Failed",
    "died_on_adjournment": "Died on adjournment",
    "withdrawn": "Withdrawn",
    "substituted": "Replaced by companion bill",
}

BADGE_DAYS = 3  # how long a "New" / "Moved" badge stays on a bill

# ------------------------------------------------------------------ compile --

_FLAGS = re.IGNORECASE
for c in CATEGORIES:
    # \bEVs?\b is the one pattern that must stay case-sensitive ("ev" is common).
    c["_patterns"] = [re.compile(p) if p == r"\bEVs?\b" else re.compile(p, _FLAGS)
                      for p in c["patterns"]]
    c["_exclude"] = [re.compile(p, _FLAGS) for p in c["exclude"]]
_AGENCIES = [re.compile(p, _FLAGS) for p in AGENCY_NAMES]
_GLOBAL_EXCLUDE = [re.compile(p, _FLAGS) for p in GLOBAL_EXCLUDE]
_BY_SLUG = {c["slug"]: c for c in CATEGORIES}


def categorize(title):
    """Return the best-matching category slug for a bill title, or None."""
    title = title or ""
    if any(p.search(title) for p in _GLOBAL_EXCLUDE):
        return None
    cleaned = title
    for p in _AGENCIES:
        cleaned = p.sub(" ", cleaned)

    best, best_score = None, 0
    for c in CATEGORIES:
        if any(p.search(cleaned) for p in c["_exclude"]):
            continue
        score = sum(1 for p in c["_patterns"] if p.search(cleaned))
        if score > best_score:  # strict ">" keeps the earlier category on ties
            best, best_score = c["slug"], score
    return best


# ------------------------------------------------------------------ fetch --


def get(session, params):
    for attempt in range(MAX_RETRIES + 1):
        r = session.get(API, params=params, timeout=30)
        if r.status_code == 429 or r.status_code >= 500:
            if attempt == MAX_RETRIES:
                r.raise_for_status()
            wait = int(r.headers.get("Retry-After", "0") or 0) or 30 * (attempt + 1)
            print(f"  ... {r.status_code}, waiting {wait}s", file=sys.stderr)
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()


def collect(session, cutoff):
    """Run every category query; return {bill_id: bill} for recent bills."""
    found, errors, calls = {}, 0, 0
    for state in JURISDICTIONS or [None]:
        for c in CATEGORIES:
            for q in c["queries"]:
                for page in range(1, PAGES_PER_QUERY + 1):
                    params = {"q": q, "per_page": 50, "page": page}
                    if state:
                        params["jurisdiction"] = state
                    try:
                        payload = get(session, params)
                    except requests.RequestException as e:
                        errors += 1
                        print(f"  ! {state or 'ALL'} '{q}' p{page}: {e}", file=sys.stderr)
                        break
                    finally:
                        calls += 1
                        time.sleep(PAUSE_SECONDS)

                    rows = payload.get("data", [])
                    for bill in rows:
                        d = parse_date(bill.get("latest_action_date"))
                        if d and d >= cutoff:
                            found[bill["id"]] = bill

                    # Results arrive newest-first; stop once a page is all old.
                    dates = [parse_date(b.get("latest_action_date")) for b in rows]
                    dates = [d for d in dates if d]
                    pg = payload.get("pagination", {})
                    if (not rows or (dates and max(dates) < cutoff)
                            or pg.get("page", 1) >= pg.get("total_pages", 1)):
                        break
    return found, errors, calls


# ---------------------------------------------------------------- shaping --


def parse_date(s):
    try:
        return date.fromisoformat(s[:10]) if s else None
    except (ValueError, TypeError):
        return None


def status_label(bill):
    s = bill.get("status")
    if s:
        return STATUS_LABELS.get(s, s.replace("_", " ").capitalize())
    return "In progress"


def shape(b, slug, today):
    action_date = parse_date(b.get("latest_action_date"))
    cat = _BY_SLUG[slug]
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
        "upcoming": bool(action_date and action_date > today),
        "introduced": b.get("introduced_date"),
        "url": b.get("source_url"),
        "category": slug,
        "category_name": cat["name"],
        "topics": [cat["name"]],  # kept so the previous embed still works
    }


def norm_title(t):
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def load_previous(path):
    try:
        with open(path, encoding="utf-8") as f:
            return {b["id"]: b for b in json.load(f).get("bills", [])}
    except (OSError, ValueError, KeyError):
        return {}


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

    changed_on = parse_date(old.get("changed_on"))
    item["changed_on"] = old.get("changed_on")
    if changed_on and (today - changed_on).days < BADGE_DAYS:
        item["change"] = old.get("change")
        if old.get("previous_status_label"):
            item["previous_status_label"] = old["previous_status_label"]
    else:
        item["change"] = None
    return item


def recency_key(item, today):
    d = parse_date(item["latest_action_date"]) or date.min
    # Future-dated actions (effective dates, scheduled hearings) sort as today.
    return min(d, today)


def pick(items, today):
    """Up to PER_CATEGORY per category, newest first, spread across states."""
    items = sorted(items, key=lambda i: recency_key(i, today), reverse=True)
    chosen = []
    for c in CATEGORIES:
        pool = [i for i in items if i["category"] == c["slug"]]
        picked, per_state = [], {}
        for i in pool:  # first pass: respect the per-state limit
            if len(picked) >= PER_CATEGORY:
                break
            if per_state.get(i["state"], 0) < PER_STATE_IN_CATEGORY:
                picked.append(i)
                per_state[i["state"]] = per_state.get(i["state"], 0) + 1
        for i in pool:  # second pass: fill any open slots
            if len(picked) >= PER_CATEGORY:
                break
            if i not in picked:
                picked.append(i)
        picked.sort(key=lambda i: recency_key(i, today), reverse=True)
        chosen.extend(picked)
    return chosen


def build_feed(found, prev, today):
    items, seen_titles = [], {}
    for b in sorted(found.values(), key=lambda b: b.get("latest_action_date") or "", reverse=True):
        slug = categorize(b.get("title"))
        if not slug:
            continue
        # Companion bills (same title, same state and session) show once.
        key = (b.get("jurisdiction_abbreviation"), b.get("session_identifier"), norm_title(b.get("title")))
        if key in seen_titles:
            continue
        seen_titles[key] = True
        items.append(shape(b, slug, today))

    feed = pick(items, today)
    for i in feed:
        mark_movement(i, prev, today)
    if not prev:  # first run: don't badge everything as "New"
        for i in feed:
            i["change"] = None
    return feed, items


# ------------------------------------------------------------------- main --


def main():
    today = datetime.now(timezone.utc).date()
    cutoff = today - timedelta(days=MAX_AGE_DAYS)
    prev = load_previous(OUTPUT)

    with requests.Session() as s:
        s.headers["User-Agent"] = "regenconsults-bill-feed/2.0 (+https://www.regenconsults.com)"
        found, errors, calls = collect(s, cutoff)

    bills, matched = build_feed(found, prev, today)
    counts = {c["slug"]: sum(1 for b in bills if b["category"] == c["slug"]) for c in CATEGORIES}
    print(f"{calls} API calls, {errors} errors, {len(found)} recent bills, "
          f"{len(matched)} categorized, {len(bills)} in feed")
    for c in CATEGORIES:
        print(f"  {c['name']:<30} {counts[c['slug']]}")

    # If the API was down, keep the previous feed rather than publishing an empty one.
    if not bills:
        print("No results; leaving the existing feed in place.", file=sys.stderr)
        return 1 if errors else 0

    feed = {
        "version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "states": JURISDICTIONS or "all",
        "categories": [{"slug": c["slug"], "name": c["name"], "count": counts[c["slug"]]}
                       for c in CATEGORIES],
        "attribution": "Bill data via Bill Commons (billcommons.org), sourced from official state legislative records and Open States.",
        "bills": bills,
    }

    os.makedirs(os.path.dirname(OUTPUT) or ".", exist_ok=True)
    tmp = OUTPUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(feed, f, indent=1, ensure_ascii=False)
    os.replace(tmp, OUTPUT)
    print(f"Wrote {len(bills)} bills to {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
