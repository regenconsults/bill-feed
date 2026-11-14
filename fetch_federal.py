"""
Federal (U.S. Congress) bill feed for regenconsults.com.

Scans the current Congress's bills and joint resolutions on the official
Congress.gov API, keeps environment-related ones, classifies them into the same
eight categories as the state feed (fetch_bills.py), and writes
docs/federal.json. It's completely separate from the state feed: if this
script fails, docs/bills.json is not touched.

Needs CONGRESS_API_KEY (an api.data.gov key). The key is sent in a header,
never in a URL, so it can't leak into logs or error messages.

See docs/federal-data-integration.md.
"""

import html
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone

import requests

import fetch_bills as fb  # categories, classifier, pick, movement badges

# ---------------------------------------------------------------- settings --

API = "https://api.congress.gov/v3"
API_KEY = os.getenv("CONGRESS_API_KEY", "").strip()

# Bills and joint resolutions only: simple and concurrent resolutions aren't
# legislation that can become law.
BILL_TYPES = ["hr", "s", "hjres", "sjres"]

MAX_AGE_DAYS = fb.MAX_AGE_DAYS      # same 180-day window as the state feed
LIST_LIMIT = 250                    # API maximum per page
PAUSE_SECONDS = 0.75                # ~4,800/hr, under the 5,000/hr key limit
MAX_CALLS_PER_RUN = int(os.getenv("FEDERAL_MAX_CALLS", "3500"))
MAX_RETRIES = 4
MAX_ACTIONS_KEPT = 30               # most recent actions stored per bill

OUTPUT = os.getenv("FEDERAL_FEED_OUT", "docs/federal.json")
# Detail cache, so unchanged bills aren't re-fetched. Not published.
CACHE = os.getenv("FEDERAL_CACHE", "data/federal-cache.json")

# Congress.gov policy areas (one per bill, assigned by CRS) that make a bill a
# candidate even if its title has no environmental keywords, e.g. BAAJA.
# Other policy areas only qualify through the title or summary.
ENV_POLICY_AREAS = {
    "Environmental Protection",
    "Energy",
    "Water Resources Development",
    "Public Lands and Natural Resources",
}

# A bill gets a category if its title matches it, or if the official summary
# matches at least this many distinct patterns for it (summaries are long, so
# one passing keyword isn't enough).
SUMMARY_MIN_SCORE = 2

TYPE_LABEL = {"HR": "H.R.", "S": "S.", "HJRES": "H.J.Res.", "SJRES": "S.J.Res."}
TYPE_URL = {"HR": "house-bill", "S": "senate-bill",
            "HJRES": "house-joint-resolution", "SJRES": "senate-joint-resolution"}

STATUS_LABELS = {
    "introduced": "Introduced",
    "in_committee": "In committee",
    "reported": "Reported by committee",
    "passed_one_chamber": "Passed one chamber",
    "passed_both": "Passed both chambers",
    "enacted": "Enacted",
    "vetoed": "Vetoed",
    "other": "Other / needs review",
}

ATTRIBUTION = ("Federal bill data retrieved from Congress.gov (https://www.congress.gov/), "
               "the official website for U.S. federal legislative information.")


class BudgetExhausted(Exception):
    pass


# ------------------------------------------------------------------- http --


