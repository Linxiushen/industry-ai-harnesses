"""One UTC-day decision cycle for electricity demand, alerts and a flexible load."""

import argparse
import csv
import hashlib
import json
import math
import random
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean, median


FIRST_DAY = date(2024, 4, 1)
SEED = 4163
CALIBRATION_DAYS = 14
TEST_DAYS = 14
VALID_STARTS = range(15, 21)  # Three consecutive one-hour slots before 23:00.
FIXED_START = 17
BLOCK_HOURS = 3


def synthetic_days():
    """Independent demand simulator: working-day shape, weather regime and noise."""
    rng = random.Random(SEED)
    days = []
    weather = 0.0
    for index in range(84):
        day = FIRST_DAY + timedelta(days=index)
        workday = day.weekday() < 5
        weather = 0.79 * weather + rng.gauss(0.0, 3.2)
        morning_center = 8.0 if workday else 10.0
        evening_center = 18.0 + rng.uniform(-0.7, 0.7)
        hourly = []
        for hour in range(24):
            morning = 15 * math.exp(-((hour - morning_center) / 2.9) ** 2)
            evening = 29 * math.exp(-((hour - evening_center) / 3.6) ** 2)
            business = 8.0 * (workday and 8 <= hour < 18)
            level = 62.0 + 5 * workday + morning + evening + business
            hourly.append(round(level + weather + rng.gauss(0.0, 1.8), 3))
        days.append((day, hourly))
    return days


def load_days(data_dir):
    if data_dir is None:
        days = synthetic_days()
        encoded = json.dumps([(str(day), row) for day, row in days], separators=(",", ":")).encode()
        return days, {"kind": "synthetic", "source": "harness.synthetic_days", "seed": SEED,
                      "normalized_sha256": hashlib.sha256(encoded).hexdigest(),
                      "scope": "Simulated single electricity system, MW averaged over each UTC hour."}
    folder = Path(data_dir)
    path = folder / "load.csv"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    metadata_path = folder / "provenance.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    if "csv_sha256" in metadata and metadata["csv_sha256"] != digest:
        raise ValueError("load.csv checksum differs from provenance.json")
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            hour = datetime.strptime(row["interval_start_utc"], "%Y-%m-%dT%H:00Z")
            value = float(row["load_mw"])
            if not math.isfinite(value) or value < 0:
                raise ValueError("load_mw must be finite and nonnegative")
            if rows and hour != rows[-1][0] + timedelta(hours=1):
                raise ValueError("Expected ordered consecutive UTC intervals")
            rows.append((hour, value))
    if len(rows) < 42 * 24 or rows[0][0].hour or len(rows) % 24:
        raise ValueError("Expected at least 42 complete UTC days beginning at midnight")
    days = [(rows[i][0].date(), [value for _, value in rows[i:i + 24]]) for i in range(0, len(rows), 24)]
    return days, {"kind": metadata.get("kind", "user-supplied"),
                  "source": metadata.get("source", "load.csv; origin unspecified"),
                  "normalized_sha256": digest, "scope": metadata.get("scope", "One hourly series, MW, UTC interval starts."),
                  "hour_basis": metadata.get("hour_basis", "UTC interval start")}


def fit(train):
    profile = {}
    for workday in (False, True):
        group = [values for day, values in train if (day.weekday() < 5) == workday]
        profile[workday] = [mean(hour) for hour in zip(*group)]
    errors = [[y - p for y, p in zip(values, profile[day.weekday() < 5])]
              for day, values in train]
    previous = [v for row in errors[:-1] for v in row]
    current = [v for row in errors[1:] for v in row]
    denominator = sum(v * v for v in previous)
    weight = sum(x * y for x, y in zip(previous, current)) / denominator if denominator else 0
    return profile, weight


def predict(model, target, previous):
    profile, weight = model
    prior_day, prior_values = previous
    return [max(0.0, target_mean + weight * (y - prior_mean))
            for target_mean, prior_mean, y in zip(profile[target.weekday() < 5],
                                                   profile[prior_day.weekday() < 5], prior_values)]


def alert_scores(rows, limit, offset):
    tp = fp = fn = 0
    for forecast, actual in rows:
        for predicted, observed in zip(forecast, actual):
            alert, event = predicted >= limit + offset, observed >= limit
            tp += alert and event
            fp += alert and not event
            fn += not alert and event
    return {"true_positives": tp, "false_positives": fp, "missed_hours": fn,
            "event_hours": tp + fn, "alert_hours": tp + fp,
            "precision": round(tp / (tp + fp), 4) if tp + fp else None,
            "recall": round(tp / (tp + fn), 4) if tp + fn else None,
            "f1": round(2 * tp / (2 * tp + fp + fn), 4) if 2 * tp + fp + fn else None}


def peak_with_block(values, start, power):
    return max(v + power * (start <= h < start + BLOCK_HOURS) for h, v in enumerate(values))


