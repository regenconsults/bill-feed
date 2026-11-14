# Federal Data Integration (Congress.gov)

Step 4, 2026-11-13. Code: `fetch_federal.py`. Output: `docs/federal.json`. Tests: `tests/test_federal.py`.

## Scope

- **Included:** bills and joint resolutions (**H.R., S., H.J.Res., S.J.Res.**) in the **current Congress** (119th as of 2026-11-13) with official action in the last 180 days, the same window the state feed uses.
- **Excluded:**
  - Simple and concurrent resolutions (H.Res., S.Res., H.Con.Res., S.Con.Res.), because they can't become law.
  - Agency rules, executive orders, and state or local actions.
- **Coverage is automatic.** Discovery is a scan of the whole current Congress, not a curated list. The published feed is still a *selection*: up to 6 bills per primary category, 12 for Infrastructure & Resilience, the same rule as the state feed. Within each category, **enacted bills come first**, then the most recently active (decision 2026-11-14; the state feed stays recency-only). "All environmental bills in Congress" would overstate it.

## Endpoints and fields used

All calls go to `https://api.congress.gov/v3`, with `format=json`.

| Endpoint | Used for |
|---|---|
| `GET /bill/{congress}/{type}?sort=updateDate desc&fromDateTime=…&limit=250&offset=…` | Discovery: every bill of that type updated in the window. Gives `type, number, title, latestAction, updateDate(IncludingText)` |
| `GET /bill/{congress}/{type}/{number}` | Detail: `policyArea, sponsors, cosponsors.count, introducedDate, latestAction, laws, legislationUrl, originChamber, updateDateIncludingText` |
| `…/actions?limit=250` | Dated action history, status, and passage and enactment dates |
| `…/summaries?limit=250` | Official CRS summary, the latest version, with HTML stripped |
| `…/committees?limit=250` | Committee names |

Notes:
- **Verified against live responses on 2026-11-13:**
  - Field names, pagination (`pagination.count`, `pagination.next`), list sorting, and the `laws` array.
  - Rate-limit headers (`x-ratelimit-limit`, `x-ratelimit-remaining`). With `DEMO_KEY` they showed a limit of 10.
- **From the official docs** (`LibraryOfCongress/api.congress.gov` README and BillEndpoint.md):
  - 5,000 requests/hour per key.
  - `limit` maximum 250.
  - No keyword-search parameter on bill lists, which is why discovery scans the list.
- **Not stated in the docs:** behavior when the rate limit is exceeded. The script treats `429` as retryable regardless.

## Authentication and secrets

- The key is in the GitHub Actions secret **`CONGRESS_API_KEY`**, which you created on 2026-11-14 UTC. The workflow passes it only to the federal step.
- The script sends it as the `X-Api-Key` **header**, never as a URL parameter. So it can't show up in URLs, exception messages, logs, or the `next` links the API returns. A test checks this.
- `federal.json` never contains the key; a test checks this too. Error messages written to the feed contain only the exception type and call count.
- If the key is missing, the federal sync records `sync.status = "error"`, `last_error = "CONGRESS_API_KEY is not set"`, and exits 1. The state feed is not touched.

## Identifier strategy

- **`id` format:** `us-congress-{congress}-{type}-{number}`, e.g. `us-congress-119-s-5653`.
- **Why it can't collide:** state `id`s are Bill Commons UUIDs, and none starts with `us-congress-`. A test checks this. The Congress number is in the ID, so H.R. 1 in the 119th and H.R. 1 in the 120th are different records.
- **Display identifier:** `bill`, e.g. `S. 5653`, `H.J.Res. 12`.
- **Structured fields:** `congress`, `bill_type`, `bill_number`.
- **Jurisdiction:** `jurisdiction: "federal"`, `legislative_body: "U.S. Congress"`, `state: null`. State records have no `jurisdiction` field yet, and the embed will treat a missing value as `state`. Step 6 will add the field to state records.
- **Official link:** `url` is Congress.gov's `legislationUrl`. If that's missing or isn't a `https://www.congress.gov/` URL, it's rebuilt from the ID, e.g. `https://www.congress.gov/bill/119th-congress/senate-bill/5653`.

## Discovery and classification

