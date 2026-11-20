"""Create a replayable hourly dataset from the public EIA-930 regional demand API."""
import argparse
import csv
import hashlib
import json
import math
import os
import tempfile
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


ENDPOINT = "https://api.eia.gov/v2/electricity/rto/region-data/data/"
TERMS = "https://www.eia.gov/about/copyrights_reuse.php"


def normalize(payload, region, start, days):
    begin = datetime.combine(start, time())
    rows = {}
    for item in payload["response"]["data"]:
        if item["type"] != "D" or item["respondent"] != region:
            raise ValueError("Unexpected demand series or balancing authority")
        if item["value-units"].lower() not in {"megawatthours", "megawatt-hours", "mwh"}:
            raise ValueError("Expected hourly energy in MWh")
        ending = datetime.strptime(item["period"], "%Y-%m-%dT%H")
        interval = ending - timedelta(hours=1)
        if interval in rows:
            raise ValueError(f"Duplicate hour {interval}")
        value = float(item["value"])
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"Invalid load at {interval}")
        rows[interval] = value  # MWh over 1 h equals average MW.
    expected_hours = [begin + timedelta(hours=h) for h in range(24 * days)]
    if set(rows) != set(expected_hours) or int(payload["response"]["total"]) != len(expected_hours):
        raise ValueError("Incomplete or out-of-period response; choose a complete date range")
    return [(t.strftime("%Y-%m-%dT%H:00Z"), rows[t]) for t in expected_hours]


def save_dataset(output_dir, normalized, provenance):
    """Publish complete, matching CSV + provenance together in a new directory."""
    if output_dir.exists():
        raise FileExistsError(f"Dataset already exists: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output_dir.parent) as temp:
        stage = Path(temp) / "dataset"
        stage.mkdir()
        csv_path = stage / "load.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(["interval_start_utc", "load_mw"])
            writer.writerows(normalized)
        provenance = {**provenance, "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest()}
        (stage / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
        stage.rename(output_dir)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path, help="New directory for the normalized dataset")
    parser.add_argument("--start", type=date.fromisoformat, default=date(2024, 4, 1))
    parser.add_argument("--days", type=int, default=84)
    parser.add_argument("--region", default="PJM")
    parser.add_argument("--response-json", type=Path, help="Normalize an existing EIA API response offline")
    args = parser.parse_args()
    if not 42 <= args.days <= 200:
        parser.error("Choose 42 to 200 contiguous UTC days (one API page)")
    if args.output_dir.exists():
        parser.error("Please choose a new output directory")
    start = datetime.combine(args.start, time())
    params = {"frequency": "hourly", "data[0]": "value", "facets[respondent][]": args.region,
              "facets[type][]": "D", "start": (start + timedelta(hours=1)).strftime("%Y-%m-%dT%H"),
              "end": (start + timedelta(days=args.days)).strftime("%Y-%m-%dT%H"),
              "sort[0][column]": "period", "sort[0][direction]": "asc", "length": 24 * args.days}
    if args.response_json:
        payload = json.loads(args.response_json.read_bytes())
        access = "user-supplied API response; origin not verified"
    else:
        key = os.environ.get("EIA_API_KEY")
        if not key:
            parser.error("Set EIA_API_KEY to your free EIA Open Data key or pass --response-json")
        try:
            with urlopen(ENDPOINT + "?" + urlencode({**params, "api_key": key}), timeout=30) as response:
                payload = json.load(response)
        except HTTPError as exc:
            parser.exit(1, f"EIA API returned HTTP {exc.code}\n")
        except URLError as exc:
            parser.exit(1, f"Unable to reach EIA API ({type(exc.reason).__name__})\n")
        access = "downloaded from api.eia.gov"
    normalized = normalize(payload, args.region, args.start, args.days)
    provenance = {"kind": "EIA-930 public records" if not args.response_json else "user-supplied EIA-format records",
                  "source": ENDPOINT, "attribution": "U.S. Energy Information Administration, Form EIA-930",
                  "terms": TERMS, "parameters": params, "access": access,
                  "normalized_at_utc": datetime.now(timezone.utc).isoformat(),
                  "transformation": "UTC hour ending minus one hour. MWh over one hour expressed as average MW."}
    save_dataset(args.output_dir, normalized, provenance)
    print(f"Saved {len(normalized)} hours to {args.output_dir}")


if __name__ == "__main__":
    main()
