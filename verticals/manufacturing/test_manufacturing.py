"""Offline regression tests for ranking, split hygiene and source-order ingestion."""

import csv
import importlib.util
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path


spec = importlib.util.spec_from_file_location("maintenance_replay", Path(__file__).with_name("harness.py"))
h = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = h
spec.loader.exec_module(h)


class ManufacturingTests(unittest.TestCase):
    def test_eval_labels_cannot_change_inference(self):
        train = h.synthetic_rows()[:400]
        model = h.HistogramClassifier(train, [r.failed for r in train])
        record = train[-1]
        altered = replace(record, sequence=99999, modes=("HDF", "OSF"), failed=not record.failed)
        self.assertEqual(model.score(record), model.score(altered))
        self.assertEqual(h.draft(record, {"HDF": model}), h.draft(altered, {"HDF": model}))

    def test_capacity_applies_locally_even_with_ties_and_short_final_batch(self):
        rows = h.synthetic_rows()[:27]
        scores = [0] * 25 + [100, 101]
        self.assertEqual(list(h.review_batches(rows, scores)), [[0, 1, 2], [26, 25]])
        self.assertEqual(list(h.review_batches(rows[:1], [99], slots=0)), [[]])

    def test_average_precision_counts_ties_together(self):
        self.assertAlmostEqual(h.average_precision([1, 1, 0], [True, False, True]), (0.5 + 2 / 3) / 2)
        self.assertIsNone(h.average_precision([1], [False]))

    def test_external_csv_and_source_order(self):
        header = ["UDI", "Air temperature [K]", "Process temperature [K]", "Rotational speed [rpm]",
                  "Torque [Nm]", "Tool wear [min]", "Machine failure", *h.MODE_NAMES]
        rows = h.synthetic_rows()[:100]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ai4i2020.csv"
            with path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(header)
                for row in rows:
                    writer.writerow([row.sequence, row.air, row.process, row.speed, row.torque, row.wear,
                                     int(row.failed), *(int(mode in row.modes) for mode in h.MODE_NAMES)])
            report = h.run(temp)
            self.assertEqual(report["data"]["first_test_sequence"], 76)
            self.assertEqual(report["data"]["kind"], "external_csv")
            self.assertTrue(all(report["checks"].values()))
            lines = path.read_text().splitlines()
            lines[-2], lines[-1] = lines[-1], lines[-2]
            path.write_text("\n".join(lines), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source order"):
                h.read_ai4i(path)


if __name__ == "__main__":
    unittest.main()
