# Federal Test Cases

Step 5, 2026-11-14. Four real 119th-Congress bills, each at a different stage, checked from Congress.gov API responses through the real code path (`fetch_federal.shape`) and against the published `docs/federal.json` on branch `federal-expansion`.

How each record was checked:
- **S. 5653, S. 240:** the saved API responses are test fixtures (`tests/fixtures/congress/`), and unit tests assert the published fields.
- **H.R. 9340, S. 465:** the published record from live run 2 was compared field by field with a fresh `GET /bill/119/{type}/{number}` made 2026-11-14 with the public `DEMO_KEY`.
- No fixture or feed file contains an API key; this was checked with grep.

## Summary

| Bill | Stage | `status` | Primary / other categories | In feed? | Check |
|---|---|---|---|---|---|
| **S. 5653**, Bipartisan American Affordability and Jobs Act of 2026 (BAAJA) | Referred to committee | `in_committee` | Infrastructure & Resilience / Water Resources | Yes (runs 2–4) | `test_s5653_matches_official_record`, `test_s5653_classified_from_summary_not_title` |
| **S. 465**, GRID Power Act | Reported, on Senate calendar | `reported` | Infrastructure & Resilience | Yes | Live comparison |
| **H.R. 9340**, Ratepayer Protection Act | Passed House; Senate cloture failed | `passed_one_chamber` | Infrastructure & Resilience | Yes | Live comparison |
| **S. 240**, Crow Tribe Water Rights Settlement Amendments Act of 2025 | **Enacted**, Public Law 119-122 | `enacted` | Water Resources | No (outranked by recency, see below) | `test_s240_enacted_law_matches_official_record` |

## S. 5653: BAAJA (required case)

Official page: https://www.congress.gov/bill/119th-congress/senate-bill/5653

| Field | Official source | Feed record | Match |
|---|---|---|---|
| ID / display | S. 5653, 119th Congress | `us-congress-119-s-5653` / `S. 5653` | ✓ |
| Title | Bipartisan American Affordability and Jobs Act of 2026 | same | ✓ |
| Sponsor / cosponsors | Sen. Capito, Shelley Moore [R-WV] / 3 | same / 3 | ✓ |
| Introduced | 2026-09-30 | `2026-09-30` | ✓ |
| Latest action | 2026-09-30: Read twice and referred to the Committee on Energy and Natural Resources. | same | ✓ |
| Committee | Energy and Natural Resources | `Energy and Natural Resources Committee` | ✓ |
| Policy area | Environmental Protection | same | ✓ |
| Summary | CRS, "Introduced in Senate (2026-09-30)" | same version, HTML stripped | ✓ |
| Enacted / effective date | none | `null` / `null` | ✓ |

- **Classification:**
  - The title matches no category pattern.
  - The bill became a candidate through its policy area.
  - Its categories come from the official summary (permitting and environmental reviews; water and energy infrastructure): **Infrastructure & Resilience** (primary) and **Water Resources**.
  - Nature & Biodiversity scored 1 (one mention of endangered species), below the 2-match threshold, so it isn't tagged.
  - `classification: "auto-title-summary"` marks the tags as editorial.
- **Discovery:** BAAJA wasn't in run 1's feed, because the budget ran out before its detail was fetched. It has been in the feed since run 2, the first complete sync.

## S. 465: GRID Power Act (reported)

Official page: https://www.congress.gov/bill/119th-congress/senate-bill/465

- **Matches live:** title, sponsor (Sen. Hoeven, John [R-ND]), policy area (Energy), latest action (2026-11-12, "Placed on Senate Legislative Calendar under General Orders. Calendar No. 698.").
- **Status `reported`:** the committee reported it on 2026-11-12. That's a stage "In committee" would misstate.
- **Passage dates:** none, correctly.

## H.R. 9340: Ratepayer Protection Act (passed one chamber)

Official page: https://www.congress.gov/bill/119th-congress/house-bill/9340

- **Matches live:** title, sponsor (Rep. Evans, Gabe [R-CO-8]), policy area (Energy), latest action (2026-09-30, "Motion to proceed to consideration of measure withdrawn in Senate. (CR S5199)").
- **Status `passed_one_chamber`:**
  - `passed_house_date` is 2026-09-16.
  - Senate cloture on the motion to proceed was not invoked (2026-09-30). The bill is **not** marked failed or inactive, because a failed cloture vote doesn't end a bill.
  - This checks the "never infer failure" rule on a real record.

