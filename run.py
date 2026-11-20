"""Run one industry workflow or compare all offline examples on the same machine."""
import argparse
import importlib
import json
from pathlib import Path

DOMAINS = ("pharma", "energy", "manufacturing")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("domain", nargs="?", choices=("all", *DOMAINS), default="all")
    parser.add_argument("--data-dir", type=Path, help="Input directory for a single domain")
    parser.add_argument("--out", type=Path, help="Write the complete decisions and evidence to JSON")
    args = parser.parse_args()
    if args.domain == "all" and args.data_dir:
        parser.error("--data-dir requires a single domain")
    runs = []
    for domain in DOMAINS if args.domain == "all" else (args.domain,):
        report = importlib.import_module(f"verticals.{domain}.harness").run(args.data_dir)
        runs.append(report)
    complete = {"schema_version": 1, "runs": runs}
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(complete, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    for run in runs:
        print(f"[{run['domain']}] {run['data']['kind']}")
        for scenario in run["scenarios"]:
            print(f"  {scenario['id']}: {json.dumps(scenario['metrics'], allow_nan=False)}")
        for check, passed in run["checks"].items():
            if not passed:
                print(f"  FAILED: {check}")
    return int(any(not all(run["checks"].values()) for run in runs))


if __name__ == "__main__":
    raise SystemExit(main())
