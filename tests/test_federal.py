"""Tests for fetch_federal.py. No network: a fake session serves fixtures.

Fixtures in tests/fixtures/congress/ are real Congress.gov responses saved
2026-11-13 (S. 5653 detail/actions/summaries/committees, a bill list page, a
law list page). Action lists built inline below are synthetic and labeled.
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import date
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import fetch_federal as ff  # noqa: E402

CG = os.path.join(HERE, "fixtures", "congress")
TODAY = date(2026, 11, 13)


def load(name):
    with open(os.path.join(CG, name), encoding="utf-8") as f:
        return json.load(f)


def s5653_entry():
    return {"detail": load("s5653_detail.json")["bill"],
            "actions": load("s5653_actions.json")["actions"],
            "summaries": load("s5653_summaries.json")["summaries"],
            "committees": load("s5653_committees.json")["committees"],
            "hydrated": True, "candidate": True, "seen_at": "2026-11-13T12:00:00+00:00"}


class FakeResponse:
    def __init__(self, status, payload=None, headers=None):
        self.status_code, self._p, self.headers = status, payload, headers or {}

    def json(self):
        return self._p

    def raise_for_status(self):
        if self.status_code >= 400:
            err = ff.requests.HTTPError(f"{self.status_code}")
            err.response = self
            raise err


class FakeSession:
    """Routes /bill/... paths to fixture payloads. `routes` maps path -> payload
    or a list of responses served in order."""

    def __init__(self, routes):
        self.routes, self.headers, self.requested = routes, {}, []

    def get(self, url, params=None, timeout=None):
        path = url.replace(ff.API, "")
        self.requested.append((path, dict(params or {})))
        r = self.routes.get(path)
        if r is None:
            return FakeResponse(404, {})
        if isinstance(r, list):
            r = r.pop(0) if len(r) > 1 else r[0]
        return r if isinstance(r, FakeResponse) else FakeResponse(200, r)

    def close(self):
        pass


def list_page(rows):
    return {"bills": rows, "pagination": {"count": len(rows)}}


def s5653_routes(extra_list_rows=()):
    row = {"congress": 119, "type": "S", "number": "5653",
           "title": "Bipartisan American Affordability and Jobs Act of 2026",
           "latestAction": {"actionDate": "2026-09-30", "text": "Read twice and referred..."},
           "updateDate": "2026-11-12", "updateDateIncludingText": "2026-11-12T15:27:22Z"}
    empty = list_page([])
    return {
        "/bill/119/hr": empty, "/bill/119/hjres": empty, "/bill/119/sjres": empty,
        "/bill/119/s": list_page([row, *extra_list_rows]),
        "/bill/119/s/5653": load("s5653_detail.json"),
        "/bill/119/s/5653/actions": load("s5653_actions.json"),
        "/bill/119/s/5653/summaries": load("s5653_summaries.json"),
        "/bill/119/s/5653/committees": load("s5653_committees.json"),
    }


class Helpers(unittest.TestCase):
    def test_identifiers_and_urls(self):
        self.assertEqual(ff.canonical_id(119, "S", "5653"), "us-congress-119-s-5653")
        self.assertEqual(ff.canonical_id(119, "HJRES", 12), "us-congress-119-hjres-12")
        self.assertEqual(ff.official_url(119, "HR", "1"),
                         "https://www.congress.gov/bill/119th-congress/house-bill/1")
        self.assertEqual(ff.official_url(111, "SJRES", "2"),
                         "https://www.congress.gov/bill/111th-congress/senate-joint-resolution/2")

    def test_federal_ids_cannot_collide_with_state_uuids(self):
        state_ids = {b["id"] for b in json.load(open(os.path.join(
            HERE, "fixtures", "baseline_bills_2026-11-13.json")))["bills"]}
        self.assertFalse(any(i.startswith("us-congress-") for i in state_ids))

    def test_current_congress(self):
        self.assertEqual(ff.current_congress(date(2026, 11, 13)), 119)
        self.assertEqual(ff.current_congress(date(2027, 1, 2)), 119)
        self.assertEqual(ff.current_congress(date(2027, 1, 3)), 120)

    def test_strip_html(self):
        self.assertEqual(ff.strip_html("<p><strong>A</strong></p><ul><li>b&nbsp;c</li></ul>"), "A\nb c")


class Status(unittest.TestCase):
    """Synthetic action lists (not real bills) for each normalized status."""

    def st(self, actions, **detail):
        return ff.normalize_status(detail, actions)

    def test_introduced_and_committee(self):
        self.assertEqual(self.st([{"actionDate": "2026-01-02", "text": "Introduced in House"}],
                                 introducedDate="2026-01-02")[0], "introduced")
        self.assertEqual(self.st([{"actionDate": "2026-01-02",
                                   "text": "Referred to the House Committee on Energy and Commerce."}])[0],
                         "in_committee")

    def test_reported(self):
        self.assertEqual(self.st([
            {"actionDate": "2026-01-02", "text": "Referred to the Committee on Energy and Natural Resources."},
            {"actionDate": "2026-03-02", "text": "Committee on Energy and Natural Resources. Reported by Senator X with an amendment."},
        ])[0], "reported")

    def test_passed_one_and_both(self):
        one = [{"actionDate": "2026-02-01", "text": "Passed/agreed to in House: On passage Passed by recorded vote: 300 - 120."}]
        status, dates = self.st(one)
        self.assertEqual((status, dates["passed_house_date"], dates["passed_senate_date"]),
                         ("passed_one_chamber", "2026-02-01", None))
        both = one + [{"actionDate": "2026-04-01", "text": "Passed/agreed to in Senate: Passed Senate without amendment by Voice Vote."}]
        status, dates = self.st(both)
        self.assertEqual((status, dates["passed_senate_date"]), ("passed_both", "2026-04-01"))

    def test_enacted_from_action_or_laws(self):
        acts = [{"actionDate": "2026-11-10", "type": "BecameLaw", "text": "Became Public Law No: 119-142."}]
        status, dates = self.st(acts)
        self.assertEqual((status, dates["enacted_date"]), ("enacted", "2026-11-10"))
        self.assertEqual(self.st([], laws=[{"number": "119-142", "type": "Public Law"}])[0], "enacted")

    def test_veto_then_override_is_enacted(self):
        acts = [{"actionDate": "2026-05-01", "type": "Veto", "text": "Vetoed by President."}]
        self.assertEqual(self.st(acts)[0], "vetoed")
        acts.append({"actionDate": "2026-06-01", "type": "BecameLaw",
                     "text": "Became Public Law No: 119-50."})
        self.assertEqual(self.st(acts)[0], "enacted")

    def test_no_failure_inferred_and_no_effective_date(self):
        status, dates = self.st([], )
        self.assertEqual(status, "other")
        self.assertNotIn("effective_date", dates)


class Shape(unittest.TestCase):
    def test_s5653_matches_official_record(self):
        item = ff.shape(s5653_entry(), TODAY, "2026-11-13T12:00:00+00:00")
        expect = {
            "id": "us-congress-119-s-5653", "jurisdiction": "federal", "state": None,
            "congress": 119, "bill_type": "S", "bill_number": "5653", "bill": "S. 5653",
            "session": "119th Congress", "origin_chamber": "Senate",
            "title": "Bipartisan American Affordability and Jobs Act of 2026",
            "sponsor": "Sen. Capito, Shelley Moore [R-WV]", "cosponsors_count": 3,
            "policy_area": "Environmental Protection",
            "committees": ["Energy and Natural Resources Committee"],
            "status": "in_committee", "status_label": "In committee",
            "latest_action": "Read twice and referred to the Committee on Energy and Natural Resources.",
            "latest_action_date": "2026-09-30", "introduced": "2026-09-30",
            "enacted_date": None, "effective_date": None, "law_number": None,
            "url": "https://www.congress.gov/bill/119th-congress/senate-bill/5653",
            "source_updated_at": "2026-11-12T15:27:22Z",
            "last_verified_at": "2026-11-13T12:00:00+00:00",
            "actions_total": 2,
        }
        for k, v in expect.items():
            with self.subTest(field=k):
                self.assertEqual(item[k], v)
        self.assertTrue(item["summary"].startswith("Bipartisan American Affordability and Jobs Act of 2026"))
        self.assertNotIn("<", item["summary"])
        self.assertEqual(item["summary_version"], "Introduced in Senate (2026-09-30)")
        self.assertEqual([a["date"] for a in item["actions"]], ["2026-09-30", "2026-09-30"])

    def test_s5653_classified_from_summary_not_title(self):
        # The title alone matches nothing; the official summary drives the tags.
        self.assertEqual(ff.classify("Bipartisan American Affordability and Jobs Act of 2026", None), [])
        item = ff.shape(s5653_entry(), TODAY, None)
        self.assertTrue(item["categories"], "BAAJA should be categorized from its summary")
        self.assertEqual(item["classification"], "auto-title-summary")

    def test_summary_needs_two_hits(self):
        self.assertEqual(ff.classify("An Act", "This bill mentions recycling once."), [])
        self.assertEqual(ff.classify("An Act", "Recycling and composting and landfill rules."),
                         ["materials-circularity"])

    def test_first_live_run_false_positives(self):
        # Titles from the first live run (2026-11-14) that were wrongly tagged.
        for title in ["Public Archives Resiliency Act",
                      "Health Care Cybersecurity and Resiliency Act of 2026",
                      "Critical Infrastructure Manufacturing Feasibility Act",
                      "Nuclear REFUEL (Recycling Efficient Fuels Utilizing Expedited Licensing) Act"]:
            with self.subTest(title=title):
                self.assertEqual(ff.classify(title, None), [])
        # ...while real resilience bills still match.
        for title in ["Disaster Recovery and Resilience Act of 2026", "Promoting Resilient Buildings Act",
                      "Climate resiliency: research farms: grant program.",
                      "To establish a Floodplains and Watershed Resilience Program"]:
            with self.subTest(title=title):
                self.assertIn("infrastructure-resilience", ff.classify(title, None))

    def test_second_live_run_missed_titles(self):
        # Real environmental bills held as needs-review in the second live run
        # (2026-11-14) that the federal-oriented patterns now place.
        cases = {"Water Resources Development Act of 2026": "water-resources",
                 "A bill to amend the Federal Water Pollution Control Act to provide grants": "water-resources",
                 "Desalination Reauthorization Act": "water-resources",
                 "Regional Great Lakes Partnership Act of 2026": "water-resources",
                 "Improving Species Recovery Act": "nature-biodiversity",
                 "SAFE for Manatees Act": "nature-biodiversity",
                 "Tropospheric Ozone Research Act of 2026": "climate-emissions",
                 "New Source Review Permitting Improvement Act": "climate-emissions",
                 "Monitor Microplastics Now Act": "materials-circularity",
                 # toxics -> Materials & Circularity (decision 2026-11-14)
                 "Paraquat Prevention Act": "materials-circularity",
                 "Alan Reinstein Ban Asbestos Now Act of 2026": "materials-circularity",
                 "Safer Choice Program Authorization Act of 2026": "materials-circularity",
                 "Banning Toxics from Plastic Bottles Act of 2026": "materials-circularity"}
        for title, slug in cases.items():
            with self.subTest(title=title):
                self.assertIn(slug, ff.classify(title, None))

    def test_missing_optional_fields(self):
        e = {"detail": {"congress": 119, "type": "HR", "number": "9", "title": "Solar Act"},
             "actions": [], "summaries": [], "committees": []}
        item = ff.shape(e, TODAY, None)
        self.assertEqual(item["url"], "https://www.congress.gov/bill/119th-congress/house-bill/9")
        self.assertIsNone(item["summary"])
        self.assertIsNone(item["sponsor"])
        self.assertEqual(item["categories"], ["infrastructure-resilience"])

    def test_non_congress_url_replaced(self):
        e = s5653_entry()
        e["detail"]["legislationUrl"] = "https://example.com/x"
        self.assertTrue(ff.shape(e, TODAY, None)["url"].startswith("https://www.congress.gov/"))


class Sync(unittest.TestCase):
    def run_main(self, routes, d, budget=None):
        out, cache = os.path.join(d, "federal.json"), os.path.join(d, "cache.json")
        sess = FakeSession(routes)
        patches = [mock.patch.object(ff, "OUTPUT", out), mock.patch.object(ff, "CACHE", cache),
                   mock.patch.object(ff, "API_KEY", "test-key"),
                   mock.patch.object(ff, "PAUSE_SECONDS", 0),
                   mock.patch.object(ff.time, "sleep", lambda s: None),
                   mock.patch.object(ff, "current_congress", lambda t: 119)]
        if budget is not None:
            patches.append(mock.patch.object(ff, "MAX_CALLS_PER_RUN", budget))
        for p in patches:
            p.start()
        try:
            rc = ff.main(session=sess)
        finally:
            for p in patches:
                p.stop()
        with open(out) as f:
            return rc, json.load(f), sess

    def test_end_to_end_and_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            rc, feed, sess = self.run_main(s5653_routes(), d)
            self.assertEqual(rc, 0)
            self.assertEqual([b["id"] for b in feed["bills"]], ["us-congress-119-s-5653"])
            self.assertEqual(feed["sync"]["status"], "ok")
            self.assertIsNotNone(feed["sync"]["last_success_at"])
            self.assertEqual(sess.headers["X-Api-Key"], "test-key")
            self.assertFalse(any("api_key" in p for _, p in sess.requested))
            first_calls = len(sess.requested)

            # Second run: unchanged updateDate -> no detail/hydrate calls, no duplicate.
            rc, feed2, sess2 = self.run_main(s5653_routes(), d)
            self.assertEqual(rc, 0)
            self.assertEqual([b["id"] for b in feed2["bills"]], ["us-congress-119-s-5653"])
            self.assertEqual(len(sess2.requested), 4)  # just the four list calls
            self.assertLess(len(sess2.requested), first_calls)
            self.assertIsNone(feed2["bills"][0]["change"])

    def test_source_update_refreshes_record(self):
        with tempfile.TemporaryDirectory() as d:
            self.run_main(s5653_routes(), d)
            routes = s5653_routes()
            routes["/bill/119/s"]["bills"][0]["updateDateIncludingText"] = "2026-11-14T10:00:00Z"
            detail = load("s5653_detail.json")
            detail["bill"]["updateDateIncludingText"] = "2026-11-14T10:00:00Z"
            detail["bill"]["latestAction"] = {"actionDate": "2026-11-13", "text": "Committee on Energy and Natural Resources. Hearings held."}
            routes["/bill/119/s/5653"] = detail
            rc, feed, sess = self.run_main(routes, d)
            b = feed["bills"][0]
            self.assertEqual((b["latest_action_date"], b["source_updated_at"], b["change"]),
                             ("2026-11-13", "2026-11-14T10:00:00Z", "moved"))
            self.assertIn("/bill/119/s/5653/actions", [p for p, _ in sess.requested])

    def test_api_failure_keeps_last_good_feed_and_records_error(self):
        with tempfile.TemporaryDirectory() as d:
            self.run_main(s5653_routes(), d)
            down = {k: FakeResponse(503, {}) for k in s5653_routes()}
            rc, feed, _ = self.run_main(down, d)
            self.assertEqual(rc, 1)
            self.assertEqual(feed["sync"]["status"], "error")
            self.assertEqual([b["id"] for b in feed["bills"]], ["us-congress-119-s-5653"])
            self.assertNotIn("test-key", json.dumps(feed))

    def test_missing_key_fails_without_touching_state_feed(self):
        with tempfile.TemporaryDirectory() as d:
            state = os.path.join(d, "bills.json")
            with open(state, "w") as f:
                f.write('{"bills": [{"id": "state"}]}')
            out = os.path.join(d, "federal.json")
            with mock.patch.object(ff, "OUTPUT", out), mock.patch.object(ff, "API_KEY", ""):
                self.assertEqual(ff.main(session=FakeSession({})), 1)
            with open(out) as f:
                self.assertEqual(json.load(f)["sync"]["last_error"], "CONGRESS_API_KEY is not set")
            with open(state) as f:
                self.assertEqual(json.load(f)["bills"], [{"id": "state"}])

    def test_resolutions_and_stale_bills_skipped(self):
        stale = {"congress": 119, "type": "S", "number": "1", "title": "Solar Act",
                 "latestAction": {"actionDate": "2025-01-01"}, "updateDate": "2026-11-12"}
        with tempfile.TemporaryDirectory() as d:
            rc, feed, sess = self.run_main(s5653_routes([stale]), d)
            paths = [p for p, _ in sess.requested]
            self.assertNotIn("/bill/119/s/1", paths)
            self.assertFalse(any(p.startswith("/bill/119/hres") or p.startswith("/bill/119/sres")
                                 for p in paths))

    def test_budget_exhaustion_is_partial_not_crash(self):
        with tempfile.TemporaryDirectory() as d:
            rc, feed, _ = self.run_main(s5653_routes(), d, budget=5)  # 4 lists + 1 detail
            self.assertEqual(rc, 1)  # nothing publishable yet
            self.assertEqual(feed["sync"]["status"], "error")
            rc, feed, _ = self.run_main(s5653_routes(), d)  # next run finishes from cache
            self.assertEqual((rc, feed["sync"]["status"], len(feed["bills"])), (0, "ok", 1))


if __name__ == "__main__":
    unittest.main()
