import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from industry_agent.model import LocalModelPlanner

CATALOG = [{"id": "trial_landscape", "domain": "pharma", "description": "Search trials"}]
PLAN = {"domain": "pharma", "tools": ["trial_landscape"], "query": "COPD"}


class LocalModelTests(unittest.TestCase):
    @patch("industry_agent.model.http.client.HTTPConnection")
    def test_structured_plan_over_loopback(self, connect):
        conn = connect.return_value
        response = conn.getresponse.return_value
        response.status = 200
        response.read.return_value = json.dumps({"choices": [{
            "message": {"content": json.dumps(PLAN)}, "finish_reason": "stop",
        }]}).encode()

        planner = LocalModelPlanner("local-test", port=12345)
        self.assertEqual(planner("Find COPD trials", CATALOG), PLAN)
        connect.assert_called_once_with("127.0.0.1", 12345, timeout=60)
        method, path, body, _ = conn.request.call_args.args
        self.assertEqual((method, path), ("POST", "/v1/chat/completions"))
        payload = json.loads(body)
        self.assertEqual(payload["messages"][-1], {"role": "user", "content": "Find COPD trials"})
        self.assertEqual(payload["model"], "local-test")
        props = payload["response_format"]["json_schema"]["schema"]["properties"]
        self.assertEqual(props["tools"]["items"]["enum"], ["trial_landscape"])
        conn.close.assert_called_once()

    @patch("industry_agent.model.http.client.HTTPConnection")
    def test_invalid_and_truncated_responses_stop_before_execution(self, connect):
        response = connect.return_value.getresponse.return_value
        response.status = 200
        for reason, content in [("stop", "Here is a plan"), ("length", json.dumps(PLAN))]:
            with self.subTest(reason=reason):
                response.read.return_value = json.dumps({"choices": [{
                    "message": {"content": content}, "finish_reason": reason,
                }]}).encode()
                with self.assertRaisesRegex(ValueError, "complete JSON"):
                    LocalModelPlanner("test")("Find trials", CATALOG)

    @patch("industry_agent.model.http.client.HTTPConnection")
    def test_redirect_is_not_followed(self, connect):
        connect.return_value.getresponse.return_value.status = 307
        with self.assertRaisesRegex(ValueError, "HTTP 307"):
            LocalModelPlanner("test")("Find trials", CATALOG)
        self.assertEqual(connect.call_count, 1)

    @patch("industry_agent.model.http.client.HTTPConnection",
           side_effect=AssertionError("Offline route contacted a model server"))
    def test_default_cli_runs_offline_and_records_decisions(self, _):
        import agent

        out = io.StringIO()
        with redirect_stdout(out):
            result = agent.main(["Find historical COPD trials", "--json"])
        self.assertEqual(result, 0)
        run = json.loads(out.getvalue())
        self.assertEqual(run["domain"], "pharma")
        self.assertEqual([tool["id"] for tool in run["tools"]], ["trial_landscape"])
        self.assertTrue(run["tools"][0]["output"])


if __name__ == "__main__":
    unittest.main()