class Client:
    def __init__(self, session, budget=MAX_CALLS_PER_RUN, pause=PAUSE_SECONDS):
        self.s, self.budget, self.pause, self.calls, self.errors = session, budget, pause, 0, 0

    def get(self, path, **params):
        """GET {API}{path} as JSON. Retries 429/5xx and connection errors."""
        params.setdefault("format", "json")
        url = path if path.startswith("http") else API + path
        for attempt in range(MAX_RETRIES + 1):
            if self.calls >= self.budget:
                raise BudgetExhausted()
            self.calls += 1
            try:
                r = self.s.get(url, params=params, timeout=30)
            except requests.RequestException as e:
                if attempt == MAX_RETRIES:
                    raise
                wait = 10 * (attempt + 1)
                print(f"  ... {type(e).__name__}, retrying in {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            finally:
                time.sleep(self.pause)
            if r.status_code == 429 or r.status_code >= 500:
                if attempt == MAX_RETRIES:
                    r.raise_for_status()
                wait = int(r.headers.get("Retry-After", "0") or 0) or 60 * (attempt + 1)
                print(f"  ... {r.status_code}, waiting {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()


# ---------------------------------------------------------------- helpers --


def current_congress(today):
    # A new Congress convenes Jan 3 of odd years.
    year = today.year - (1 if (today.year % 2 == 1 and (today.month, today.day) < (1, 3)) else 0)
    return (year - 1789) // 2 + 1


def ordinal(n):
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def canonical_id(congress, btype, number):
    return f"us-congress-{congress}-{btype.lower()}-{number}"


def official_url(congress, btype, number):
    return f"https://www.congress.gov/bill/{ordinal(int(congress))}-congress/{TYPE_URL[btype.upper()]}/{number}"


def strip_html(s):
    s = re.sub(r"<\s*(br|/p|/li)\s*/?>", "\n", s or "", flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s).replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n", s).strip()


def parse_date(s):
    return fb.parse_date(s)


# ----------------------------------------------------------- normalizing --

_PASSED = [
    (re.compile(r"^Passed/agreed to in House\b", re.I), "House"),
    (re.compile(r"^Passed/agreed to in Senate\b", re.I), "Senate"),
    (re.compile(r"^Passed House\b", re.I), "House"),
    (re.compile(r"^Passed Senate\b", re.I), "Senate"),
    (re.compile(r"^On passage Passed\b", re.I), "House"),
    (re.compile(r"^On motion to suspend the rules and pass the (bill|resolution)[^.]*Agreed to", re.I), "House"),
]
_REPORTED = re.compile(r"\b(reported (by|to|favorably|with|without)|ordered to be reported|placed on (the )?(senate legislative calendar|union calendar|house calendar))", re.I)
_VETO = re.compile(r"\bvetoed by (the )?president\b", re.I)
_LAW = re.compile(r"^Became (Public|Private) Law\b", re.I)


def normalize_status(detail, actions):
    """Return (status, dates) from the official record.

    status is one of STATUS_LABELS. dates holds introduced/passed/enacted dates
    taken from dated actions. Effective date is never inferred.
    """
    dates = {"introduced_date": detail.get("introducedDate"),
             "passed_house_date": None, "passed_senate_date": None, "enacted_date": None}
    chambers, reported, vetoed = set(), False, None
    for a in sorted(actions, key=lambda a: a.get("actionDate") or ""):
        text, d, typ = a.get("text") or "", a.get("actionDate"), a.get("type") or ""
        if typ == "BecameLaw" or _LAW.search(text):
            dates["enacted_date"] = dates["enacted_date"] or d
        if typ == "Veto" and _VETO.search(text):
            vetoed = d
        for rx, ch in _PASSED:
            if rx.search(text):
                chambers.add(ch)
                key = f"passed_{ch.lower()}_date"
                dates[key] = dates[key] or d
        if _REPORTED.search(text):
            reported = True

    if detail.get("laws") or dates["enacted_date"]:
        return "enacted", dates
    if vetoed:
        return "vetoed", dates
    if chambers == {"House", "Senate"}:
        return "passed_both", dates
    if chambers:
        return "passed_one_chamber", dates
    if reported:
        return "reported", dates
    if (detail.get("committees") or {}).get("count") or any(
            re.search(r"\breferred to\b", a.get("text") or "", re.I) for a in actions):
        return "in_committee", dates
    if actions or detail.get("introducedDate"):
        return "introduced", dates
    return "other", dates


def classify(title, summary_text):
    """Return category slugs, primary first, from title + official summary."""
    title_s = dict(fb.score_categories(title))
    summ_s = dict(fb.score_categories(summary_text)) if summary_text else {}
    combined = {}
    for c in fb.CATEGORIES:
        t, s = title_s.get(c["slug"], 0), summ_s.get(c["slug"], 0)
        if t >= 1 or s >= SUMMARY_MIN_SCORE:
            combined[c["slug"]] = 2 * t + s
    order = [c["slug"] for c in fb.CATEGORIES]
    return sorted(combined, key=lambda k: (-combined[k], order.index(k)))


def latest_summary(summaries):
    if not summaries:
        return None
    return max(summaries, key=lambda s: (s.get("actionDate") or "", s.get("updateDate") or ""))


def shape(entry, today, verified_at):
    d, actions = entry["detail"], entry.get("actions") or []
    btype, num, congress = d["type"].upper(), str(d["number"]), int(d["congress"])
    status, dates = normalize_status(d, actions)
    summ = latest_summary(entry.get("summaries"))
    summary_text = strip_html(summ.get("text")) if summ else None
    slugs = classify(d.get("title"), summary_text)
    la = d.get("latestAction") or {}
    sponsor = (d.get("sponsors") or [{}])[0].get("fullName")
    url = d.get("legislationUrl") or official_url(congress, btype, num)
    if not url.startswith("https://www.congress.gov/"):
        url = official_url(congress, btype, num)
    laws = d.get("laws") or []
    recent = sorted(actions, key=lambda a: (a.get("actionDate") or "", a.get("actionTime") or ""),
                    reverse=True)
    item = {
        "id": canonical_id(congress, btype, num),
        "jurisdiction": "federal",
        "legislative_body": "U.S. Congress",
        "state": None,
        "congress": congress,
        "bill_type": btype,
        "bill_number": num,
        "bill": f"{TYPE_LABEL[btype]} {num}",
        "session": f"{ordinal(congress)} Congress",
        "origin_chamber": d.get("originChamber"),
        "title": d.get("title"),
        "summary": summary_text,
        "summary_version": (f"{summ.get('actionDesc')} ({summ.get('actionDate')})" if summ else None),
        "sponsor": sponsor,
        "cosponsors_count": (d.get("cosponsors") or {}).get("count"),
        "policy_area": (d.get("policyArea") or {}).get("name"),
        "committees": [c.get("name") for c in entry.get("committees") or [] if c.get("name")],
        "status": status,
        "status_label": STATUS_LABELS[status],
        "latest_action": la.get("text"),
        "latest_action_date": la.get("actionDate"),
        "upcoming": False,
        "introduced": dates["introduced_date"],
        "passed_house_date": dates["passed_house_date"],
        "passed_senate_date": dates["passed_senate_date"],
        "enacted_date": dates["enacted_date"],
        "effective_date": None,  # not provided by the API; never inferred
        "law_number": (f"{laws[0].get('type')} {laws[0].get('number')}" if laws else None),
        "actions": [{"date": a.get("actionDate"), "text": a.get("text"), "type": a.get("type")}
                    for a in recent[:MAX_ACTIONS_KEPT]],
        "actions_total": len(actions),
        "url": url,
        "source_updated_at": d.get("updateDateIncludingText") or d.get("updateDate"),
        "last_verified_at": verified_at,
        "classification": "auto-title-summary",
    }
    if slugs:
        cat = fb._BY_SLUG[slugs[0]]
        item.update(category=cat["slug"], category_name=cat["name"], categories=slugs,
                    topics=[fb._BY_SLUG[s]["name"] for s in slugs])
    else:
        item.update(category=None, category_name=None, categories=[], topics=[])
    return item


# ------------------------------------------------------------------ fetch --


def list_recent(client, congress, cutoff):
    """Yield list items for bills updated on or after cutoff, newest first."""
    from_dt = f"{cutoff.isoformat()}T00:00:00Z"
    for t in BILL_TYPES:
        offset = 0
        while True:
            page = client.get(f"/bill/{congress}/{t}", limit=LIST_LIMIT, offset=offset,
                              sort="updateDate desc", fromDateTime=from_dt)
            rows = page.get("bills") or []
            yield from rows
            offset += len(rows)
            total = (page.get("pagination") or {}).get("count", 0)
            if not rows or offset >= total:
                break


def prune(cache, cutoff):
    """Drop cached bills whose latest action fell out of the window."""
    for k in [k for k, e in cache.items()
              if (parse_date((e.get("detail", {}).get("latestAction") or {}).get("actionDate"))
                  or date.min) < cutoff]:
        del cache[k]


def is_candidate(title, policy_area):
    return policy_area in ENV_POLICY_AREAS or bool(fb.score_categories(title))


def hydrate(client, entry, key_path):
    """Fetch actions, summaries and committees for a candidate bill."""
    base = f"/bill/{key_path}"
    entry["actions"] = client.get(f"{base}/actions", limit=250).get("actions") or []
    entry["summaries"] = client.get(f"{base}/summaries", limit=250).get("summaries") or []
    entry["committees"] = client.get(f"{base}/committees", limit=250).get("committees") or []
    entry["hydrated"] = True


def sync(client, cache, congress, today, now_iso):
    """Refresh the cache from the API. Returns (complete, stats)."""
    cutoff = today - timedelta(days=MAX_AGE_DAYS)
    stats = {"listed": 0, "recent": 0, "details_fetched": 0, "hydrated": 0, "pending": 0}
    complete = True
    listed = []
    try:
        for row in list_recent(client, congress, cutoff):
            stats["listed"] += 1
            d = parse_date((row.get("latestAction") or {}).get("actionDate"))
            if d and d >= cutoff and row.get("type", "").lower() in BILL_TYPES:
                listed.append(row)
    except BudgetExhausted:
        complete = False

    stats["recent"] = len(listed)
    if complete:
        prune(cache, cutoff)
    # Newest action first, so a partial run covers the most current bills.
    listed.sort(key=lambda r: (r.get("latestAction") or {}).get("actionDate") or "", reverse=True)
    for row in listed:
        key = canonical_id(row["congress"], row["type"], row["number"])
        path = f"{row['congress']}/{row['type'].lower()}/{row['number']}"
        entry = cache.get(key)
        upd = row.get("updateDateIncludingText") or row.get("updateDate")
        try:
            if entry is None or entry.get("list_update") != upd:
                detail = client.get(f"/bill/{path}").get("bill") or {}
                entry = {"list_update": upd, "detail": detail}
                stats["details_fetched"] += 1
                cache[key] = entry
            entry["candidate"] = is_candidate(entry["detail"].get("title"),
                                              (entry["detail"].get("policyArea") or {}).get("name"))
            if entry["candidate"] and not entry.get("hydrated"):
                hydrate(client, entry, path)
                entry["verified_at"] = now_iso
                stats["hydrated"] += 1
            entry["seen_at"] = now_iso
        except BudgetExhausted:
            complete = False
            stats["pending"] = sum(1 for r in listed
                                   if cache.get(canonical_id(r["congress"], r["type"], r["number"]),
                                                {}).get("seen_at") != now_iso)
            break
        except requests.HTTPError as e:
            client.errors += 1
            code = e.response.status_code if e.response is not None else "?"
            print(f"  ! {key}: HTTP {code}", file=sys.stderr)
    return complete, stats


# ---------------------------------------------------------------- output --


def build_feed(cache, prev, today, congress):
    cutoff = today - timedelta(days=MAX_AGE_DAYS)
    items, needs_review, seen_titles = [], [], {}
    entries = [e for e in cache.values() if e.get("candidate") and e.get("hydrated")
               and int(e["detail"].get("congress", 0)) == congress]
    entries.sort(key=lambda e: (e["detail"].get("latestAction") or {}).get("actionDate") or "",
                 reverse=True)
    for e in entries:
        d = parse_date((e["detail"].get("latestAction") or {}).get("actionDate"))
        if not d or d < cutoff:
            continue
        # seen_at: the last run that confirmed this record against the API.
        item = shape(e, today, e.get("seen_at") or e.get("verified_at"))
        if not item["categories"]:
            needs_review.append(item["id"])
            continue
        # Identical-title companions (House and Senate versions) show once:
        # the most recently acted-on one.
        t = fb.norm_title(item["title"])
        if t in seen_titles:
            continue
        seen_titles[t] = True
        items.append(item)
    feed = fb.pick(items, today)
    for i in feed:
        fb.mark_movement(i, prev, today)
    if not prev:
        for i in feed:
            i["change"] = None
    return feed, items, needs_review


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, obj, indent=1):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=indent, ensure_ascii=False)
    os.replace(tmp, path)


