# Launch Readiness

Step 8, 2026-11-14. **Everything here is a draft.** Nothing has been published, scheduled, emailed or posted.

**Status of earlier steps:**
- Steps 1–7 are complete.
- `tracker-validation-report.md` recommends ready for review.
- The tracker itself is already live, as you approved on 2026-11-14: https://www.regenconsults.com/legislation-tracker

**Announcement draft:**
- Google Doc "Legislative Tracker Announcement Draft": https://docs.google.com/document/d/1e4MlrQJwc1Z8VP_fJ4_35bQyEMuqMREdCARQQdTMGHc/edit
- It follows the format of the posts in *LinkedIn Posts & Scripts › Posted*: a "LinkedIn Post Draft" heading, a Theme / Topic / Angle table, the carousel slides, then the post text with hashtags.

## 1. Verified public-facing features

Each item was checked on the live page (2026-11-14) or in the validation report.

| Feature | Verified wording |
|---|---|
| Coverage | U.S. congressional bills and joint resolutions from the current (119th) Congress, plus state legislation drawn from all 50 states and D.C. |
| Selection | Highlights recent activity (official action in the last 180 days), up to 6 bills per category in each feed (12 for Infrastructure & Resilience). **It is not every bill.** |
| Jurisdiction filter | All · Federal · State, plus a state selector |
| Categories | Building & Energy · Climate & Emissions · Water Resources · Land Use & Development · Materials & Circularity · Nature & Biodiversity · Environmental Justice · Infrastructure & Resilience |
| Status filter | All · Active · Enacted · Inactive. Each bill also shows its specific stage, e.g. "Reported by committee", "Passed one chamber". |
| Search | Bill number (with or without punctuation, e.g. "HR 9340"), title, latest action. For federal bills, also sponsor and official summary. |
| Bill details | Latest official action and date; dates such as introduced, passed House or Senate, and signed into law **when the record has them**. Federal bills also show sponsor, committee and the official CRS summary. |
| Official links | Every bill links to its official page: Congress.gov for federal bills, the state legislature's site for state bills |
| Freshness | Separate "State data updated…" and "Federal data updated…" times on the page |

## 2. Data sources and coverage wording

- **Federal:** "Federal bill data comes from Congress.gov, the official source for U.S. federal legislative information (Library of Congress)."
- **State:** "State bill data comes via Bill Commons, sourced from official state legislative records and Open States."
- **Scope:** use **"U.S. congressional bills"** or **"bills in Congress"**. Never "all federal legislation" or "every bill".
- **Update timing:**
  - Both feeds run on an automatic twice-daily schedule. The first scheduled federal run succeeded on 2026-11-14 (run 43617943953).
  - GitHub doesn't guarantee start times: that run was due at 11:00 UTC and started at 16:52 UTC.
  - Safe wording: **"refreshed automatically, typically twice a day"**. Avoid exact times.
  - The drafts leave timing out entirely. Add it only after the 23:00 UTC run is also confirmed, if you want it.

## 3. Limitations to disclose

- **Selection:** the tracker highlights a curated selection of recent activity, not every bill.
- **Not covered:**
  - local ordinances
  - federal agency regulations and rules
  - executive orders
  - simple and concurrent resolutions in Congress
- **Editorial categories:** assigned automatically from official titles and summaries, so a bill can be miscategorized or missed. A federal bill without an official summary yet is categorized from its title only.
- **No effective dates:** federal records don't include effective dates, so the tracker never estimates one.
- **Not legal advice:** the page footer already says so.

## 4. Two-slide carousel

The copy is from the plan.
- **Visual style:** use ReGen's existing look, matching the site: dark green `#1f3510` field, cream `#fdfdf2` text, the light thin display face from the site headings, and the starburst REGEN mark.
- **Slide 1:**
  - Headline: **"The policies we put in place today shape the built environment of tomorrow."**
  - Supporting line: "Environmental legislation matters."
  - Layout: headline large, centered on the dark-green field; supporting line smaller below; REGEN mark bottom-left.
- **Slide 2:**
  - Headline: **"Stay informed. Understand what's changing."**
  - Supporting line: "Explore environmental legislation across federal and state jurisdictions."
  - URL: **regenconsults.com/legislation-tracker**
  - Layout: headline and supporting line on top; the screenshot below in a rounded frame on the cream background, cropped to the tracker area; URL at the bottom.
- **Screenshot:** genuine, captured from the live page on 2026-11-14 with the page zoomed out to 62%; the image itself is unedited.
  - What it shows: Climate & Emissions selected, with federal (S. 5706) and state (MA, NJ, IL) bills side by side.
  - File: `docs/launch/tracker-screenshot-2026-11-14.jpg`, 1420×693.
  - It's also inserted in the Google Doc.

## 5. LinkedIn post draft

The full text is in the Google Doc. The claims in it map to §1 and §2:
- federal + state
- the eight categories
- jurisdiction, state, status and category filters
- search by bill number or keyword
- status, latest official action and key dates where available
- official links
- sources
- scope and limitations

It makes no claim about update frequency.

## 6. Items still needing your review

1. **Read the announcement draft** in the Google Doc: wording, tone, hashtags.
2. **Design the two slides** from the copy and layout notes in §4. The slides themselves aren't made, only the copy and notes.
3. **Refresh-timing wording:** decide whether to add it. The 23:00 UTC run check is pending and will be reported.
4. **Known data issue (cosmetic):** House/Senate companion bills whose titles differ slightly can both appear, e.g. H.R. 331 and S. 1254 (Aquifer Recharge Flexibility Act). The dedupe matches identical titles only. Fixing it means matching on a normalized title, a small pipeline change I can make if you want it.
5. **Optional cleanup:** remove the 3-day `federal-cache` artifact upload from the workflow.
6. **Posting:** posting, scheduling or sharing the announcement is yours to do. I haven't done any of it.
