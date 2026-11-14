"""Regression tests for the existing state pipeline (fetch_bills.py).

Stdlib unittest only, no network. Run from the repo root:
    python3 -m unittest discover -s tests -v
"""

import copy
import json
import os
import sys
import tempfile
import unittest
from datetime import date
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import fetch_bills as fb  # noqa: E402

FIX = os.path.join(HERE, "fixtures")
TODAY = date(2026, 11, 13)


def load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


def api_row(**over):
    row = load("billcommons_row_mi_hb6486.json")
    row.update(over)
    return row


class BaselineCategorization(unittest.TestCase):
    """Every 2026-11-13 baseline bill gets its reviewed eight-category tags."""

    def test_baseline_titles_get_reviewed_tags(self):
        bills = load("baseline_bills_2026-11-13.json")["bills"]
        expected = {(e["state"], e["bill"]): e["new"]
                    for e in load("taxonomy_expected_2026-11-13.json")["bills"]}
        self.assertEqual(len(bills), 45)
        for b in bills:
            with self.subTest(bill=f"{b['state']} {b['bill']}"):
                got = [s for s, _ in fb.score_categories(b["title"])]
                self.assertEqual(got, expected[(b["state"], b["bill"])])

    def test_only_reviewed_drop(self):
        dropped = [(e["state"], e["bill"]) for e in load("taxonomy_expected_2026-11-13.json")["bills"]
                   if not e["new"]]
        self.assertEqual(dropped, [("PA", "HR 652")])  # game-warden pay study

    def test_user_reviewed_bills(self):
        # Reviewed by the user 2026-10-07 and kept; must stay categorized.
        self.assertEqual(fb.categorize("Vape products: household hazardous waste: advertising."),
                         "materials-circularity")
        self.assertEqual(fb.categorize("Authorizes Assembly Telecommunications and Utilities Committee "
                                       "to enter upon investigation or inquiry into BPU's and DEP's efforts "
                                       "to comply with certain provisions of P.L.2007, c.340 requiring "
                                       "development of plan for ratepayer relief; grants committee subpoena power."),
                         "infrastructure-resilience")
        self.assertEqual(fb.categorize('Requires youth serving organization to adopt and implement '
                                       '"Air Quality Participation Policy" established by Commissioner of Health.'),
                         "climate-emissions")

    def test_eight_categories_stable_ids(self):
        self.assertEqual([c["slug"] for c in fb.CATEGORIES], [
            "building-energy", "climate-emissions", "water-resources", "land-use",
            "materials-circularity", "nature-biodiversity", "environmental-justice",
            "infrastructure-resilience"])
        self.assertEqual(len({c["name"] for c in fb.CATEGORIES}), 8)

    def test_contextual_rules(self):
        self.assertEqual(fb.categorize("Energy conservation code update"), "building-energy")
        self.assertEqual(fb.categorize("Water conservation programs"), "water-resources")
        self.assertEqual(fb.categorize("Land conservation easements"), "nature-biodiversity")
        self.assertEqual(fb.categorize("Utility-scale solar facility siting"), "infrastructure-resilience")
        self.assertEqual(fb.categorize("Community solar program"), "building-energy")
        # transit-worker bills stay out, but the same excludes don't block grid bills
        self.assertIsNone(fb.categorize("Transit authority employee collective bargaining"))
        self.assertEqual(fb.categorize("Electric grid modernization; labor standards"),
                         "infrastructure-resilience")

    def test_dry_run_fixes(self):
        self.assertEqual([x for x, _ in fb.score_categories("Zero-emission transit buses: axle weight.")],
                         ["infrastructure-resilience"])
        self.assertEqual(fb.categorize("Real property tax: welfare exemption: community land trusts."),
                         "land-use")
        self.assertEqual(fb.categorize("Reduces methane emissions from landfills"), "climate-emissions")

    def test_multi_category(self):
        got = [s for s, _ in fb.score_categories(
            "Climate resiliency: stormwater and floodplain management")]
        self.assertEqual(got[0], "infrastructure-resilience")
        self.assertIn("climate-emissions", got)
        self.assertIn("water-resources", got)

    def test_global_exclude(self):
        self.assertIsNone(fb.categorize("Approves reimbursable agreement with WMATA for solar canopy"))
        self.assertIsNone(fb.categorize("Communication from the Department regarding recycling"))

    def test_agency_names_do_not_count(self):
        self.assertIsNone(fb.categorize("Department of Environmental Conservation; appropriations"))
        self.assertEqual(fb.categorize("Requires DEC to regulate recycling facilities"), "materials-circularity")

    def test_tie_goes_to_first_listed(self):
        # "community solar" matches Building & Energy and "solar" Infrastructure; 1 each.
        self.assertEqual(fb.categorize("Community solar geographic restrictions"), "building-energy")

    def test_ev_pattern_is_case_sensitive(self):
        self.assertEqual(fb.categorize("Expands EV charging station grants"), "infrastructure-resilience")
        self.assertIsNone(fb.categorize("Relating to levies on event venues"))

    def test_none_and_empty(self):
        self.assertIsNone(fb.categorize(None))
        self.assertIsNone(fb.categorize(""))


