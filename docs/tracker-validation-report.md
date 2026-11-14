# Tracker Validation Report

Step 7, 2026-11-14.
- **Scope:** the merged `main` (merge commit `7e46c41`), the live feeds at `https://regenconsults.github.io/bill-feed/{bills,federal}.json`, and the live page `https://www.regenconsults.com/legislation-tracker`.
- **Release:** you approved merging and pasting the new embed on 2026-11-14, so this validation covers the released state as well as the pre-release checks.

## 1. Checks run

| Check | Result | Notes |
|---|---|---|
| Unit tests (`python -m unittest discover -s tests`) | **Pass, 54/54** | Local Python 3.9 and CI Python 3.12, `test` job on every run. No network: fixtures are real saved responses. |
| Integration (live runs) | **Pass** | Branch runs 1–5 and the first `main` run (§5). |
| Python compile (`py_compile`) | Pass | |
| Workflow YAML parse | Pass | |
| Linting / type checking / build / end-to-end | **Not available** | The repo has no linter, type checker, build step or e2e suite. Nothing was skipped; there's nothing to run. The embed was exercised in Chrome instead (§6). |
| State regression cases (baseline R1–R12) | **Pass** | Against the baseline feed in the local harness, and against the live page (§2). |
| Credentials exposure | **Pass** | §7. |

## 2. State baseline comparison

**Baseline:** tag `baseline-2026-11-13` (`1f80f8d`), 45 bills, plus the backup in `bill-feed-backups/2026-11-13/`.
**Now:** the live `bills.json` (generated 2026-11-14 13:27 UTC), 52 bills.

**Record count, 45 → 52, explained.** The selection rule is unchanged (6 per primary category, newest first), but the eight categories changed:
- The old feed: seven categories at 6, and Environmental Equity at 3. Total 45.
- The new feed: six categories at 6, Infrastructure & Resilience at 12 (approved), and Environmental Justice at 4. Total 52.

**Records:**
- **31 of the 45 baseline bills are still published.** For all 31, bill number, state, title, URL, session and latest action date are identical to the baseline. Nothing was corrupted.
- **14 are no longer in the snapshot:**
  - **PA HR 652:** removed on purpose. It's a game-warden pay bill and was a false positive; the change was reviewed in Step 3.
  - **13 others** are still in the 180-day window and still match a category, but newer bills outrank them. Nine of the 13 are energy or transport bills:
    - The old Clean Energy, Grid, Buildings and Transportation categories had 24 slots between them. Their replacements, Building & Energy plus Infrastructure & Resilience, have 18.
    - The other four (CA AB 1663, and three energy-efficiency bills from NH, NY and CA) were outranked by newer bills in the same category.
  - None of the 14 was deleted from any source. The feed has always been a rotating snapshot (see `tracker-audit.md`), and git history keeps every earlier version.

**Regression cases on the live page (2026-11-14):**

| Case | Baseline | Live | Explanation |
|---|---|---|---|
| State tab, `HB 6486` | 1 | 1 | — (checked against the live feed) |
| `solar` | 4 | 5 | One newer solar bill is in the snapshot |
| `recycl` | 2 | 2 | — |
| NJ | 11 | 11 | — |
| NJ + Enacted | 0 | 0 (empty state shown) | — |

- **Embed behavior:** every case gives the same result as the old embed when run on the same feed file (local harness, `tracker-interface.md`).
- **Snapshot drift:** the live differences are snapshot changes, not embed changes.

## 3. Federal test bills against official sources

Full field-by-field tables are in `federal-test-cases.md`.
- **S. 5653 (BAAJA):** matches Congress.gov. In committee; Infrastructure & Resilience plus Water Resources, from the official summary.
- **S. 465:** matches. Reported.
- **H.R. 9340:** matches. Passed one chamber; a failed Senate cloture vote is not treated as failure.
- **S. 240:** matches. Enacted, Public Law 119-122, both passage dates and the signing date.
- **Live feed, every enacted record:** the federal feed carries all four environmental laws enacted in the window (S. 240, H.R. 7250, S. 629, H.R. 972). Their law numbers match `GET /law/119`.

## 4. Data-quality checks (live feeds, scripted)

Run 2026-11-14 against the published files. **No problems found.**

| Check | Result |
|---|---|
| Duplicate federal bills | none (45 unique IDs). Companion bills with identical titles are deduplicated. |
| Federal/state ID collisions | none. Federal IDs all match `us-congress-{n}-{type}-{n}`, and no state ID starts with `us-congress-` |
| Missing or malformed official URLs | none. Every federal URL is `https://www.congress.gov/bill/…`, and every state URL is http(s) |
| Invalid category references | none. Every `category` and `categories` slug is one of the eight, `topics` matches `categories`, and the primary comes first |
| Contradictory statuses | none. Enacted ⇒ enacted date + law number, and law fields appear only on enacted bills. Passed ⇒ a passage date. No `effective_date` is inferred |
| Date format, timezone | All dates are `YYYY-MM-DD`. The embed formats them at local noon, so no time zone can shift the day. No introduced or enacted date falls after the latest action |
| Stale records | none older than 180 days. Future dates appear only on records flagged `upcoming` (scheduled state hearings) |
| Failed refreshes | Federal `sync.status = ok`, `last_error = null` |
| Pagination | Each run listed 11,401 bills of the four types, the same across runs. Paging stops at `pagination.count`. Tests cover multi-page lists |
| Rate limits | 0 errors in every run. A few 429s and timeouts were retried successfully. A run stays under 5,000 calls per hour (3,500 per-run budget, 0.75 s pacing) |

## 5. Sync and failure isolation

