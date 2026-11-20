"""Route a business question to the industry workflows and print the evidence."""

import argparse
import json
import sys
from pathlib import Path

from industry_agent.model import LocalModelPlanner
from industry_agent.runtime import run_agent


def print_summary(report):
    print(f"{report['domain'] or 'Unrouted'} | {report['status']} | "
          f"{len(report['tools'])}/{report['max_tools']} tools")
    print(report["request"])
    if report["data"].get("kind"):
        print(f"Data: {report['data']['kind']}")
    for step in report["steps"]:
        print(f"  {step['kind']}: {step['message']}")
    for tool in report["tools"]:
        print(f"\n{tool['id']}")
        for key, value in tool["metrics"].items():
            print(f"  {key}: {value}")
        for name, rows in tool["output"].items():
            if isinstance(rows, list) and rows:
                example = json.dumps(rows[0], ensure_ascii=False, separators=(", ", ": "))
                print(f"  {name}[0]: {example}")
    for reason in report["review"]:
        print(f"  Review: {reason}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", help="Question or task in plain language")
    parser.add_argument("--domain", choices=("energy", "manufacturing", "pharma"),
                        help="Restrict the plan to one industry")
    parser.add_argument("--data-dir", type=Path, help="Use a custom cohort with --domain")
    parser.add_argument("--max-tools", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--local-model", metavar="NAME",
                        help="Use a model already running locally (e.g. Ollama)")
    parser.add_argument("--port", type=int, help="Local chat API port (default 11434)")
    parser.add_argument("--json", action="store_true", help="Emit the full run on stdout")
    parser.add_argument("--out", type=Path, help="Save the full run as JSON")
    args = parser.parse_args(argv)
    if args.port is not None and args.local_model is None:
        parser.error("--port requires --local-model")
    if args.data_dir is not None and args.domain is None:
        parser.error("--data-dir requires --domain")
    try:
        planner = None
        if args.local_model is not None:
            planner = LocalModelPlanner(args.local_model, 11434 if args.port is None else args.port)
        report = run_agent(args.request, domain=args.domain, max_tools=args.max_tools,
                           planner=planner, data_dir=args.data_dir)
        if args.json or args.out:
            full = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)
            if args.out:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(full + "\n", encoding="utf-8")
            if args.json:
                print(full)
        if not args.json:
            print_summary(report)
            if args.out:
                print(f"\nFull evidence: {args.out}")
    except (ValueError, OSError) as exc:
        print(f"agent: {exc}", file=sys.stderr)
        return 2
    return 0 if report["status"] in {"completed", "needs_review"} else 1


if __name__ == "__main__":
    if not sys.stdout.isatty():
        # Keep redirected reports interoperable even on non-UTF-8 Windows hosts.
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