## S. 240: Crow Tribe Water Rights Settlement Amendments Act (enacted)

Official page: https://www.congress.gov/bill/119th-congress/senate-bill/240

| Field | Official source | Feed record | Match |
|---|---|---|---|
| Status | Became Public Law No: 119-122 | `enacted` / "Enacted" | ✓ |
| Law number | 119-122 (also in `GET /law/119`) | `Public Law 119-122` | ✓ |
| Passed Senate | 2025-12-11 | `passed_senate_date: 2025-12-11` | ✓ |
| Passed House | 2026-09-14 | `passed_house_date: 2026-09-14` | ✓ |
| Signed | 2026-10-15 | `enacted_date: 2026-10-15` | ✓ |
| Effective date | not provided | `null` (not inferred from signing) | ✓ |
| Sponsor | Sen. Daines, Steve [R-MT] | same | ✓ |
| Policy area | Native Americans | same | ✓ |

- **Classification:**
  - The policy area is not one of the four environmental areas.
  - It was found because its title matches "water rights".
  - It's tagged **Water Resources**.
- **Not in the published feed:**
  - Each category shows its 6 most recently active bills, the same rule as the state feed.
  - Six water bills had later actions (2026-10-29 to 2026-11-12), two of them technical corrections, so this law is outranked.
  - Whether enacted laws should be prioritized is an open decision; see below.

## Sync and idempotency (live runs on the branch)

| Run | Cache | API calls | Details fetched | Pending | `sync.status` | Bills | Duplicate IDs |
|---|---|---|---|---|---|---|---|
| 1 [43543815457](https://github.com/regenconsults/bill-feed/actions/runs/43543815457) | empty | 3,500 (budget) | 2,258 | 1,914 | `partial` | 42 | 0 |
| 2 [43550101393](https://github.com/regenconsults/bill-feed/actions/runs/43550101393) | run 1 | 2,655 | 1,913 | 0 | `ok` | 45 | 0 |
| 3 [43556153715](https://github.com/regenconsults/bill-feed/actions/runs/43556153715) | run 2 | **72** | **0** | 0 | `ok` | 45 | 0 |
| 4 [43557325284](https://github.com/regenconsults/bill-feed/actions/runs/43557325284) | run 3 | **48** (list calls only) | **0** | 0 | `ok` | 45 | 0 |

- **Steady state:**
  - Run 3 made the list calls plus 8 hydrations of bills that newly matched after the pattern changes. It took 4 minutes, against about 50 for a cold start.
  - Run 4, with no source or pattern changes in between, made **only the 48 list calls**: 0 detail fetches, 0 hydrations, the same 45 bills.
- **Stable IDs:** 39 of 45 IDs carried over from run 2 to run 3. The 6 swaps came from the new toxics, ozone, desalination and microplastics patterns, under the same per-category limit. No record was duplicated or re-keyed.
- **Offline coverage (unit tests):**
  - A rerun with no source changes makes only the list calls (`test_end_to_end_and_idempotent`).
  - A changed `updateDateIncludingText` re-fetches the bill and marks it moved (`test_source_update_refreshes_record`).
  - An API failure keeps the last good feed (`test_api_failure_keeps_last_good_feed_and_records_error`).
- **Run 4's state job failed:** its `bills.json` push to the branch was rejected because I pushed fix commits during the run. The federal job and tests passed. `main` and the live feed were not affected. The same race exists on `main` if anyone pushes during the roughly 5-minute state job; a pull-and-retry like the federal job's would close it.

## Open decisions

1. **Enacted bills drop out fast.** Selection is recency-only, so a law signed a month ago is outranked by bills with routine actions such as technical corrections. Options:
   - (a) Keep it as is, matching the state feed.
   - (b) Reserve slots for, or rank first, bills enacted in the window.
2. **Run artifact:** the federal job now uploads its cache as a 3-day artifact (`federal-cache`), used here to get S. 240 without handling the key. The repo is public, so anyone signed in to GitHub can download it. It holds only public Congress.gov data. It can be removed after validation.