- **The jobs refresh independently.**
  - The federal job runs after the state job whether or not it succeeded, and it writes only `federal.json`. The state job never reads the federal feed.
  - Branch runs 1–5: every federal run succeeded. The state job failed once (run 4), on a git push race. The federal job and the tests still passed. That race is now fixed with a pull-and-retry.
- **Federal API failure:**
  - **Tested offline:** an API error keeps the last good federal feed and records `sync.status = error`. A missing key fails without touching `bills.json`.
  - **In the browser:** a page whose federal feed returns 404 shows all state bills, a "Federal legislation is temporarily unavailable" line, and a notice. The reverse case and both-down were also tested.
- **Idempotency:**
  - Branch run 4 made only list calls: 48 calls, 0 detail fetches, 0 hydrations, the same 45 IDs.
  - Unit test: a second run with no source changes makes only the list calls.
- **Source updates:** a changed `updateDateIncludingText` re-fetches the bill, updates the record and its `source_updated_at` and `last_verified_at`, and marks it moved (unit test).
- **Cold cache on `main`:**
  - Actions caches can't be shared from a branch to `main`, so the first `main` run starts empty.
  - Before merging I added a rule: a partial run keeps the previously published federal bills and records `partial` (test `test_partial_run_keeps_previous_bills`). The cold start therefore can't thin out the live feed.
  - **First `main` run (43604518546):** see the addendum.

## 6. Interface: responsive and accessibility

Checked in Chrome, in the local harness and on the live page.
- **Desktop (1284px):** the page renders with the site's own fonts and styles.
- **Phone (390px frame):** rows stack and nothing scrolls sideways (`scrollWidth = 390`).
- **Live page:** no horizontal overflow, and no console errors.
- **Keyboard and screen readers:**
  - Chips are buttons with `aria-pressed` in labelled groups.
  - Rows keep `aria-expanded`.
  - Focus returns to the chip or row that was used.
  - `:focus-visible` outlines are visible.
  - The update lines and result count are announced politely.
- **Filters and search on the live page:**
  - All: 97. Federal: 45. State: 52. Federal + Enacted: 4.
  - `S 5653` → 1, with a Congress.gov link.
  - Choosing a state hides federal bills.
  - Clear filters resets everything.

## 7. Credentials

- The key is only in the Actions secret `CONGRESS_API_KEY`. It's sent as a request header, never in URLs.
- Run logs show it masked (`***`) for all runs checked: 5 branch runs. No log contains `api_key=` or a header value.
- No key-like string appears in tracked files, and no `.env` or credential file was ever committed.
- `federal.json`, `bills.json`, the embed, and the `federal-cache` artifact contain no key. The browser never receives one: the page reads only public static JSON.
- The `DEMO_KEY` used for spot checks is Congress.gov's public demo key.

## 8. Known limitations and open issues

1. **The feed is a selection, not complete coverage.** Up to 6 bills per category (12 for Infrastructure & Resilience) in each feed. The page copy says "bills moving through…", not "all bills".
2. **Title-only federal classification before CRS summaries exist.** About 370 federal bills with an environmental policy area match no category. They're mostly land conveyances, memorials and trails, oil and gas, nuclear licensing, critical minerals, and disapproval resolutions whose titles name no subject. They're logged as needs-review on every run, and many will classify once their summaries are published.
3. **Ties between categories** go to chip order, e.g. "Great Lakes Wolf Recovery" → Water Resources first, Nature second.
4. **No effective dates** for federal bills; the API doesn't provide them.
5. **The scheduled (cron) runs of the federal job haven't happened yet.** Every federal run so far was started by hand. That's why the page makes no refresh-frequency claim. The first scheduled runs on `main` are 23:00 UTC today and 11:00 UTC tomorrow.
6. **The `federal-cache` artifact** (3-day retention) can be downloaded from the public repo. It holds only public Congress.gov data. It's optional and can be removed.
7. **Rollback:**
   - Embed: `squarespace-code-block.live.html` is the pre-federal embed (SHA-256 `74fe7679…eb89d`), plus the backup folder.
   - Data: revert merge `7e46c41` on `main`.
   - The live block's SHA-256 before the paste matched this backup exactly. After the paste it's `603be986…0ce4`, the same as `squarespace-code-block.federal.html`.

## 9. Release recommendation

**Ready for review, and released with your approval on 2026-11-14.**
- All automated checks that exist pass.
- The federal data matches official sources for the tested bills.
- There are no duplicate or colliding IDs.
- A federal outage leaves state results usable.
- No credentials are exposed.
- Every state difference from the baseline is explained.

Before Step 8 announces it: confirm the first two scheduled runs on `main` (item 5) succeed.

## Addendum: first `main` run

[Run 43604518546](https://github.com/regenconsults/bill-feed/actions/runs/43604518546), dispatched on `main` right after the merge: **success**.

- **State job:** 14:22–14:27 UTC, success. Published 52 bills, all with `jurisdiction: "state"`.
- **Tests:** 54/54 pass.
- **Federal job:** 14:27–15:23 UTC, success. This is the cold-cache case.
  - 3,500 calls (the budget), 0 errors.
  - Listed 11,405 bills; 4,178 in the window; 2,276 details fetched; 1,901 pending.
  - The new safeguard engaged: "Sync incomplete (1901 pending); kept the previous 45 bills".
  - The live `federal.json` still has the same 45 bills, including the 4 enacted laws, with `sync.status = "partial"` and `last_error = "1901 bills pending; previous bills kept"`. `last_success_at` (shown on the page) is still 13:27 UTC.
- **Data-quality script after the run:** no problems, 0 cross-feed collisions.
- **Expected next:** the 23:00 UTC scheduled run (the first cron run of the federal job) should finish the backlog, return to `ok`, and publish a fresh selection. Confirming that is the remaining item in §8.5.