1. List all four bill types updated since (today − 180 days), newest first, and keep those whose **latest action** is in the window.
2. For each bill that's new, or whose `updateDateIncludingText` changed since the cached copy, fetch the detail.
3. **Candidate** if its `policyArea` is one of *Environmental Protection, Energy, Water Resources Development, Public Lands and Natural Resources*, **or** its title matches any category pattern.
   - Policy area matters: BAAJA's title ("Bipartisan American Affordability and Jobs Act of 2026") matches nothing, but its policy area is Environmental Protection.
4. For candidates, fetch actions, summaries and committees.
5. **Categories** use the same eight-category patterns as state bills (`fetch_bills.score_categories`).
   - A category applies if the **title** matches at least one pattern, or the **official summary** matches at least **2** distinct patterns. One passing mention in a long summary isn't enough.
   - Primary category = highest of (2 × title score + summary score); ties go to whichever category is listed first.
   - `classification: "auto-title-summary"` marks the tags as editorial, not a source fact.
6. **Fallback:** a candidate with no category is **not published**. It's counted in `sync.needs_review`, and its ID is printed in the run log.
7. **Companions:** House and Senate versions with identical titles are published once, keeping the one with the most recent action.

## Status and action normalization

Status comes only from the official record. The latest action text is always kept beside it (`latest_action`, `latest_action_date`, plus the most recent 30 `actions` with `actions_total`).

| `status` | Label | Rule (first match wins) |
|---|---|---|
| `enacted` | Enacted | Detail has `laws[]`, or an action of type `BecameLaw` / text "Became Public (Private) Law" |
| `vetoed` | Vetoed | A `Veto` action "Vetoed by President" with no later enactment (an override → enacted) |
| `passed_both` | Passed both chambers | Passage actions recorded for both House and Senate |
| `passed_one_chamber` | Passed one chamber | Passage action in one chamber ("Passed/agreed to in House/Senate", "On passage Passed", suspension "…Agreed to") |
| `reported` | Reported by committee | Reported or ordered reported, or placed on a calendar |
| `in_committee` | In committee | Committee referral (committees count or "Referred to") |
| `introduced` | Introduced | Has actions or an introduced date, but nothing above |
| `other` | Other / needs review | Nothing above applies |

Notes:
- `reported` is one addition to the plan's list. It's a real, common stage that "In committee" would misstate.
- **Failure is never inferred.** There's no federal "Failed" status: a bill that stalls, or whose Congress ends, keeps its last real status.
- **Dates:** `introduced` (`introducedDate`), `passed_house_date`, `passed_senate_date` (first passage action), `enacted_date` (the BecameLaw action).
- **`effective_date` is always `null`.** The API doesn't provide effective dates, and an enactment date is not an effective date.
- **Embed status chips:** `enacted` → Enacted; `vetoed` → Inactive; everything else → Active. The existing embed already groups this way, because `vetoed` is in its inactive list.

## Pagination, rate limits and retries

- **Pagination:** `offset` steps by 250 until `pagination.count` is reached.
- **Pacing:** 0.75 s between calls, about 4,800/hr, under the 5,000/hr key limit.
- **Per-run budget:** 3,500 calls (`FEDERAL_MAX_CALLS`). Once it's spent, the run stops cleanly. Everything already fetched is cached, and the next run continues from the cache.
  - The first run, with an empty cache, may need two or three runs to work through the backlog. Bills are processed newest-first, so the most current ones are covered first.
  - **A partial run never replaces a published feed.** If a run ends with bills still pending and a previous feed exists, the previous bills stay, and `sync.status` is set to `partial` with "previous bills kept". `last_success_at` doesn't change. This matters on `main`'s first run, because Actions caches made on a branch can't be read from `main`.
- **Retries:**
  - `429` or `5xx`: up to 4 retries, waiting `Retry-After` or 60/120/180/240 s.
  - Connection errors: up to 4 retries.
  - Any other per-bill HTTP error is logged and that bill is skipped.
  - A list-level failure fails the sync.
- **Idempotent:** records are keyed by ID, and a rerun with no source changes makes only the four list calls, with no duplicates. Tests cover this.

## Refresh cadence and isolation

