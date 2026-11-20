"""Rank machine observations and prepare maintenance review cases, offline."""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import math
import random
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


SEED = 20261120
BATCH = 25
CAPACITY = 3
MAX_INSPECTION_SLOTS = 8
BINS = 12
MODE_NAMES = {
    "HDF": "heat dissipation",
    "PWF": "power",
    "OSF": "overstrain",
    "TWF": "tool wear",
    "RNF": "random failure",
}
FEATURES = ("temperature_gap_K", "speed_rpm", "power_kW", "wear_load_min_Nm", "tool_wear_min")
DOI = "https://doi.org/10.24432/C5HS5C"


@dataclass(frozen=True)
class Observation:
    sequence: int
    air: float
    process: float
    speed: float
    torque: float
    wear: float
    failed: bool
    modes: tuple[str, ...]

    def features(self):
        power = self.speed * self.torque * math.tau / 60_000
        return (self.process - self.air, self.speed, power, self.wear * self.torque, self.wear)


def synthetic_rows():
    """Original teaching workload. Each failure label includes unobserved noise."""
    rng = random.Random(SEED)
    rows = []
    wear = 0
    for seq in range(1, 4001):
        if wear > 225 or rng.random() < 0.008:
            wear = 0
        wear += rng.randint(1, 6)
        air = round(299 + 1.5 * math.sin(seq / 310) + rng.gauss(0, 0.5), 2)
        gap = max(4, rng.gauss(9.6 + 0.8 * math.cos(seq / 400), 1.5))
        process = round(air + gap, 2)
        speed = round(max(1000, rng.gauss(1510, 170)), 1)
        torque = round(max(10, rng.gauss(41, 7) - 0.025 * (speed - 1510)), 2)
        modes = []
        for mode, eligible, chance in (
            ("HDF", gap < 8.4 and speed < 1410, 0.65),
            ("PWF", speed * torque * math.tau / 60_000 > 8.0, 0.75),
            ("OSF", wear * torque > 8700, 0.70),
            ("TWF", wear > 198, 0.13),
            ("RNF", True, 0.012),
        ):
            if rng.random() < chance and eligible:
                modes.append(mode)
        rows.append(Observation(seq, air, process, speed, torque, wear, bool(modes), tuple(modes)))
    return rows


def read_ai4i(path):
    rows = []
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        records = csv.DictReader(handle)
        required = {"UDI", "Air temperature [K]", "Process temperature [K]", "Rotational speed [rpm]",
                    "Torque [Nm]", "Tool wear [min]", "Machine failure", *MODE_NAMES}
        if not required.issubset(records.fieldnames or ()):
            raise ValueError("Expected the UCI ai4i2020.csv headers")
        for record in records:
            if any(record[key] not in {"0", "1"} for key in ("Machine failure", *MODE_NAMES)):
                raise ValueError("Outcome and mode labels must be binary")
            row = Observation(
                int(record["UDI"]), float(record["Air temperature [K]"]), float(record["Process temperature [K]"]),
                float(record["Rotational speed [rpm]"]), float(record["Torque [Nm]"]), float(record["Tool wear [min]"]),
                record["Machine failure"] == "1", tuple(k for k in MODE_NAMES if record[k] == "1"),
            )
            if not all(math.isfinite(v) for v in (row.air, row.process, row.speed, row.torque, row.wear)):
                raise ValueError("Non-finite telemetry")
            if rows and row.sequence <= rows[-1].sequence:
                raise ValueError("Expected unique UDI in increasing source order")
            rows.append(row)
    if len(rows) < 100:
        raise ValueError("Too few ordered records for this split and batch size")
    return rows


