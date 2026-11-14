# Legislation Tracker — Step 1 Audit

Audited 2026-11-13 against `main` at `1f80f8d` (feed generated 2026-11-13T18:28:46Z).
Nothing in the application was changed in this step. This file is the only addition.

## 1. Architecture

There is no server, database or build step. The whole system is four parts:

| Part | Where | What it does |
|---|---|---|
| Ingestion script | `fetch_bills.py` (Python 3.12, only dependency `requests`) | Queries the Bill Commons API, categorizes bills by title regex, picks a curated subset, writes `docs/bills.json` |
| Scheduler | `.github/workflows/refresh-bills.yml` | GitHub Actions cron `0 11,23 * * *` plus a manual `workflow_dispatch`. Runs the script, then commits and pushes `docs/bills.json` to `main` as `bill-feed-bot` |
| Storage / hosting | `docs/bills.json` in the **public** repo `regenconsults/bill-feed`, served by GitHub Pages (`main` branch, `/docs`) | `https://regenconsults.github.io/bill-feed/bills.json`. Verified headers: `200`, `access-control-allow-origin: *`, `cache-control: max-age=600` |
| Front end | One Squarespace Code Block on `/legislation-tracker` | Vanilla JS and CSS (`.rgt-*` classes). Contains both the hero and the tracker. Fetches the JSON in the browser and renders it |

**Secrets and config:** none. `gh secret list` and `gh variable list` both come back empty. `BILL_STATES` is unset, so all states are fetched. Bill Commons is used anonymously, with no key.

**Tests, lint, type checks, build:** none exist. There's no `requirements.txt` either; the workflow runs `pip install requests`.

**Front-end source of truth:** the live block is the real source. In the repo:
- `squarespace-code-block.v1-live.html` is one revision behind the live block. Live has the Topic→Category label, per-category counts, and chip order taken from `feed.categories`. I diffed the two on 2026-11-13.
- `squarespace-code-block.html` is an older stock `bf-*` embed and is not in use.
- I saved a copy of the current live block during the audit; it should be committed as part of Step 2.

## 2. State data source and refresh path

- **Source:** Bill Commons public API, `GET https://api.billcommons.org/api/v1/bills?q=<term>&per_page=50&page=N`. It says its data comes from official state legislative records and Open States.
- **Fetch:** 8 categories × 5–7 query terms × up to 2 pages, with a 2 s pause between calls. On a 429 or 5xx it retries up to 3 times, using `Retry-After` or a 30/60/90 s backoff. Other errors are counted and that query is skipped.
- **Filter:** drops bills whose latest action is older than 180 days, drops anything matching `GLOBAL_EXCLUDE`, strips agency names from titles, then scores each title against every category's regexes.
- **Dedupe:** companion bills with the same state, session and normalized title are shown once.
- **Curate (`pick`):** keeps at most 6 bills per category and at most 2 per state within a category on the first pass, newest first.
- **Movement:** compares against the previous `bills.json` by `id` and sets `change` = `new` / `moved` / `null`. The badge lasts 3 days.
- **Failure behavior:** if no bills result, the previous file is left in place. With partial errors, the script still writes whatever it got.
- **Observed runs:** the last 12 scheduled runs all succeeded, each taking about 3m50s. They start well after the cron times, though: 18:25, 03:13, 18:43 and 02:34 UTC, against 11:00/23:00 scheduled. So "twice daily" holds, but the clock times in `BUILD_BILL_FEED.md` don't.

### Trace of one state bill (MI HB 6486)

1. API row: `id 3b580269-…`, `jurisdiction_abbreviation MI`, `identifier "HB 6486"`, `status in_committee`, `latest_action_text "bill electronically reproduced 11/12/2026"`, `latest_action_date 2026-11-17` (a future date), `introduced_date null`, `source_url https://legislature.mi.gov/Bills/Bill?ObjectName=2026-HB-6486`.
2. `categorize()`: the title contains "solar" and "open space". Clean Energy and Water & Land each score 1, and Clean Energy wins because it is listed first.
3. `shape()` produces the record with `state`, `bill`, `title`, `session`, `status`, `status_label "In committee"`, `upcoming true`, `url`, `category "clean-energy"` and `topics ["Clean Energy"]`.
4. `mark_movement()` sets `change "new"` because it is first seen 2026-11-13.
5. Embed: the row shows `MI / HB 6486`, the title, the "Clean Energy" tag, an "In committee" pill in the Active group, and "Nov 17, 2026". The expanded view shows the latest action, the session, and a "View on legislature site ↗" link.

## 3. Current schema and category behavior

### Feed record (`bills[]`, version 2)

`id, state, bill, title, session, status, status_label, latest_action, latest_action_date, upcoming, introduced, url, category, category_name, topics[], first_seen, changed_on, change, previous_status_label`

Top level: `version, generated_at, states, categories[{slug,name,count}], attribution, bills`.

How the plan's required concepts map onto it:

