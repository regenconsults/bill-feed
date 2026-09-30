# Build script: add the Environmental Bill Tracker to the ReGen Consulting Squarespace site

**For Claude Code.** Read this whole file before doing anything. Work through the phases in order and stop at every **CHECKPOINT** to report to the user.

This folder contains:
- `fetch_bills.py`: fetches environment-related state bills from the Bill Commons API and writes `docs/bills.json`
- `.github/workflows/refresh-bills.yml`: runs the fetch twice a day (11:00 and 23:00 UTC) and commits the result
- `squarespace-code-block.html`: the embed that displays the feed on the site
- `BUILD_BILL_FEED.md`: this file

---

## Settings (the user may edit these before you start)

```
GITHUB_REPO_NAME = bill-feed
PAGE_PLACEMENT   = new-unlinked-page      # or: existing-page
NEW_PAGE_TITLE   = Legislation Tracker
NEW_PAGE_SLUG    = /legislation-tracker
EXISTING_PAGE    = (only if PAGE_PLACEMENT = existing-page, e.g. "Homeowners Guide")
SECTION_HEADING  = Environmental Legislation Tracker
SECTION_INTRO    = Environment-related bills moving through state legislatures across all 50 states, refreshed twice daily.
```

---

## Hard rules: these override everything else

1. **Do not publish.** The site must stay private or password-protected. Never change Site Visibility, and never click anything that makes the site public, including "Publish", "Go live", or "Upgrade to publish".
2. **Do not touch the domain or DNS.** Do not connect regenconsults.com, and do not change domain or DNS settings.
3. **Leave everything else as it is.** Do not edit, move, restyle, or delete any existing page, section, block, navigation item, header, footer, Site Styles setting, font, color, or Custom CSS/Code Injection. The only permitted change to the site is adding the new feed section or page described below.
4. **Read-only is fine.** You may open Site Styles to read the palette hex values. Do not save anything there.
5. **Do not enter credentials or payment details.** If Squarespace or GitHub asks for a login, a password, a plan upgrade, or payment, stop and ask the user.
6. **Stop and ask** if anything is ambiguous, if a step would change something outside the new feed, or if the UI doesn't match these instructions.

---

## Phase 1: Host the feed on GitHub

1. Confirm `git` and the GitHub CLI (`gh`) are installed and that `gh auth status` shows the user is logged in. If not, stop and ask the user to log in. Do not handle their credentials yourself.
2. Initialize this folder as a git repo and create a **public** repository named `GITHUB_REPO_NAME` under the user's account with `gh repo create`. Free GitHub Pages requires a public repo. Before creating it, confirm with the user that a public repo is OK.
3. Create `docs/.nojekyll` (empty file) and a placeholder `docs/bills.json` containing `{"bills": []}`. Commit all files and push to `main`.
4. Enable GitHub Pages from the `main` branch, `/docs` folder:
   `gh api -X POST repos/{owner}/{repo}/pages -f "source[branch]=main" -f "source[path]=/docs"`
5. Check that Actions has write permission: Settings → Actions → General → Workflow permissions. The workflow already declares `contents: write`. If the push step fails, ask the user to enable "Read and write permissions".
6. Trigger the first run: `gh workflow run refresh-bills.yml`, then `gh run watch`.
7. After it finishes, `git pull` and check `docs/bills.json`:
   - `generated_at` is present and `bills` has entries
   - each bill has `state`, `bill`, `title`, `status_label`, `latest_action`, `latest_action_date`, `url`
8. Wait for Pages to deploy (1–3 minutes), then confirm the feed is reachable:
   `curl -sI https://<owner>.github.io/<repo>/bills.json` should return `200` with `access-control-allow-origin: *`.

**CHECKPOINT 1:** Report the live feed URL, the number of bills, and 3 sample bills (state, number, title, status). Ask the user to confirm before continuing.

---

## Phase 2: Prepare the embed

1. In `squarespace-code-block.html`, set `FEED_URL` to the Pages URL from Phase 1.
2. **Match the brand without changing the site.** Using Claude in Chrome, open the Squarespace editor → Site Styles → Colors (the Daytime palette) and **read** the hex values. Close without saving. Then set the `--bf-*` variables in the embed's `<style>`:
   - `--bf-ink`: the palette's darkest text color
   - `--bf-muted`: a secondary or lighter text color
   - `--bf-line`: a light neutral for borders
   - `--bf-card`: the lightest background (usually white)
   - `--bf-accent` and `--bf-new`: the primary brand accent
   - `--bf-moved`: a second, contrasting palette accent
   Do not add fonts; the embed inherits All Round Gothic from the site.
3. Commit the updated embed file to the repo. The site does not load it from there; this is only for record-keeping.

---

## Phase 3: Add the feed in Squarespace (Claude in Chrome)

Run `/chrome` if Chrome isn't connected yet. Work in a new tab.

1. **Safety check first.** In Settings → Site Availability (or Site Visibility), confirm the site is **Private** or **Password Protected**. Read this setting only. If the site is Public, **stop immediately** and tell the user. Saving edits on a public site makes them live.
2. **Placement:**
   - If `PAGE_PLACEMENT = new-unlinked-page`: in Pages, add a new blank page in the **Not Linked** section (not the main navigation) titled `NEW_PAGE_TITLE`, with the URL slug `NEW_PAGE_SLUG`. Do not change the navigation.
   - If `PAGE_PLACEMENT = existing-page`: open `EXISTING_PAGE` and add **one new section at the very bottom**, above the footer. Do not change any existing section on that page.
3. In that section, add:
   - a **Text block** with `SECTION_HEADING` as a Heading 2, followed by `SECTION_INTRO` as normal paragraph text. Use the site's existing heading and paragraph styles; do not change fonts, sizes, or colors.
   - a **Code block** below it: set mode to HTML, turn "Display Source" **off**, and paste the full contents of `squarespace-code-block.html`.
   - Use the site's default section styling; do not adjust section colors or backgrounds.
4. If Squarespace says code blocks or JavaScript require a different plan, **stop** and tell the user. Do not upgrade.
5. Click **Save** in the page editor. This saves to the private site; it does not publish.

---

## Phase 4: Verify

1. Exit the editor and view the page. Code-block scripts often don't run inside the editor, so check the page itself. Confirm:
   - "Updated [date/time]" appears and bill cards render
   - status pills and latest actions show; titles link to official legislature pages and open in a new tab
   - the State filter lists multiple states and filtering works
   - the attribution line appears at the bottom
   - the layout works at phone width (use the editor's mobile preview or resize the window)
2. Check the browser console for errors related to the feed.
3. Spot-check that nothing else changed: the navigation, the header and footer, and the other pages look the same as before.
4. Confirm Site Visibility is still Private or Password Protected.

**CHECKPOINT 2 (final report):** Give the user:
- the feed URL and the GitHub repo URL
- where the tracker lives on the site (page name and URL slug)
- a screenshot of the rendered feed (desktop and mobile)
- confirmation that the site is still private, that nothing was published, that no domain or DNS settings changed, and that no other page or setting was modified
- any issues, and anything you skipped because it needed their approval

---

## Ongoing notes for the user

- The feed refreshes at about 7am and 7pm Eastern. For an immediate refresh, open the repo's Actions tab → "Refresh environmental bill feed" → **Run workflow**.
- To change search terms, edit `KEYWORDS` near the top of `fetch_bills.py` and push the change. The site picks it up on the next refresh without any Squarespace edits.
- If the Bill Commons API is down, the previous feed stays in place instead of going blank.