class HistogramClassifier:
    """Bernoulli event classifier with independent, quantile-binned sensors."""

    def __init__(self, train, targets):
        if len(train) != len(targets) or not 0 < sum(targets) < len(targets):
            raise ValueError("Training requires both event and non-event observations")
        size = len(train)
        positives = sum(targets)
        self.prior = math.log((positives + 1) / (size - positives + 1))
        self.edges = []
        self.weights = []
        for column in zip(*(row.features() for row in train)):
            ordered = sorted(column)
            edges = sorted(set(ordered[size * index // BINS] for index in range(1, BINS)))
            counts = [Counter(), Counter()]
            for value, target in zip(column, targets):
                counts[int(target)][bisect.bisect_right(edges, value)] += 1
            width = len(edges) + 1
            self.edges.append(edges)
            self.weights.append([
                math.log((counts[1][b] + 1) / (positives + width))
                - math.log((counts[0][b] + 1) / (size - positives + width))
                for b in range(width)
            ])

    def evidence(self, row):
        return [weights[bisect.bisect_right(edges, value)]
                for value, edges, weights in zip(row.features(), self.edges, self.weights)]

    def score(self, row):
        return self.prior + sum(self.evidence(row))


def average_precision(scores, truth):
    """Non-interpolated AP, moving a threshold across each distinct score."""
    groups = {}
    for score, target in zip(scores, truth):
        hits, count = groups.get(score, (0, 0))
        groups[score] = (hits + target, count + 1)
    hits = count = 0
    area = 0.0
    for score in sorted(groups, reverse=True):
        events, size = groups[score]
        hits += events
        count += size
        area += events * hits / count
    return area / hits if hits else None


def review_batches(rows, scores, slots=CAPACITY):
    if len(scores) != len(rows) or slots < 0:
        raise ValueError("Invalid review workload")
    for start in range(0, len(rows), BATCH):
        indexes = range(start, min(start + BATCH, len(rows)))
        yield sorted(indexes, key=lambda i: (-scores[i], rows[i].sequence))[:slots]


def validate_inspection_slots(slots):
    if type(slots) is not int or not 1 <= slots <= MAX_INSPECTION_SLOTS:
        raise ValueError(f"inspection_slots must be an integer from 1 to {MAX_INSPECTION_SLOTS}.")


def draft(row, models):
    if not models:
        return {"suggested_category": "unclassified", "review_state": "draft", "evidence": []}
    category = max(models, key=lambda key: models[key].score(row))
    evidence = models[category].evidence(row)
    order = sorted(range(len(evidence)), key=lambda i: -evidence[i])
    features = row.features()
    return {
        "suggested_category": category if evidence[order[0]] > 0 else "unclassified",
        "review_state": "draft",
        "evidence": [{"field": FEATURES[i], "reading": round(features[i], 3),
                      "log_likelihood_ratio": round(evidence[i], 3)}
                     for i in order[:2] if evidence[i] > 0],
    }


def run(data_dir=None, *, slots=CAPACITY):
    validate_inspection_slots(slots)
    if data_dir is None:
        rows = synthetic_rows()
        serial = json.dumps([list(vars(row).values()) for row in rows], separators=(",", ":"))
        data = {"source": "Original seeded manufacturing simulator v1", "kind": "synthetic",
                "seed": SEED, "sha256": hashlib.sha256(serial.encode()).hexdigest(),
                "scope": "Synthetic ordered machine observations. Outcomes refer to the same observation."}
    else:
        path = Path(data_dir) / "ai4i2020.csv"
        rows = read_ai4i(path)
        data = {"source": "User-supplied AI4I-format CSV", "kind": "external_csv", "reference": DOI,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "scope": "UDI source order. The official AI4I benchmark is synthetic; provenance of supplied bytes depends on the caller."}
    split = len(rows) * 3 // 4
    train, test = rows[:split], rows[split:]
    risk = HistogramClassifier(train, [row.failed for row in train])
    models = {}
    for mode in MODE_NAMES:
        if mode == "RNF":
            continue
        labels = [row.failed and mode in row.modes for row in train]
        if 0 < sum(labels) < len(labels):
            models[mode] = HistogramClassifier(train, labels)
    scores = [risk.score(row) for row in test]
    truth = [row.failed for row in test]
    wear = [row.wear for row in test]
    queues = list(review_batches(test, scores, slots))
    selected = [i for queue in queues for i in queue]
    wear_queues = list(review_batches(test, wear, slots))
    baseline = [i for queue in wear_queues for i in queue]
    expected_sizes = [min(slots, len(test) - start) for start in range(0, len(test), BATCH)]
    caught = sum(truth[i] for i in selected)
    cases = [{"sequence": test[i].sequence, "review_batch": batch,
              "rank_within_batch": rank, **draft(test[i], models)}
             for batch, queue in enumerate(queues, 1) for rank, i in enumerate(queue, 1)]
    correct = sum(truth[i] and case["suggested_category"] in test[i].modes for i, case in zip(selected, cases))
    examples = sorted(range(len(test)), key=lambda i: (-scores[i], test[i].sequence))[:5]
    data.update({"rows": len(rows), "train_rows": split, "test_rows": len(test),
                 "first_test_sequence": test[0].sequence, "train_failures": sum(r.failed for r in train),
                 "test_failures": sum(truth), "features": list(FEATURES)})
    return {
        "domain": "manufacturing", "data": data,
        "scenarios": [
            {"id": "condition-monitoring", "user": "Reliability engineer",
             "output": {"highest_risk_records": [{"sequence": test[i].sequence, "ranking_score": round(scores[i], 3)}
                                                 for i in examples]},
             "metrics": {"average_precision": average_precision(scores, truth),
                         "wear_only_average_precision": average_precision(wear, truth),
                         "prevalence": sum(truth) / len(truth)}},
            {"id": "inspection-queue", "user": "Maintenance planner",
             "output": {"records_per_batch": BATCH, "slots_per_batch": slots,
                        "batches": [[test[i].sequence for i in queue] for queue in queues]},
             "metrics": {"records_reviewed": len(selected), "failures_in_queue": caught,
                         "failures_outside_queue": sum(truth) - caught, "false_alerts": len(selected) - caught,
                         "recall_at_capacity": caught / sum(truth) if any(truth) else None,
                         "wear_only_failures_at_same_capacity": sum(truth[i] for i in baseline)}},
            {"id": "work-order-evidence", "user": "Maintenance analyst",
             "output": {"category_key": MODE_NAMES, "draft_cases": cases},
             "metrics": {"draft_count": len(cases), "known_category_matches": correct,
                         "queued_confirmed_failures": caught, "category_accuracy_among_queued_failures": correct / caught if caught else None}},
        ],
        "checks": {"evaluation_follows_training": train[-1].sequence < test[0].sequence,
                   "queue_respects_capacity": all([len(queue) for queue in ranked] == expected_sizes
                                                  for ranked in (queues, wear_queues)),
                   "unique_review_cases": len(set(selected)) == len(selected),
                   "all_selected_cases_drafted": len(cases) == len(selected)},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", help="Optional directory containing ai4i2020.csv")
    print(json.dumps(run(parser.parse_args().data_dir), indent=2, allow_nan=False))
