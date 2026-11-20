"""Run from the energy directory with python -m unittest -v test_energy."""
import csv
import hashlib
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path


def load_sibling(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


energy = load_sibling("harness")
eia = load_sibling("fetch_eia")


class EnergyReplayTests(unittest.TestCase):
    def test_unseen_day_does_not_change_that_days_forecast_alerts_or_schedule(self):
        reference = energy.run()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "load.csv"
            with path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["interval_start_utc", "load_mw"])
                days = energy.synthetic_days()
                for day, values in days:
                    for hour, y in enumerate(values):
                        if day == days[-1][0]:
                            y += 150 if hour == 2 else 30
                        writer.writerow([f"{day}T{hour:02}:00Z", y])
            replay = energy.run(temp)
            for i in (0, 1):
                self.assertEqual(reference["scenarios"][i]["output"], replay["scenarios"][i]["output"])
            ref_schedule = reference["scenarios"][2]["output"]["daily_schedules"]
            new_schedule = replay["scenarios"][2]["output"]["daily_schedules"]
            self.assertEqual([r["start_hour_utc"] for r in ref_schedule], [r["start_hour_utc"] for r in new_schedule])
            self.assertNotEqual(ref_schedule[-1]["observed_peak_mw"], new_schedule[-1]["observed_peak_mw"])
            (Path(temp) / "provenance.json").write_text(json.dumps({"csv_sha256": hashlib.sha256(b"other").hexdigest()}))
            with self.assertRaisesRegex(ValueError, "checksum"):
                energy.run(temp)

    def test_scheduler_respects_contiguous_slots_and_response_to_forecast(self):
        for expected in (15, 16, 17, 18, 19, 20):
            forecast = [100.0] * 24
            forecast[expected:expected + 3] = [50.0] * 3
            chosen = energy.choose_start(forecast, 20)
            self.assertEqual(chosen, expected)
            self.assertEqual(energy.peak_with_block(forecast, chosen, 20), 100)
        # When every feasible decision has the same peak and reserved energy, take the earliest.
        self.assertEqual(energy.choose_start([50.0] * 24, 10), 15)

    def test_eia_hour_ending_and_missing_duplicate_data(self):
        start = datetime(2024, 4, 1)
        records = [{"period": (start + timedelta(hours=i + 1)).strftime("%Y-%m-%dT%H"),
                    "type": "D", "respondent": "PJM", "value": str(i), "value-units": "megawatthours"}
                   for i in range(24)]
        payload = {"response": {"total": "24", "data": list(reversed(records))}}
        normalized = eia.normalize(payload, "PJM", start.date(), 1)
        self.assertEqual(normalized[0], ("2024-04-01T00:00Z", 0.0))
        self.assertEqual(normalized[-1], ("2024-04-01T23:00Z", 23.0))
        payload["response"]["data"].pop()
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            eia.normalize(payload, "PJM", start.date(), 1)
        payload["response"]["data"].append(records[-1])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            eia.normalize(payload, "PJM", start.date(), 1)

    def test_empty_peak_window_reports_unsupported_metrics(self):
        scores = energy.alert_scores([([3, 5], [4, 6])], limit=10, offset=0)
        self.assertEqual((scores["event_hours"], scores["alert_hours"]), (0, 0))
        self.assertIsNone(scores["recall"])
        self.assertIsNone(scores["precision"])
        self.assertIsNone(scores["f1"])


if __name__ == "__main__":
    unittest.main()
