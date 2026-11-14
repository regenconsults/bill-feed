# Tracker Interface (federal + state)

Step 6, 2026-11-14.
- **New embed:** `squarespace-code-block.federal.html`.
- **Built from:** `squarespace-code-block.live.html`, the copy of what's live now. Same markup, same `.rgt-*` styles, same behavior where nothing needed to change.
- **Not yet on the site.** Pasting it into Squarespace is a separate, approved step.

## What changed for visitors

| Area | Before | Now |
|---|---|---|
| Hero line | "…state legislatures across all 50 states, refreshed twice daily." | "…the U.S. Congress and state legislatures across all 50 states." The refresh claim is removed until the scheduled federal refresh has been tested (plan Step 6, item 14). |
| Jurisdiction | none (state only) | **Jurisdiction** chips: All · Federal · State |
| State selector | always shown | Shown for All and State, hidden for Federal. Choosing a state while Federal is selected switches to State. A chosen state shows only that state's bills. |
| Row label | state code (e.g. **NJ**) | state code, or **Federal** for congressional bills, above the bill number |
| Status chips | All · Active · Enacted · Inactive | unchanged. Federal statuses map the same way: enacted → Enacted, vetoed → Inactive, everything else → Active. The row pill shows the specific status, e.g. "Reported by committee". |
| Category chips | from the state feed, counts over all bills | Combined from both feeds in feed order. Counts reflect the selected jurisdiction. |
| Search | state, bill number, title, latest action | Also **official summary**, **sponsor**, and bill numbers typed without punctuation: `HR 9340`, `hr9340` and `H.R. 9340` all match. |
| Expanded row | latest action, session, legislature link | Adds jurisdiction, then sponsor, committee, introduced, passed House, passed Senate, signed into law (with law number) and effective date, **each only when the record has it**. Federal bills show the official CRS summary (labeled with its version, trimmed to about 900 characters) and a **View on Congress.gov** link. |
| Update line | one "Updated …" | **State data updated …** and **Federal data updated …**, each with its own status dot. Federal uses `sync.last_success_at`. |
| Credit line | state attribution + "Not legal advice." | both attributions + "Not legal advice." |

## Loading, empty and error states

- Each feed loads on its own. Whichever arrives first is shown right away, and the other merges in when it arrives.
- **One feed down:** its update line turns orange ("Federal legislation is temporarily unavailable."), a notice says "…showing state bills only," and the other feed's bills stay fully usable. If the visitor picks the jurisdiction that's down, the empty state names the outage instead of saying no bills match.
- **Both down:** both lines are orange, and the empty state reads "Legislation data is temporarily unavailable."
- **No matches:** unchanged ("No recent activity matches these filters." + Clear filters). Clear filters also resets Jurisdiction.

## Order

- Bills are grouped by category in the feed's order, newest action first within each group.
- With State selected, the order is exactly as before.
- With All selected, federal bills appear inside each category group, ordered by date with the state bills.

## Accessibility and layout

- **Chip rows** are labeled groups (`role="group"`, `aria-labelledby`), and each chip reports `aria-pressed`.
- **Focus:** after a click or keypress, focus stays on the chip or row the visitor used.
- **Focus rings:** buttons, the select, and the link show a visible `:focus-visible` outline.
- **Rows:** keep `aria-expanded`. The +/− icon and the decorative table header are hidden from screen readers.
- **Live updates:** the update lines and the result count are `aria-live="polite"`.
- **Mobile:** the existing breakpoint (819px) is unchanged, with rows stacking into cards. The detail grid's first cell now spans the full row, so it can't create an extra column on narrow screens.

## Intentional decisions

- **No local-government or regulatory filters**, per the plan.
- **Feed URLs are attributes** on the tracker element (`data-state-feed`, `data-federal-feed`), so the page can be tested against local copies. The defaults are the GitHub Pages URLs.
- **Launch order matters:**
  - The live state `bills.json` on `main` still uses the earlier category names. The branch version uses the new eight.
  - The embed shows the categories from both feeds, so a mismatch can't hide records. But until the branch is merged, the chip row would list both sets of names.
  - So **merge first (both feeds on the new taxonomy), then paste the embed.**
  - Pasted before the merge, the federal feed doesn't exist yet. The tracker would show state bills with "Federal legislation is temporarily unavailable."

## How it was tested

Local harness, Chrome, served from 127.0.0.1, using real feed files:
- **Regression cases from `docs/tracker-baseline.md`, State selected:** `HB 6486` → 1, `solar` → 4, `recycl` → 2, NJ → 11, NJ + Enacted → 0 with the empty state shown. All the same as the baseline.
- **Federal:** 45 bills, and the state selector hides. `S 5653`, `s5653`, `HR 9340`, `Capito` (sponsor) and `permitting` (summary only) each find exactly one bill. Choosing CA under All shows 10 state bills and 0 federal.
- **Detail panels:** H.R. 9340 shows sponsor, committee, introduced and passed-House dates, and a Congress.gov link. State HB 6486 shows only the fields it has.
- **Outages:** federal-down, state-down and both-down pages behave as described above.
- **Branch feeds (run 5) together:** 97 bills, the 8 new categories only, and Enacted shows 4 federal laws. S. 240's panel shows passed House, passed Senate, and signed with its law number.
- **Phone width (390px):** rows stack, nothing scrolls sideways, and the summary wraps.
- **CRS summaries:** list items arrive as separate lines, so lines that end mid-sentence are rejoined.
