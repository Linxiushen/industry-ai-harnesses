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

    def test_inspection_capacity_sweep_uses_one_cohort_and_equal_ranked_workload(self):
        manufacturing = runtime.manufacturing
        rows = manufacturing.synthetic_rows()
        test = rows[len(rows) * 3 // 4:]
        batches = [test[start:start + manufacturing.BATCH]
                   for start in range(0, len(test), manufacturing.BATCH)]
        baseline = [sorted(batch, key=lambda row: (-row.wear, row.sequence)) for batch in batches]
        truth = {row.sequence for row in test if row.failed}
        original = run_agent("inspection-queue", domain="manufacturing", max_tools=1)
        prior_queues = [[] for _ in batches]
        for slots in range(1, manufacturing.MAX_INSPECTION_SLOTS + 1):
            with self.subTest(slots=slots):
                report = run_agent("inspection-queue", domain="manufacturing", max_tools=1,
                                   inspection_slots=slots)
                (queue,) = report["tools"]
                self.assertEqual(report["status"], "needs_review")
                self.assertEqual(report["data"]["sha256"], original["data"]["sha256"])
                self.assertEqual(report["data"]["inspection_capacity"], {
                    "slots_per_batch": slots, "default_slots_per_batch": manufacturing.CAPACITY,
                })
                self.assertEqual(report["steps"][0]["parameters"], {"inspection_slots": slots})
                self.assertEqual(queue["output"]["slots_per_batch"], slots)
                queues = queue["output"]["batches"]
                self.assertEqual(len(queues), len(batches))
                for previous, current, cohort in zip(prior_queues, queues, batches):
                    self.assertEqual(current[:len(previous)], previous)
                    self.assertEqual(len(current), min(slots, len(cohort)))
                    self.assertLessEqual(set(current), {row.sequence for row in cohort})
                prior_queues = queues
                selected = [sequence for current in queues for sequence in current]
                caught = len(truth.intersection(selected))
                expected_baseline = sum(row.failed for batch in baseline for row in batch[:slots])
                metrics = queue["metrics"]
                self.assertEqual(metrics["records_reviewed"], len(selected))
                self.assertEqual(metrics["failures_in_queue"], caught)
                self.assertEqual(metrics["false_alerts"], len(selected) - caught)
                self.assertEqual(metrics["failures_outside_queue"], len(truth) - caught)
                self.assertEqual(metrics["wear_only_failures_at_same_capacity"], expected_baseline)
                if slots == manufacturing.CAPACITY:
                    self.assertEqual(report["tools"], original["tools"])

    def test_inspection_capacity_follows_adaptive_budget_and_work_order(self):
        scenario = "制造设备故障交接"
        with patch.object(runtime.manufacturing, "run", wraps=runtime.manufacturing.run) as evaluate:
            report = run_agent(scenario, domain="manufacturing", inspection_slots=5)
        evaluate.assert_called_once_with(None, slots=5)
        ranking, queue, orders = report["tools"]
        self.assertEqual(ranking, run_agent(scenario)["tools"][0])
        self.assertEqual([case["sequence"] for case in orders["output"]["draft_cases"]],
                         [sequence for batch in queue["output"]["batches"] for sequence in batch])
        direct = run_agent("work-order-evidence", domain="manufacturing", max_tools=1, inspection_slots=5)
        self.assertEqual(direct["tools"], [orders])
        bounded = run_agent(scenario, domain="manufacturing", max_tools=2, inspection_slots=5)
        self.assertEqual(bounded["status"], "budget_exhausted")
        self.assertEqual(bounded["tools"], [ranking, queue])

    def test_inspection_capacity_checks_value_domain_and_reachability(self):
        for invalid in [True, False, 0, 9, "4", 4.0]:
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "integer from 1 to 8"):
                run_agent("inspection-queue", domain="manufacturing", inspection_slots=invalid)
        for domain in [None, "energy", "pharma"]:
            with self.subTest(domain=domain), self.assertRaisesRegex(ValueError, "explicit manufacturing"):
                run_agent("inspection-queue", domain=domain, inspection_slots=4)
        unrelated = [("condition-monitoring", 3), ("manufacturing-oee-losses", 3),
                     ("制造设备故障交接", 1), ("制造设备全流程", 1)]
        with patch.object(runtime.manufacturing, "run", wraps=runtime.manufacturing.run) as evaluate:
            for request, budget in unrelated:
                with self.subTest(request=request, budget=budget):
                    report = run_agent(request, domain="manufacturing", max_tools=budget, inspection_slots=4)
                    self.assertEqual(report["status"], "needs_clarification")
                    self.assertEqual(report["tools"], [])
                    self.assertIn("reachable inspection queue", report["review"][0])
        evaluate.assert_not_called()

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