- **Schedule:** the existing workflow, `refresh-bills.yml`, on the same twice-daily schedule. The state cadence is unchanged.
- **Jobs:** the workflow now has three.
  - **`refresh`** (state) is byte-for-byte the previous job.
  - **`federal`** runs after it with `if: always()`, so it runs even if the state job fails. It writes only `docs/federal.json`. Its fetch step is `continue-on-error`, so `federal.json` is still committed with its error status. A final step then marks the job failed, so the failure shows in the Actions tab.
  - **`test`** runs the unit tests in parallel and gates nothing.
- **Cache:** the detail cache (`data/federal-cache.json`) is kept with `actions/cache` and is not committed (`data/` is in `.gitignore`). If the cache is lost, the next run rebuilds it within the per-run budget.

## Observability

`docs/federal.json` → `sync`:
- `status`: `ok`, `partial` (budget hit or some per-bill errors), or `error`.
- `last_success_at`, `last_attempt_at`, `last_error`.
- `api_calls`, `needs_review`, `candidates_in_window`.
- Top-level `generated_at` changes only on a successful write.

Plus the Actions run log line: `N API calls, E errors; listed …, recent …, details …, hydrated …, pending …; … categorized, … need review, … in feed`.

## Known data limitations

- **Summary lag:** CRS summaries often appear days or weeks after introduction. Until one does, a bill is categorized from its title only, or held as needs-review.
- **Cosponsors:** only the count is stored, not names. That saves one call per bill.
- **Action cap:** bills with more than 250 actions (rare, very large bills) are capped at the first 250 returned. The latest action still comes from the detail record.
- **Effective dates** are never available.
- **First run:** the first production run will likely end `partial` until the cache is built.
- **Congress turnover:** after a new Congress convenes, the previous Congress's bills drop out of the feed.

## Live test runs (branch `federal-expansion`, 2026-11-14 UTC)

Both runs used the real `CONGRESS_API_KEY` secret through `workflow_dispatch` on the branch. Nothing was merged to `main`, and the published `bills.json` was not touched by these runs.

| | Run 1 ([43543815457](https://github.com/regenconsults/bill-feed/actions/runs/43543815457)) | Run 2 ([43550101393](https://github.com/regenconsults/bill-feed/actions/runs/43550101393)) |
|---|---|---|
| Cache at start | empty | from run 1 |
| API calls / errors | 3,500 (budget) / 0 | 2,655 / 0 (1 timeout, retried) |
| Bills listed / in 180-day window | 11,401 / 4,171 | 11,401 / 4,171 |
| Details fetched / pending | 2,258 / 1,914 | 1,913 / **0** |
| Candidates / categorized / needs review | 379 / 124 / 255 | 585 / 174 / 411 |
| Published | 42 | 45 (no duplicate IDs) |
| `sync.status` | `partial` | **`ok`** |
| Federal job time | about 62 min | about 50 min |

- **The backlog clears in two runs**, as expected. Steady-state runs re-fetch only bills whose source changed.
- **BAAJA (S. 5653)** is in the run 2 feed: primary Infrastructure & Resilience, plus Water Resources, both from its summary; status `in_committee`.
- **Fixes after run 1:** false positives on "resiliency" (archives, cybersecurity), "critical infrastructure" and nuclear-fuel "recycling" were removed. Test: `test_first_live_run_false_positives`.
- **Fixes after run 2:** 28 clearly environmental bills held as needs-review now match, through added patterns for federal water programs (Water Pollution Control Act, Water Resources Development Act, desalination, irrigation, reservoirs, Great Lakes, dam safety), species recovery and named species, ozone and New Source Review, and microplastics. Test: `test_second_live_run_missed_titles`. The state regression tests still pass, so no state bill changed category.
- **Toxics and chemical safety** (pesticides, paraquat, asbestos, Safer Choice, Chemical Safety Board, toxics in plastic bottles) had no category. **Decision 2026-11-14: Materials & Circularity.** With the new patterns, 11 more run 2 bills match.
- **Unplaced by design:** most of the rest are land conveyances, memorials, trails and parks, nuclear licensing, critical minerals, oil and gas, and Congressional Review Act disapproval resolutions whose titles name no subject. Many will classify once CRS publishes their summaries.