class Shape(unittest.TestCase):
    def test_shape_matches_baseline_record(self):
        slugs = [s for s, _ in fb.score_categories(api_row()["title"])]
        self.assertEqual(slugs, ["land-use", "nature-biodiversity", "infrastructure-resilience"])
        out = fb.shape(api_row(), slugs, TODAY)
        self.assertEqual(out, {
            "id": "3b580269-dd96-4016-8f39-9b20622d6c73",
            "state": "MI",
            "bill": "HB 6486",
            "title": api_row()["title"],
            "session": "2025-2026 Regular Session (103rd Legislature)",
            "status": "in_committee",
            "status_label": "In committee",
            "latest_action": "bill electronically reproduced 11/12/2026",
            "latest_action_date": "2026-11-17",
            "upcoming": True,
            "introduced": None,
            "url": "https://legislature.mi.gov/Bills/Bill?ObjectName=2026-HB-6486",
            "category": "land-use",
            "category_name": "Land Use & Development",
            "categories": ["land-use", "nature-biodiversity", "infrastructure-resilience"],
            "topics": ["Land Use & Development", "Nature & Biodiversity", "Infrastructure & Resilience"],
            "classification": "auto-title",
        })

    def test_shape_accepts_single_slug(self):
        out = fb.shape(api_row(), "land-use", TODAY)
        self.assertEqual((out["categories"], out["topics"]), (["land-use"], ["Land Use & Development"]))

    def test_short_title_preferred(self):
        self.assertEqual(fb.shape(api_row(short_title="Solar Act"), "land-use", TODAY)["title"], "Solar Act")

    def test_status_labels(self):
        self.assertEqual(fb.status_label({"status": "enacted"}), "Enacted")
        self.assertEqual(fb.status_label({"status": "died_on_adjournment"}), "Died on adjournment")
        self.assertEqual(fb.status_label({"status": "some_new_value"}), "Some new value")
        self.assertEqual(fb.status_label({}), "In progress")

    def test_parse_date_tolerates_bad_input(self):
        self.assertIsNone(fb.parse_date(None))
        self.assertIsNone(fb.parse_date("not a date"))
        self.assertEqual(fb.parse_date("2026-11-17T00:00:00Z"), date(2026, 11, 17))


class Movement(unittest.TestCase):
    def setUp(self):
        self.item = fb.shape(api_row(), "land-use", TODAY)

    def test_new(self):
        out = fb.mark_movement(dict(self.item), {}, TODAY)
        self.assertEqual((out["change"], out["first_seen"]), ("new", "2026-11-13"))

    def test_moved(self):
        old = dict(self.item, status="introduced", status_label="Introduced",
                   first_seen="2026-10-01", changed_on="2026-10-01", change=None)
        out = fb.mark_movement(dict(self.item), {old["id"]: old}, TODAY)
        self.assertEqual(out["change"], "moved")
        self.assertEqual(out["previous_status_label"], "Introduced")
        self.assertEqual(out["first_seen"], "2026-10-01")

    def test_badge_persists_then_expires(self):
        old = dict(self.item, first_seen="2026-11-12", changed_on="2026-11-12", change="new")
        self.assertEqual(fb.mark_movement(dict(self.item), {old["id"]: old}, TODAY)["change"], "new")
        old["changed_on"] = "2026-11-01"
        self.assertIsNone(fb.mark_movement(dict(self.item), {old["id"]: old}, TODAY)["change"])