| Concept | Present? | Notes |
|---|---|---|
| Jurisdiction federal/state | **No** | Every record is implicitly state |
| State | Yes | `state` |
| Chamber/body | No | The API's `chamber` is `null` on the sample |
| Identifier + session | Yes | `bill`, `session`; `id` is a Bill Commons UUID |
| Official title | Yes | `short_title` or `title` |
| Summary | No | The API returns no summary |
| Status | Yes | `status` (Bill Commons enum) and `status_label` |
| Action history | **No** | Latest action only |
| Introduced date | Partial | Missing on 26 of 45 records |
| Passed / enacted / effective dates | No | |
| Categories | Single | `category` plus a one-item `topics[]` |
| Official URL | Yes | All 45 are valid http(s) |
| Source updated / last verified | Partial | The API has `updated_at`, but the feed drops it. `generated_at` is feed-level only |
| Sponsor | No | |

### Categories in use now (v2)

`clean-energy` Clean Energy · `grid` Grid & Energy Affordability · `buildings` Green & Healthy Buildings · `transportation` Clean Transportation · `climate` Climate & Emissions · `waste` Waste & Circular Economy · `water-land` Water & Land · `equity` Environmental Equity.

- Assignment is automatic, by title regex only: one category per bill, highest score wins, ties go to whichever category is listed first. There's no review mechanism and no confidence value is stored.
- Slugs and display names are already separate.
- **Multi-category is cheap on the front end.** The live embed filters on `topics.indexOf(...)` and counts per topic, so a bill with several `topics` already shows under each one. The script is what limits bills to one category.

### These are not the plan's eight

| Plan category | Closest current source | Gap |
|---|---|---|
| Building & Energy | `buildings`, part of `clean-energy` (distributed energy), part of `grid` | The definition centers on buildings. It's unclear where utility-scale solar, wind and transmission belong |
| Climate & Emissions | `climate` | Same name, so a direct carry-over |
| Water Resources | water half of `water-land` | Split required |
| Land Use & Development | — | **No current coverage.** Needs new queries and patterns (zoning, density, housing) |
| Materials & Circularity | `waste` | Rename, plus sourcing/materials terms |
| Nature & Biodiversity | land/habitat half of `water-land` | Split required |
| Environmental Justice | `equity` | Rename |
| Infrastructure & Resilience | `transportation`, part of `grid` (utilities) | Adaptation/resilience terms are new |

A draft mapping goes in `docs/category-taxonomy.md` in Step 3. Two items there need your decision, listed in §7.

### Status

The embed groups statuses into three filter chips: Active, Enacted, and Inactive (`withdrawn, died_on_adjournment, killed, vetoed, substituted`). The plan's normalized set (Introduced / In Committee / Passed One Chamber / Passed Both / Enacted / Failed-Withdrawn / Other) is finer-grained but has no Vetoed or Sent-to-governor. I recommend keeping the Bill Commons enum for state bills, mapping federal statuses onto the same enum plus labels, and leaving the three-chip grouping alone. That avoids breaking the current state filter.

## 4. User-facing features verified

I checked these in the live page's served HTML (`curl` of `/legislation-tracker`, 2026-11-13) and against the current feed. I did **not** load the page in a browser in this step.

- A hero: "Environmental Legislation Tracker". The intro reads: *"Environment-related bills moving through state legislatures across all 50 states, refreshed twice daily."*
- An "Updated …" timestamp from `generated_at`, with a green or orange status dot.
- A "N of M bills" count.
- Search across state, bill number, title and latest action text.
- A State dropdown built from the states present in the feed (11 right now).
- Status chips: All / Active / Enacted / Inactive.
- Category chips with counts, in feed order.
- Expandable rows showing the full title, latest action and date, session, and an official link that opens in a new tab.
- "Show more" in steps of 15, an empty state with Clear filters, and the attribution line with "Not legal advice."
- A single error state: if the fetch fails, the message reads "Legislation feed is temporarily unavailable."
- Mobile layout below 819px (from the CSS; not visually checked).
- No URL or query-string state, so there are no saved links to filters that could break.

**Copy accuracy note:** the feed is a curated sample of **45 bills from 11 states**: NJ 11, CA 10, PA 8, IL 4, MI 3, OH 2, NH 2, MA 2, VA 1, DC 1, NY 1. All states are *searched*, but the intro's "across all 50 states" reads as coverage, and that's stronger than what's shown. This is relevant to Step 8.

## 5. Commands

```bash
# local run without touching the published file
BILL_FEED_OUT=/tmp/bills.json python3 fetch_bills.py      # ~4 min, ~100 API calls
# limit to a few states for a quick run
BILL_STATES=NJ,CA BILL_FEED_OUT=/tmp/bills.json python3 fetch_bills.py
# trigger production refresh (commits to main)
gh workflow run refresh-bills.yml
gh run list -w refresh-bills.yml
```

There are no test, lint or build commands.

## 6. Risks and recommended minimal-change approach

### Risks