def choose_start(forecast, power):
    return min(VALID_STARTS, key=lambda h: (peak_with_block(forecast, h, power),
                                            sum(forecast[h:h + BLOCK_HOURS]), h))


def run(data_dir=None):
    days, provenance = load_days(data_dir)
    test_start = len(days) - TEST_DAYS
    cal_start = test_start - CALIBRATION_DAYS
    train = days[:cal_start]
    model = fit(train)
    train_loads = sorted(v for _, row in train for v in row)
    limit = train_loads[math.ceil(len(train_loads) * 0.90) - 1]
    power = 0.12 * median(train_loads)  # Hypothetical additional flexible load.
    if power <= 0:
        raise ValueError("Training median must be positive for the flexible-load scenario")
    calibration = [(predict(model, days[i][0], days[i - 1]), days[i][1])
                   for i in range(cal_start, test_start)]
    error_scale = mean(abs(x - y) for xs, ys in calibration for x, y in zip(xs, ys))
    offsets = [error_scale * step / 2 for step in (0, -1, 1, -2, 2)]
    offset = max(offsets, key=lambda k: alert_scores(calibration, limit, k)["f1"] or 0)
    predictions, alerts, schedules = [], [], []
    test, prior_day, prior_week = [], [], []
    scheduled_peaks, fixed_peaks = [], []
    for i in range(test_start, len(days)):
        day, actual = days[i]
        forecast = predict(model, day, days[i - 1])
        start = choose_start(forecast, power)
        peak = peak_with_block(actual, start, power)
        fixed = peak_with_block(actual, FIXED_START, power)
        test.append((forecast, actual))
        prior_day.append((days[i - 1][1], actual))
        prior_week.append((days[i - 7][1], actual))
        predictions.append({"date": str(day), "forecast_mw": [round(x, 3) for x in forecast]})
        alerts.append({"date": str(day), "utc_hours": [h for h, y in enumerate(forecast) if y >= limit + offset]})
        schedules.append({"date": str(day), "start_hour_utc": start, "end_hour_utc": start + BLOCK_HOURS,
                          "observed_peak_mw": round(peak, 3), "fixed_start_peak_mw": round(fixed, 3)})
        scheduled_peaks.append(peak)
        fixed_peaks.append(fixed)

    def mae(pairs):
        return round(mean(abs(p - y) for ps, ys in pairs for p, y in zip(ps, ys)), 4)

    provenance.update({"start": str(days[0][0]), "end_inclusive": str(days[-1][0]),
                       "training_days": len(train), "calibration_days": CALIBRATION_DAYS,
                       "test_days": TEST_DAYS, "training_end": str(train[-1][0]),
                       "test_start": str(days[test_start][0])})
    provenance.setdefault("hour_basis", "UTC interval start")
    return {"domain": "energy", "data": provenance, "scenarios": [
        {"id": "day-ahead-load", "user": "Electricity demand planner",
         "output": {"daily_24h_forecasts": predictions},
         "metrics": {"mae_mw": mae(test), "prior_day_mae_mw": mae(prior_day),
                     "prior_week_mae_mw": mae(prior_week), "test_hours": 24 * len(test)}},
        {"id": "peak-hour-alerts", "user": "System operator staffing a peak watch",
         "output": {"event_threshold_mw": round(limit, 3), "forecast_trigger_mw": round(limit + offset, 3),
                    "daily_watch_hours": alerts},
         "metrics": {**alert_scores(test, limit, offset),
                     "prior_day_f1": alert_scores(prior_day, limit, 0)["f1"]}},
        {"id": "flexible-load-scheduling", "user": "Demand-response aggregator allocating an incremental load",
         "output": {"block_mw": round(power, 4), "duration_hours": BLOCK_HOURS,
                    "fixed_start_hour_utc": FIXED_START, "daily_schedules": schedules},
         "metrics": {"mean_daily_peak_mw": round(mean(scheduled_peaks), 4),
                     "fixed_mean_daily_peak_mw": round(mean(fixed_peaks), 4),
                     "mean_peak_reduction_mw": round(mean(fixed_peaks) - mean(scheduled_peaks), 4),
                     "peak_worse_days": sum(a > b for a, b in zip(scheduled_peaks, fixed_peaks)),
                     "total_incremental_energy_mwh": round(power * BLOCK_HOURS * TEST_DAYS, 4)}}
    ], "checks": {"chronological_split": train[-1][0] < days[cal_start][0] < days[test_start][0],
                  "all_336_test_predictions": sum(len(p["forecast_mw"]) for p in predictions) == 24 * TEST_DAYS,
                  "all_schedules_feasible": all(row["start_hour_utc"] in VALID_STARTS
                                                 and row["end_hour_utc"] - row["start_hour_utc"] == BLOCK_HOURS
                                                 for row in schedules)}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, help="Directory containing load.csv and optional provenance.json")
    args = parser.parse_args()
    print(json.dumps(run(args.data_dir), indent=2, allow_nan=False))
