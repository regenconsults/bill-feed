# Category Taxonomy

Introduced 2026-11-13 (Step 3) and used for both state and federal bills. Defined in `CATEGORIES` in `fetch_bills.py`.

## The eight categories

The order below is the order of the filter chips. It's also the tie-break order.

| ID (stable) | Label | Covers |
|---|---|---|
| `building-energy` | Building & Energy | Building codes, energy codes, building efficiency, electrification, energy performance, distributed energy (rooftop and community solar, net metering), building-related energy standards |
| `climate-emissions` | Climate & Emissions | Greenhouse-gas targets, emissions accounting, carbon reduction, climate policy, decarbonization, air quality |
| `water-resources` | Water Resources | Water quality, drinking water, wastewater, stormwater, watershed management, water conservation, water infrastructure |
| `land-use` | Land Use & Development | Zoning, planning, density, housing and development policy, site development (brownfields), land-use regulation |
| `materials-circularity` | Materials & Circularity | Recycling, reuse, waste reduction, product stewardship, sustainable material sourcing, embodied carbon, circular economy, **toxics and chemical safety** (pesticides, asbestos, toxic substances; your decision, 2026-11-14) |
| `nature-biodiversity` | Nature & Biodiversity | Habitat, biodiversity, forestry, land conservation, ecosystems, public lands, ecological restoration |
| `environmental-justice` | Environmental Justice | Environmental health, disproportionate pollution burdens, cumulative impacts, community impacts, equitable access |
| `infrastructure-resilience` | Infrastructure & Resilience | Transportation, public infrastructure, utilities and the grid, **utility-scale clean energy and transmission** (your decision, 2026-11-13), climate adaptation, disaster and flood resilience |

## How records store categories

All of these fields are additive. The live embed keeps working without changes.

- `category`: primary ID, used to choose which bills make the feed (up to 6 per primary category, 12 for Infrastructure & Resilience).
- `category_name`: primary label.
- `categories`: every matching ID, primary first. **This is new.**
- `topics`: every matching label, primary first. The site filters and counts on this field, so a bill shows under each of its categories.
- `classification`: `"auto-title"`. This marks the tags as an editorial suggestion, not a legislative fact. **This is new.**
- Feed-level `categories[].count` is the number of feed bills *tagged* with that category. One bill can count in several.

## Mapping from the previous categories

The old categories used the same structure, just different IDs. Mapping applied to the 45 baseline bills:

| Previous (v2) | → New primary | Bills |
|---|---|---|
| `buildings` Green & Healthy Buildings | `building-energy` | 6 |
| `clean-energy` Clean Energy | `infrastructure-resilience` 4 · `building-energy` 1 (community solar) · `land-use` 1 (MI farmland/solar) | 6 |
| `grid` Grid & Energy Affordability | `infrastructure-resilience` 5 · `land-use` 1 (PA data-center bill with municipal zoning, also tagged Infrastructure) | 6 |
| `transportation` Clean Transportation | `infrastructure-resilience` | 6 |
| `climate` Climate & Emissions | `climate-emissions` | 6 |
| `waste` Waste & Circular Economy | `materials-circularity` | 6 |
| `water-land` Water & Land | `water-resources` 3 · `nature-biodiversity` 2 · **dropped 1** | 6 |
| `equity` Environmental Equity | `environmental-justice` | 3 |

Every bill's tags are listed in `tests/fixtures/taxonomy_expected_2026-11-13.json`, alongside its old category, and a test enforces them.

- **Dropped on purpose:** PA HR 652, a study of pay for game wardens and waterways conservation officers. It only matched "conservation", and it was a false positive under the old taxonomy too.
- **Bills you reviewed on 2026-10-07** stay categorized:
  - CA AB 2667 → Materials & Circularity
  - NJ AR 154 → Infrastructure & Resilience
  - NJ S 4684 → Climate & Emissions

## Classification rules

1. Only the **title** is matched for state bills, because Bill Commons provides no summary. Federal bills (Step 4) will also have the official summary and Congress.gov policy area. See `docs/federal-data-integration.md`.
2. These titles are left out of every category:
   - Titles matching `GLOBAL_EXCLUDE`: communications, license plates, financial statements, routine reports, transit funding agreements.
   - Agency names (e.g. "Department of Environmental Conservation") are removed before matching, so a bill doesn't qualify just because it names one.
3. Each category has its own `exclude` list, and pattern groups can carry their own excludes:
   - Transit-worker, labor and police bills are excluded from the transportation patterns only, not from the grid or energy patterns that now share the category.
   - Conservation-officer and game-warden bills are excluded from Nature.
4. Context-sensitive cases are handled in the patterns, not with bare keywords:
   - "energy conservation" → Building & Energy
   - "water conservation" → Water Resources
   - other "conservation" → Nature & Biodiversity
   - "community / rooftop / residential solar" → Building & Energy
   - "solar" in general → Infrastructure & Resilience
   - `EV` matches only in capitals
   - "zero-emission" (vehicles, buses) counts only toward Infrastructure, not Climate
   - "community land trust" (a housing tool) → Land Use; other "land trust" → Nature
5. A bill gets **every** category it matches. Its primary category is the one with the most distinct pattern matches; ties go to the category listed first.

## Fallback: uncategorized bills

A bill that comes back from a search but matches no category is **not published**. There's no public ninth category. Each run logs the counts as "N recent bills, M categorized", and the gap between the two is the uncategorized set.

There's no confidence score or manual-review queue. The current architecture is a static JSON file with no admin interface. Corrections are made by editing patterns or excludes and adding a test case, the same way PA HR 652 was handled.

## Known edge cases needing review

- **PA HB 2888**: hyperscale data centers. Primary is Land Use (municipal zoning), and it's also tagged Infrastructure (ratepayer).
- **MA SD 4278**: "Pioneer Valley Transit Authority FY26 Annual Report". This is an existing behavior that Step 3 didn't change: the routine-report exclude only matches titles that *start* with "report". It's a candidate for a future exclude, but that needs your approval because it would remove a bill.

## Live dry run (2026-11-13)

This was a full Bill Commons run of the branch code. It wrote only to a scratch file; the published feed was not touched.

- **Run:** 106 API calls with 0 errors. 4 rate-limit (429) waits were retried successfully.
- **Bills:** 1,241 recent bills found, 538 categorized, **46 in the feed**, from 11 states. No duplicate IDs and no bad URLs.
- **Multi-category:** 10 of the 46 carry more than one tag.
- **Tag counts:** Building & Energy 7 · Climate & Emissions 6 · Water Resources 6 · Land Use & Development 7 · Materials & Circularity 6 · Nature & Biodiversity 7 · Environmental Justice 4 · Infrastructure & Resilience 15.

These problems came out of the run and are fixed and tested:
- CA AB 1944 (zero-emission transit buses) was going to Climate.
- CA AB 672 (community land trusts) was going to Nature.

**Coverage note:** Infrastructure & Resilience absorbs three former categories (Clean Energy, Grid, Clean Transportation) plus resilience, so it gets **12 feed slots** (approved 2026-11-13); every other category keeps 6.
