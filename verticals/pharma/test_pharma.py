import importlib.util
import unittest
from datetime import date
from pathlib import Path


def load(module):
    spec = importlib.util.spec_from_file_location(module, Path(__file__).with_name(module + ".py"))
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


h = load("harness")
fetch = load("fetch_registry")


class ClinicalOperationsTest(unittest.TestCase):
    def test_fictional_cohort_business_outputs(self):
        retrieval, site, triage = h.run()["scenarios"]
        self.assertEqual([(r["study"], r["city"]) for r in site["output"]["shortlist"]],
                         [("SIM-01", "Boston"), ("SIM-02", "Chicago")])
        self.assertEqual([r["study"] for r in triage["output"]["follow_up"]], ["SIM-10", "SIM-03"])
        self.assertEqual({r["study"] for r in site["output"]["manual_review"]}, {"SIM-04", "SIM-06"})
        self.assertEqual({r["study"] for r in triage["output"]["manual_review"]}, {"SIM-08", "SIM-12"})
        hits = {s["query"]: s["hits"] for s in retrieval["output"]}
        self.assertEqual(hits["migraine"], [])
        self.assertEqual(hits["COPD"][0]["id"], "NCT00440687")
        self.assertEqual(hits["NSCLC"][0]["phase"], ["Phase 2"])
        self.assertEqual(hits["COPD"][0]["url"], "https://clinicaltrials.gov/study/NCT00440687")
        sources = h.run()["data"]
        self.assertEqual(sources["kind"], "mixed")
        self.assertEqual(sources["source"]["trial_landscape"]["kind"], "historical_registry_metadata")
        self.assertEqual(sources["source"]["operations"]["kind"], "synthetic")

    def test_reporting_threshold_is_inclusive_and_posting_status_is_tristate(self):
        study = {"id": "X", "status": "COMPLETED", "completion_type": "ACTUAL",
                 "primary_completion": "2024-01-02", "has_results": False}
        rows = [study, {**study, "id": "Y", "has_results": None},
                {**study, "id": "Z", "primary_completion": "2024-01-03"},
                {**study, "id": "W", "primary_completion": "2025-04-25"}]
        result = h.follow_up(rows, date(2025, 1, 1))
        self.assertEqual(result["follow_up"][0]["days_since_primary_completion"], 365)
        self.assertEqual([r["study"] for r in result["follow_up"]], ["X"])
        self.assertEqual([r["study"] for r in result["manual_review"]], ["Y", "W"])

    def test_site_country_and_freshness(self):
        site = {"country": "United States", "status": "RECRUITING", "city": "Boston"}
        study = {"id": "X", "status": "RECRUITING", "updated": "2024-01-01", "sites": [site, site]}
        result = h.shortlist([study], date(2024, 6, 29))
        self.assertEqual(len(result["shortlist"]), 1)
        self.assertFalse(h.shortlist([study], date(2024, 6, 30))["shortlist"])
        self.assertFalse(h.shortlist([study], date(2024, 6, 29), "Canada")["shortlist"])

    def test_registry_projection_preserves_missing_flags_and_drops_contact_fields(self):
        record = {"protocolSection": {"identificationModule": {"nctId": "NCT00000001"},
                  "contactsLocationsModule": {"locations": [{"city": "Oslo", "facility": "F",
                  "country": "Norway", "contacts": [{"name": "Example"}]}]}}}
        view = fetch.project(record, "NCT00000001")
        self.assertIsNone(view["has_results"])
        self.assertEqual(view["sites"], [{"city": "Oslo", "country": "Norway", "status": None}])
        with self.assertRaises(ValueError):
            fetch.project(record, "NCT00000002")


if __name__ == "__main__":
    unittest.main()