class PickAndBuild(unittest.TestCase):
    def test_pick_uses_primary_category_only(self):
        items = [{"id": "a", "state": "NJ", "category": "land-use",
                  "categories": ["land-use", "water-resources"], "latest_action_date": "2026-11-01"}]
        self.assertEqual([i["id"] for i in fb.pick(items, TODAY)], ["a"])  # not duplicated

    def _items(self, n, slug="climate-emissions", state="NJ"):
        return [{"id": f"{state}{i}", "state": state, "category": slug,
                 "latest_action_date": f"2026-11-{(i % 28) + 1:02d}"} for i in range(n)]

    def test_per_category_cap(self):
        self.assertEqual(len(fb.pick(self._items(10), TODAY)), fb.PER_CATEGORY)

    def test_infrastructure_gets_twelve_slots(self):
        items = []
        for st in ["NJ", "CA", "PA", "MI", "OH", "IL", "NY"]:
            items += self._items(3, slug="infrastructure-resilience", state=st)
        self.assertEqual(len(fb.pick(items, TODAY)), 12)

    def test_spread_across_states_when_possible(self):
        items = self._items(6, state="NJ") + self._items(3, state="CA") + self._items(3, state="PA")
        states = [i["state"] for i in fb.pick(items, TODAY)]
        self.assertEqual(sorted(states), ["CA", "CA", "NJ", "NJ", "PA", "PA"])

    def test_companion_bills_dedupe_and_first_run_has_no_badges(self):
        a = api_row(id="a", identifier="HB 1")
        b = api_row(id="b", identifier="SB 1")  # same state/session/title
        feed, matched = fb.build_feed({"a": a, "b": b}, {}, TODAY)
        self.assertEqual(len(matched), 1)
        self.assertTrue(all(i["change"] is None for i in feed))

    def test_uncategorized_dropped(self):
        feed, _ = fb.build_feed({"x": api_row(id="x", title="Relating to fishing licenses")}, {}, TODAY)
        self.assertEqual(feed, [])


class MainFailureSafety(unittest.TestCase):
    def test_empty_result_keeps_existing_feed(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "bills.json")
            with open(out, "w") as f:
                f.write('{"bills": [{"id": "keep"}]}')
            with mock.patch.object(fb, "OUTPUT", out), \
                 mock.patch.object(fb, "collect", return_value=({}, 5, 5)):
                rc = fb.main()
            self.assertEqual(rc, 1)
            with open(out) as f:
                self.assertEqual(json.load(f)["bills"], [{"id": "keep"}])

    def test_writes_feed_shape(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "bills.json")
            row = api_row(latest_action_date="2026-11-10")
            with mock.patch.object(fb, "OUTPUT", out), \
                 mock.patch.object(fb, "collect", return_value=({row["id"]: row}, 0, 1)):
                self.assertEqual(fb.main(), 0)
            with open(out) as f:
                feed = json.load(f)
            self.assertEqual(feed["version"], 2)
            self.assertEqual([c["slug"] for c in feed["categories"]], [c["slug"] for c in fb.CATEGORIES])
            self.assertEqual(feed["bills"][0]["bill"], "HB 6486")
            counts = {c["slug"]: c["count"] for c in feed["categories"]}
            # the one bill counts in each of its three tags
            self.assertEqual(sum(counts.values()), 3)
            self.assertEqual(counts["land-use"], 1)


if __name__ == "__main__":
    unittest.main()