1. **No durable record store.** Each run *replaces* the feed with a fresh pick of up to 48 bills. Bills rotate out as a matter of course. The only history is git: 91 commits change `bills.json`. The plan's rule "never delete or overwrite existing state records" can't literally hold under the current design. The realistic version is: don't change *how* state bills get selected, and keep every past snapshot in git, which already happens. Step 2 will record this honestly instead of inventing a database.
2. **Bot pushes to `main` twice a day.** Any work has to rebase cleanly over `docs/bills.json` commits. Work belongs on a branch.
3. **The Congress.gov API needs a key** (api.data.gov). None is configured. It has to be added by you as a GitHub Actions secret and must never be written into the public JSON or logs.
4. **Congress.gov discovery.** As far as I know the v3 API has no keyword search. Finding environmental bills likely means listing bills by update date per Congress, then using per-bill detail or `policyArea`/`subjects`, which costs more calls. The documented rate limit (believed to be 5,000/hr) and paging still need confirming against the current docs in Step 4. This is the main design unknown for federal.
5. **Failure isolation.** Today one script writes one file. If federal ingestion went into `fetch_bills.py`, a federal crash could take state refreshes down with it, and a merged file means one error state on the page.
6. **Front-end assumptions.** `b.state` is shown in the bill column and fills the State dropdown. `group()` knows only Bill Commons statuses. The link label says "legislature site". Federal records would show a blank or odd state and need their own label.
7. **Title-only classification.** Bill Commons gives no summary, so state categories stay title-based. Federal bills have official summaries and `policyArea`, which allows better classification there. The two will be classified with different evidence, and that should be documented.
8. **Identifier collisions.** State `id`s are UUIDs. A federal id of the form `us-congress-119-s-5653` can't collide with them.
9. **Live page edits are manual** (Squarespace editor via Chrome), and there's no staging page. Previewing will need either a local HTML harness or an unlinked Squarespace page. Either way, your approval comes first.

### Recommended approach

- **State pipeline untouched in logic.** Step 3 changes only the `CATEGORIES` table and lets `topics` hold several values. `category` stays as the primary category so nothing that reads it breaks.
- **Federal as a separate script and file.** Add `fetch_federal.py`, which writes `docs/federal.json`, run as its own workflow step with `continue-on-error` (or as its own job). It gets its own `generated_at`, `last_success_at` and `last_error`. State refreshes can't be blocked by it.
- **Embed fetches both files independently,** each with its own error state. Changes to the embed: a jurisdiction control (All / Federal / State), the State dropdown shown only for State or All, a jurisdiction label on every row, and a federal link label of "View on Congress.gov". Everything else in the live design stays.
- **Federal record = the state record shape plus fields:** `jurisdiction`, `congress`, `bill_type`, `bill_number`, `sponsor`, `summary`, `actions[]`, `committees[]`, `enacted_date`, `source_updated_at`, `last_verified_at`. State records gain `jurisdiction: "state"`. The embed treats a missing value as state, so the old feed keeps working.
- **Tests:** add `pytest` with fixtures for `categorize`, `shape`, `mark_movement`, and federal normalization. No live API calls in tests.

## 7. Unknowns and decisions needed

**Can't be established from the repo:**
- Bill Commons anonymous rate limits and terms. The code assumes about 1 call every 2 s works, and the run history suggests it does.
- Whether anything besides the Squarespace block reads `bills.json`. Changes will stay backward-compatible regardless.
- Congress.gov API key: you need one.
- Whether a staging or unlinked Squarespace page is available for previews.
- **BAAJA:** secondary sources (CRS report listings, IFP, Earthjustice) identify it as the *Bipartisan American Affordability and Jobs Act of 2026*, **S. 5653, 119th Congress**, introduced 2026-09-30 by Sen. Capito. It's a permitting-reform bill. **This is unverified.** Step 5 will confirm it on Congress.gov. Note that it's mainly energy and infrastructure permitting, so it would test Building & Energy versus Infrastructure & Resilience.

**Decisions for you (needed by Steps 3–4):**
1. Where utility-scale clean energy (solar and wind farms, storage) and transmission go in the new taxonomy: Building & Energy, Climate & Emissions, or Infrastructure & Resilience.
2. Whether federal bills are discovered automatically (keyword/policy-area scan of the current Congress) or through a small curated watchlist of bill IDs fetched by the normal pipeline. A watchlist is reliable but not "coverage". A scan is broader but costs more and is noisier.
3. Approval to keep `bills.json` backward-compatible (adding fields only) and add a separate `federal.json`, rather than restructuring into one feed.

**Decided 2026-11-13:**
1. Utility-scale clean energy and transmission go to **Infrastructure & Resilience**.
2. Federal bills are found by **automatic scan**.
3. Feed format is **approved**: `bills.json` is extended by adding fields only, and federal bills go in a separate `federal.json`.
4. You have a Congress.gov key. It will go in as a GitHub Actions secret, `CONGRESS_API_KEY`, and will not be shared in chat.
