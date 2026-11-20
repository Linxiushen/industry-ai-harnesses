import json
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from industry_agent import runtime
from industry_agent.runtime import run_agent


class AgentGraphTests(unittest.TestCase):
    def test_adaptive_triage_has_evidence_and_only_fits_domain_once(self):
        with patch.object(runtime.manufacturing, "run", wraps=runtime.manufacturing.run) as evaluate:
            report = run_agent("制造设备故障交接")
        self.assertEqual(evaluate.call_count, 1)
        self.assertEqual(report["status"], "needs_review")
        ranking, queue, orders = report["tools"]
        self.assertEqual([ranking["id"], queue["id"], orders["id"]],
                         ["condition-monitoring", "inspection-queue", "work-order-evidence"])
        self.assertEqual([row["sequence"] for row in orders["output"]["draft_cases"]],
                         [seq for batch in queue["output"]["batches"] for seq in batch])
        self.assertEqual([s.get("follow_up") for s in report["steps"] if s["kind"] == "observe"],
                         [queue["id"], orders["id"], None])
        self.assertEqual(report["steps"][-1]["kind"], "review")
        json.dumps(report, allow_nan=False)

    def test_budget_closes_graph_before_authorizing_another_tool(self):
        report = run_agent("Triage manufacturing failures", max_tools=1)
        self.assertEqual(report["status"], "budget_exhausted")
        self.assertEqual([s["kind"] for s in report["steps"]], ["plan", "tool", "observe", "budget"])
        self.assertEqual(report["steps"][2]["follow_up"], "inspection-queue")
        self.assertIn("inspection-queue", report["review"][-1])

    def test_retrieve_different_conditions_and_abstain_on_no_evidence(self):
        for request, expected in [("检索慢阻肺临床试验", "NCT00440687"),
                                  ("Find historical NSCLC trials", "NCT00188279")]:
            with self.subTest(request=request):
                report = run_agent(request)
                self.assertEqual(report["status"], "completed")
                hits = report["tools"][0]["output"]["hits"]
                self.assertEqual(hits[0]["id"], expected)
                self.assertIn(expected, hits[0]["url"])
                self.assertEqual(report["data"]["kind"], "historical_registry_metadata")
        empty = run_agent("Find migraine trials")
        self.assertEqual(empty["status"], "needs_review")
        self.assertEqual(empty["tools"][0]["output"]["hits"], [])

    def test_country_filter_and_condition_operate_on_registry_cohort(self):
        report = run_agent("在加拿大筛选糖尿病临床试验招募站点")
        tool, = report["tools"]
        self.assertEqual(report["data"]["kind"], "synthetic")
        self.assertEqual(tool["output"]["condition_filter"], "diabetes")
        self.assertEqual([(r["study"], r["city"]) for r in tool["output"]["shortlist"]], [("SIM-02", "Toronto")])
        self.assertEqual(run_agent("Find recruiting sites in Australia")["tools"][0]["output"]["shortlist"], [])

    def test_ambiguous_and_unknown_requests_do_not_execute_tools(self):
        for request in ["Forecast share prices", "compare electricity and manufacturing risks", "Find clinical trials"]:
            with self.subTest(request=request):
                report = run_agent(request)
                self.assertEqual(report["status"], "needs_clarification")
                self.assertEqual(report["tools"], [])

    def test_malformed_external_plans_never_dispatch(self):
        proposals = [
            {"domain": "pharma", "tools": ["exec"]},
            {"domain": "energy", "tools": ["registry_follow_up"]},
            {"domain": "pharma", "tools": ["registry_follow_up", "registry_follow_up"]},
            {"domain": "pharma", "tools": ["registry_follow_up"], "country": "US"},
            {"domain": "pharma", "tools": ["trial_landscape"], "query": 4},
            {"domain": "pharma", "tools": [], "url": "unregistered"},
            {"domain": "energy", "tools": ["day-ahead-load"]},
        ]
        for proposal in proposals:
            with self.subTest(proposal=proposal):
                report = run_agent("Clinical research", domain="pharma", planner=lambda *_: proposal)
                self.assertEqual(report["status"], "error")
                self.assertEqual(report["tools"], [])
                self.assertNotIn("tool", [step["kind"] for step in report["steps"]])
        def fails(*args):
            raise ValueError("credentials in backend diagnostic")
        report = run_agent("Clinical research", planner=fails)
        self.assertNotIn("credentials", json.dumps(report))
        self.assertEqual(report["status"], "error")

    def test_valid_external_plan_obeys_parameters_and_catalog(self):
        def planner(request, catalog):
            self.assertEqual({c["domain"] for c in catalog}, {"pharma"})
            return {"domain": "pharma", "tools": ["trial_landscape", "recruiting_locations"],
                    "query": "COPD", "country": "Canada"}
        report = run_agent("Explore this clinical operations brief", domain="pharma", planner=planner)
        self.assertEqual(report["status"], "needs_review")
        self.assertEqual(report["data"]["kind"], "mixed")
        search, sites = report["tools"]
        self.assertEqual(search["output"]["hits"][0]["id"], "NCT00440687")
        self.assertEqual(sites["output"]["condition_filter"], "COPD")
        self.assertEqual(sites["output"]["shortlist"], [])

    def test_energy_metrics_survive_execution_and_missing_files_are_explicit(self):
        report = run_agent("Assess peak hour alerts for electricity", max_tools=1)
        self.assertEqual([tool["id"] for tool in report["tools"]], ["peak-hour-alerts"])
        metrics = report["tools"][0]["metrics"]
        self.assertEqual(metrics["event_hours"], metrics["missed_hours"] + metrics["true_positives"])
        self.assertEqual(report["data"]["test_days"], 14)
        with TemporaryDirectory() as empty:
            failed = run_agent("Forecast electricity load", data_dir=empty)
        self.assertEqual(failed["status"], "error")
        self.assertEqual(failed["tools"], [])
        self.assertEqual(failed["steps"][-1]["kind"], "error")


if __name__ == "__main__":
    unittest.main()
