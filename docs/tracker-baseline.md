# Legislation Tracker — Step 2 Baseline

Recorded 2026-11-13. Branch `federal-expansion`, cut from `main` at `1f80f8d`.

## Where the data lives

There's one data store: `docs/bills.json` in `regenconsults/bill-feed`, served by GitHub Pages. No separate development database exists. Local runs write wherever `BILL_FEED_OUT` points, and the published file is left alone.

The feed is regenerated in full on every run, so it isn't an accumulating record set. Bills rotate in and out by design: at most 6 per category, and only those with action in the last 180 days. **Every past state of the feed is kept in git history.** On 2026-11-13, 91 commits had modified `docs/bills.json`.

## Backups

| What | Location | Verification |
|---|---|---|
| Feed at baseline | git tag `baseline-2026-11-13` → `1f80f8d` (local tag, **not pushed yet**) | — |
| Feed copy | `~/Desktop/Claude/Projects/bill-feed-backups/2026-11-13/bills.json` (outside the repo) | SHA-256 `1e17d293…10a87` matches `git show baseline-2026-11-13:docs/bills.json`, and it parses as JSON |
| Live Squarespace block | same folder, `squarespace-live-block.html`, also committed as `squarespace-code-block.live.html` | SHA-256 `74fe7679…eb89d`, extracted from the served page on 2026-11-13 |
| Regression fixture | `tests/fixtures/baseline_bills_2026-11-13.json` | Identical to the tagged file |

The feed holds only public legislative data and contains no credentials, so committing it as a fixture is safe.

**Rollback:**
- Feed: `git checkout baseline-2026-11-13 -- docs/bills.json`, or any earlier commit.
- Embed: paste `squarespace-code-block.live.html` back into the Code Block.

## Baseline counts (feed generated 2026-11-13T18:28:46Z)

- **Total:** 45 state bills. All 45 `id`s are unique, and so are all 45 (state, bill, session) combinations.
- **By state:** NJ 11 · CA 10 · PA 8 · IL 4 · MI 3 · OH 2 · NH 2 · MA 2 · VA 1 · DC 1 · NY 1
- **By status:** in_committee 26 · enacted 9 · died_on_adjournment 3 · introduced 2 · passed_one_chamber 2 · withdrawn 1 · vetoed 1 · *(null → "In progress")* 1
- **By embed status chip:** Active 31 · Enacted 9 · Inactive 5
- **By category:** Clean Energy 6 · Grid & Energy Affordability 6 · Green & Healthy Buildings 6 · Clean Transportation 6 · Climate & Emissions 6 · Waste & Circular Economy 6 · Water & Land 6 · Environmental Equity 3
- **Missing or malformed fields:**
  - `url`: 0 missing or non-http
  - `title`, `bill`, `state`, `session`, `latest_action`, `latest_action_date`: 0 missing
  - `introduced`: 26 missing (Bill Commons returns null)
  - `status`: 1 missing
  - Future-dated latest action (`upcoming`): 1 (MI HB 6486, 2026-11-17)

## Representative regression cases

These are checked against the baseline fixture. The live feed changes every refresh, so the UI checks in Step 6/7 will run against this fixture loaded locally.

| # | Action in the embed | Expected on baseline |
|---|---|---|
| R1 | Load | "45 of 45 bills"; State dropdown has 11 states; category chips in feed order with counts, e.g. "Environmental Equity (3)" |
| R2 | Search `HB 6486` | 1 result: MI HB 6486, In committee, Clean Energy, Nov 17, 2026 |
| R3 | Search `solar` | 4 results |
| R4 | Search `recycl` | 2 results |
| R5 | State = NJ | 11 results |
| R6 | State = NJ + Enacted | 0 results; empty state with "Clear filters" |
| R7 | Status = Enacted / Active / Inactive | 9 / 31 / 5 |
| R8 | Category = Green & Healthy Buildings | 6: NJ S 4556, NJ S 4593, CA SB 222 (Enacted), NH HB 1748 (Died on adjournment), CA AB 196 (Withdrawn), NY A 11556 |
| R9 | Category = Environmental Equity | 3, all Enacted: CA AB 1600, CA AB 1457, IL SB 3772 |
| R10 | Expand MI HB 6486 | Latest action "bill electronically reproduced 11/12/2026 · Nov 17, 2026"; session shown; "View on legislature site ↗" links to `legislature.mi.gov/...2026-HB-6486` in a new tab |
| R11 | Feed URL unreachable | "Legislation feed is temporarily unavailable." with an orange dot |
| R12 | Previously reviewed bills (NJ AR 154, NJ S 4684, CA AB 2667) | You confirmed these are categorized correctly. They aren't in today's snapshot, so they will be spot-checked by title through `categorize()` in Step 3 |

## Automated tests

Added `tests/test_state_feed.py`. It uses stdlib `unittest`, needs no new dependencies, and makes no network calls.

```bash
python3 -m unittest discover -s tests -v
```

**Run 2026-11-13, local Python 3.9.6: 19 tests, all passed.** Coverage:
- All 45 baseline titles re-categorize to their recorded category.
- Global excludes, agency-name stripping, tie-break order, and the case-sensitive `EV` pattern.
- `shape()` output, field for field, against the MI HB 6486 API row.
- Status labels, including unknown and null; tolerant date parsing.
- Movement badges: new, moved, persisting, expired.
- Per-category cap, per-state spread, companion dedupe, no badges on first run, uncategorized bills dropped.
- `main()` keeps the existing file when the API returns nothing; the written feed has the v2 shape.

## Limitations

- **Embed not under automated test.** The embed's JavaScript (search, filters) has no automated tests, because Node isn't installed locally and the code lives in Squarespace. R1–R11 are manual checks.
- **Tag only local.** `baseline-2026-11-13` exists only on this machine until you approve pushing it. The commit itself is already on GitHub.
- **No CI test step yet.** Tests aren't wired into the workflow. That's planned for Step 4, when the workflow changes anyway.
- **Python version.** CI uses Python 3.12 and the local run used 3.9.6. The tests use nothing that differs between them.
- **No live API run.** I didn't make a live Bill Commons call in this step. The last 12 production runs succeeded, per `gh run list`.
