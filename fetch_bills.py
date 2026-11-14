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
#   patterns - regexes; a bill gets the category if its TITLE matches one
#   exclude  - regexes that disqualify a title for this category only
# A bill gets every category it matches (shown as tags). Its primary category,
# used to pick which bills make the feed, is the one with the most matching
# patterns; ties go to the category listed first. List order is also the
# order the chips appear on the site.
#
# Categories are an editorial suggestion made from the title only; they are
# not a fact from the legislature. See docs/category-taxonomy.md.
CATEGORIES = [
    {
        "slug": "building-energy",
        "name": "Building & Energy",
        "queries": ["green building", "energy efficiency", "energy code", "heat pump",
                    "building electrification", "weatherization", "net metering",
                    "community solar"],
        "patterns": [r"green building", r"energy efficien", r"energy (conservation )?code",
                     r"building (energy|code)", r"heat pump", r"building electrification",
                     r"\belectrification\b", r"embodied carbon", r"building performance",
                     r"weatheriz", r"healthy (building|home|housing)",
                     r"low[- ]carbon (building|construction)",
                     r"\bnet[- ]zero (building|home|energy)",
                     r"net metering", r"distributed (generation|energy)",
                     r"(rooftop|residential|community) solar", r"solar (panel|energy system)s? (on|for) (home|residen|building|school)",
                     r"benchmarking", r"residential (clean|renewable) energy"],
        "exclude": [r"tax: exemptions?; exemption for building materials"],
    },
    {
        "slug": "climate-emissions",
        "name": "Climate & Emissions",
        "queries": ["climate", "emissions", "greenhouse gas", "air quality", "methane",
                    "decarbonization"],
        # "zero-emission" (vehicles, buses) is left to Infrastructure & Resilience.
        "patterns": [r"\bclimate\b", r"(?<!zero[- ])\bemissions?\b", r"greenhouse gas",
                     r"\bcarbon (dioxide|capture|pollution|reduction|neutral|free|sequestration|intensity)",
                     r"air quality", r"air pollut", r"\bmethane\b", r"cap[- ]and[- ](trade|invest)",
                     r"short[- ]lived climate", r"decarboni[sz]", r"\bozone\b", r"new source review",
                     r"clean air act",
                     r"zero[- ]carbon", r"renewable portfolio", r"clean (energy|electricity) standard"],
        "exclude": [r"climate[- ]controlled", r"(campus|school|workplace|business|investment) climate",
                    r"climate survey"],
    },
    {
        "slug": "water-resources",
        "name": "Water Resources",
        "queries": ["stormwater", "water quality", "drinking water", "wastewater",
                    "groundwater"],
        "patterns": [r"stormwater", r"water quality", r"watershed", r"clean water",
                     r"drinking water", r"groundwater", r"wastewater", r"\bsewer",
                     r"\bPFAS\b", r"water (conservation|supply|infrastructure|system|utilit|reuse|recycl)",
                     r"lead service line", r"\baquifer", r"water rights",
                     # federal water-program titles (added after the 2026-11-14 federal run)
                     r"water pollution control", r"water resources development", r"desalinat",
                     r"\birrigation\b", r"\breservoirs?\b", r"great lakes", r"rural water",
                     r"water (security|management|project|storage)", r"dam (and hydropower )?safety"],
        "exclude": [],
    },
    {
        "slug": "land-use",
        "name": "Land Use & Development",
        "queries": ["zoning", "land use", "brownfield", "accessory dwelling"],
        "patterns": [r"\bzoning\b", r"\bland use\b", r"land[- ]use (plan|regulat|polic)",
                     r"comprehensive plan", r"\bbrownfield", r"accessory dwelling",
                     r"smart growth", r"\binfill\b", r"urban growth", r"\bsubdivision",
                     r"transit[- ]oriented", r"(housing|residential) density",
                     r"farmland (and open space )?preservation", r"community land trust"],
        "exclude": [],
    },
    {
        "slug": "materials-circularity",
        "name": "Materials & Circularity",
        "queries": ["solid waste", "recycling", "waste management",
                    "producer responsibility", "packaging", "compost"],
        "patterns": [r"solid waste", r"recycl", r"waste (management|reduction|diversion|disposal|hauling)",
                     r"\blandfill", r"compost", r"producer responsibility",
                     r"packaging (waste|reduction|material|producer|recycl|stewardship)",
                     r"(plastic|sustainable|reusable|compostable) packaging",
                     r"single[- ]use plastic", r"plastic (bag|waste|pollution|product)",
                     r"organic waste", r"food waste", r"hazardous waste", r"circular economy",
                     r"product stewardship", r"right to repair", r"embodied carbon",
                     r"low[- ]carbon (concrete|cement|material)",
                     r"(building|construction) material.*(carbon|toxic|healthy|sustainab)",
                     r"buy clean", r"microplastic"],
        # Nuclear fuel "recycling" is reactor fuel policy, not materials circularity.
        "exclude": [r"labor dispute", r"recycling efficient fuels", r"nuclear fuel", r"spent (nuclear )?fuel"],
    },
    {
        "slug": "nature-biodiversity",
        "name": "Nature & Biodiversity",
        "queries": ["conservation", "wetlands", "wildlife habitat", "biodiversity",
                    "forest"],
        "patterns": [r"(?<!energy )(?<!water )\bconservation\b", r"wetland", r"\bhabitat\b",
                     r"biodiversity", r"open space", r"(?<!community )land trust",
                     r"\bforest (health|management|conservation|carbon|restoration)",
                     r"\bforestry\b", r"endangered species", r"\bwildlife\b(?! (officer|crime|violation))",
                     r"pollinator", r"invasive species", r"ecosystem", r"(ecological|habitat) restoration",
                     r"public lands", r"species recovery",
                     r"\b(wolf|wolves|salmon|manatees?|whales?)\b"],
        # Personnel bills for conservation officers / game wardens aren't nature policy.
        "exclude": [r"conservation officers?", r"game wardens?"],
    },
    {
        "slug": "environmental-justice",
        "name": "Environmental Justice",
        "queries": ["environmental justice", "environmental equity", "energy equity",
                    "overburdened communities", "disadvantaged communities"],
        "patterns": [r"environmental justice", r"environmental equity", r"energy equity",
                     r"clean energy equity", r"overburdened", r"disadvantaged communit",
                     r"frontline communit", r"climate justice", r"energy justice",
                     r"environmental health", r"cumulative impact", r"pollution burden"],
        "exclude": [],
    },
    {
        "slug": "infrastructure-resilience",
        "name": "Infrastructure & Resilience",
        # Covers three former categories (clean energy, grid, transportation)
        # plus resilience, so it gets more feed slots (approved 2026-11-13).
        "per_category": 12,
        # Transportation, utilities and the grid, utility-scale clean energy,
        # and adaptation/resilience (decision 2026-11-13: utility-scale clean
        # energy and transmission belong here, not in Building & Energy).
        "queries": ["renewable energy", "clean energy", "solar", "wind energy",
                    "energy storage", "electric grid", "transmission", "ratepayer",
                    "utility rates", "interconnection", "electric vehicle",
                    "zero-emission vehicle", "public transit", "transit", "electric bus",
                    "resilience", "flood", "wildfire mitigation", "climate adaptation"],
        "patterns": [
            # utility-scale clean energy
            r"renewable energ", r"clean energy", r"\bsolar\b", r"photovoltaic",
            r"\bwind (energy|power|turbine|farm|facilit|project|generation)",
            r"offshore wind", r"energy storage", r"battery storage", r"geothermal",
            r"zero[- ]carbon (electric|energy|resource)",
            # grid, utilities, affordability
            r"\bgrid\b", r"\btransmission (line|infrastructure|facilit|project|siting|planning|system)",
            r"\bratepayer", r"\b(utility|electric|electricity|energy) (rate|bill|cost)s?\b",
            r"energy affordab", r"energy burden", r"load forecast",
            r"\binterconnection\b", r"resource adequacy", r"\bmicrogrid",
            # adaptation and resilience
            # "resilien" only with a climate/hazard context word nearby, so
            # "cybersecurity resiliency" and "archives resiliency" don't count.
            r"\b(climate|flood|disaster|coastal|community|communities|infrastructure|grid|energy|"
            r"wildfire|water|environmental|storm|drought|hazard|weather)\W+(\w+\W+){0,2}resilien",
            r"resilien\w*\W+(\w+\W+){0,3}(climate|flood|disaster|extreme weather|natural hazard|"
            r"wildfire|storm|drought|sea[- ]level)",
            r"resilient (building|infrastructure|communit|grid|coast|home|housing)",
            r"climate adaptation", r"sea[- ]level rise",
            r"flood (control|mitigation|risk|resilien|protection|plain|prepared)", r"floodplain",
            r"wildfire (mitigation|prevention|risk|resilien)", r"hazard mitigation",
            r"(public|green|resilient) infrastructure",
        ],
        "exclude": [],
        # Transportation patterns keep their own excludes (carried over from the
        # old Clean Transportation category) so transit-worker and police bills
        # stay out without affecting the energy and grid patterns above.
        "subgroups": [{
            "patterns": [r"electric vehicle", r"\bEVs?\b", r"charging station",
                         r"zero[- ]emission [a-z ]{0,20}(vehicle|bus|truck|fleet)", r"electric (school )?bus",
                         r"public transit", r"mass transit", r"public transportation",
                         r"\btransit (authority|agency|district|system|service|fund|capital|operat)",
                         r"transit[- ]oriented", r"bus rapid transit", r"passenger rail",
                         r"vehicle electrification"],
            "exclude": [r"employee", r"\blabor\b", r"collective bargaining", r"\bpolice\b",
                        r"commercial code"],
        }],
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


def _rx(p):
    # \bEVs?\b is the one pattern that must stay case-sensitive ("ev" is common).
    return re.compile(p) if p == r"\bEVs?\b" else re.compile(p, _FLAGS)


for c in CATEGORIES:
    # Each rule is (pattern, excludes that cancel that pattern).
    c["_rules"] = [(_rx(p), []) for p in c["patterns"]]
    for g in c.get("subgroups", []):
        gx = [re.compile(x, _FLAGS) for x in g["exclude"]]
        c["_rules"] += [(_rx(p), gx) for p in g["patterns"]]
    c["_exclude"] = [re.compile(p, _FLAGS) for p in c["exclude"]]
_AGENCIES = [re.compile(p, _FLAGS) for p in AGENCY_NAMES]
_GLOBAL_EXCLUDE = [re.compile(p, _FLAGS) for p in GLOBAL_EXCLUDE]
_BY_SLUG = {c["slug"]: c for c in CATEGORIES}


def score_categories(title):
    """Return [(slug, score), ...] for every matching category, best first.

    Ties keep CATEGORIES order. An empty list means the title matched nothing
    (or is excluded), and the bill is left out of the feed.
    """
    title = title or ""
    if any(p.search(title) for p in _GLOBAL_EXCLUDE):
        return []
    cleaned = title
    for p in _AGENCIES:
        cleaned = p.sub(" ", cleaned)

    scores = []
    for c in CATEGORIES:
        if any(p.search(cleaned) for p in c["_exclude"]):
            continue
        score = sum(1 for p, ex in c["_rules"]
                    if p.search(cleaned) and not any(x.search(cleaned) for x in ex))
        if score:
            scores.append((c["slug"], score))
    scores.sort(key=lambda s: -s[1])  # stable: ties keep CATEGORIES order
    return scores


def categorize(title):
    """Return the primary category slug for a bill title, or None."""
    s = score_categories(title)
    return s[0][0] if s else None


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


def shape(b, slugs, today):
    """slugs: matching category slugs, primary first (or a single slug)."""
    if isinstance(slugs, str):
        slugs = [slugs]
    action_date = parse_date(b.get("latest_action_date"))
    cat = _BY_SLUG[slugs[0]]
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
        "category": cat["slug"],          # primary category
        "category_name": cat["name"],
        "categories": list(slugs),         # all matching categories, primary first
        "topics": [_BY_SLUG[x]["name"] for x in slugs],  # what the site filters on
        "classification": "auto-title",    # editorial suggestion, not a source fact
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
    """Up to PER_CATEGORY (or the category's per_category) per primary
    category, newest first, spread across states."""
    items = sorted(items, key=lambda i: recency_key(i, today), reverse=True)
    chosen = []
    for c in CATEGORIES:
        limit = c.get("per_category", PER_CATEGORY)
        pool = [i for i in items if i["category"] == c["slug"]]
        picked, per_state = [], {}
        for i in pool:  # first pass: respect the per-state limit
            if len(picked) >= limit:
                break
            if per_state.get(i["state"], 0) < PER_STATE_IN_CATEGORY:
                picked.append(i)
                per_state[i["state"]] = per_state.get(i["state"], 0) + 1
        for i in pool:  # second pass: fill any open slots
            if len(picked) >= limit:
                break
            if i not in picked:
                picked.append(i)
        picked.sort(key=lambda i: recency_key(i, today), reverse=True)
        chosen.extend(picked)
    return chosen


def build_feed(found, prev, today):
    items, seen_titles = [], {}
    for b in sorted(found.values(), key=lambda b: b.get("latest_action_date") or "", reverse=True):
        scored = score_categories(b.get("title"))
        if not scored:
            continue
        # Companion bills (same title, same state and session) show once.
        key = (b.get("jurisdiction_abbreviation"), b.get("session_identifier"), norm_title(b.get("title")))
        if key in seen_titles:
            continue
        seen_titles[key] = True
        items.append(shape(b, [slug for slug, _ in scored], today))

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
    # Counts are tags, so a bill with two categories counts in both.
    counts = {c["slug"]: sum(1 for b in bills if c["slug"] in b["categories"]) for c in CATEGORIES}
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