def main(session=None):
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat(timespec="seconds")
    today = now.date()
    congress = int(os.getenv("FEDERAL_CONGRESS") or current_congress(today))
    previous = load_json(OUTPUT, {})
    prev_bills = {b["id"]: b for b in previous.get("bills", [])}
    sync_info = dict(previous.get("sync") or {})
    sync_info["last_attempt_at"] = now_iso

    def fail(msg):
        # Keep the last good bills; record the failure so it's visible.
        print(f"Federal sync failed: {msg}", file=sys.stderr)
        sync_info.update(status="error", last_error=msg)
        out = dict(previous) if previous.get("bills") else {
            "version": 1, "jurisdiction": "federal", "bills": [], "attribution": ATTRIBUTION}
        out["sync"] = sync_info
        write_json(OUTPUT, out)
        return 1

    if not API_KEY:
        return fail("CONGRESS_API_KEY is not set")

    cache = load_json(CACHE, {})
    own = session is None
    session = session or requests.Session()
    session.headers.update({"X-Api-Key": API_KEY,
                            "User-Agent": "regenconsults-bill-feed/federal-1.0"})
    client = Client(session, budget=MAX_CALLS_PER_RUN, pause=PAUSE_SECONDS)
    try:
        complete, stats = sync(client, cache, congress, today, now_iso)
    except requests.RequestException as e:
        # Message deliberately excludes the URL and headers.
        write_json(CACHE, cache, indent=None)
        return fail(f"{type(e).__name__} after {client.calls} calls")
    finally:
        if own:
            session.close()
    write_json(CACHE, cache, indent=None)

    feed, matched, needs_review = build_feed(cache, prev_bills, today, congress)
    print(f"{client.calls} API calls, {client.errors} errors; listed {stats['listed']}, "
          f"recent {stats['recent']}, details {stats['details_fetched']}, hydrated "
          f"{stats['hydrated']}, pending {stats['pending']}; {len(matched)} categorized, "
          f"{len(needs_review)} need review, {len(feed)} in feed")

    if not feed and not complete:
        return fail(f"incomplete sync with no publishable bills ({stats['pending']} pending)")

    counts = {c["slug"]: sum(1 for b in feed if c["slug"] in b["categories"]) for c in fb.CATEGORIES}
    status = "ok" if complete and not client.errors else "partial"
    sync_info.update(status=status, last_error=None if status == "ok" else
                     f"{stats['pending']} bills pending, {client.errors} errors")
    sync_info["last_success_at"] = now_iso
    sync_info.update(api_calls=client.calls, needs_review=len(needs_review),
                     candidates_in_window=len(matched) + len(needs_review))
    out = {
        "version": 1,
        "jurisdiction": "federal",
        "generated_at": now_iso,
        "congress": congress,
        "scope": "Bills and joint resolutions (H.R., S., H.J.Res., S.J.Res.) in the current Congress "
                 f"with official action in the last {MAX_AGE_DAYS} days",
        "categories": [{"slug": c["slug"], "name": c["name"], "count": counts[c["slug"]]}
                       for c in fb.CATEGORIES],
        "sync": sync_info,
        "attribution": ATTRIBUTION,
        "bills": feed,
    }
    write_json(OUTPUT, out)
    print(f"Wrote {len(feed)} federal bills to {OUTPUT} (sync {status})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
