"""Build a self-contained GitHub Pages artifact, including real agent replays."""
import argparse
import hashlib
import json
import re
import shutil
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from industry_agent.catalog import entries
from industry_agent.runtime import run_agent
from verticals.manufacturing.harness import CAPACITY, MAX_INSPECTION_SLOTS

CORE_SHA256 = "9bc8f127db6c590b191b9aee754022cb41b1a36c7bac233776c11c5ecb541be8"
EXAMPLES = {
    "pharma": "检索 COPD 临床试验",
    "manufacturing": "按设备风险安排巡检，并生成工单",
    "energy": "预测明天的用电负荷，检查峰值预警，并为可调负荷排班",
}
SHOWCASE_IDS = ("trial_landscape", "inspection-queue", "flexible-load-scheduling")
STUDIO_SCRIPTS = (
    "run-history.js", "runtime-client.js", "result-table.js", "result-evidence.js", "result-review.js",
    "batch-workspace.js", "inspection-capacity.js", "studio.js",
)
STUDIO_STYLES = (
    "studio.css", "result-table.css", "result-review.css", "batch-workspace.css",
    "inspection-capacity.css",
)


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")


def build_showcase(reports):
    trial_id, queue_id, schedule_id = SHOWCASE_IDS
    trial_report = reports[trial_id]
    trial_source = trial_report["data"]["source"][trial_id]
    trial_result = trial_report["tools"][0]["output"]
    trial_hits = trial_result["hits"]
    trial_revision = trial_source["source_commit"]

    queue_report = reports[queue_id]
    queue = queue_report["tools"][0]
    queue_metrics, queue_output = queue["metrics"], queue["output"]

    reference_file = ROOT / "verticals/energy/reference_results.json"
    reopt = json.loads(reference_file.read_text(encoding="utf-8"))["runs"]["reopt_reference"]
    reopt_metrics = reopt["metrics"][schedule_id]
    if not reopt["checks"]["all_schedules_feasible"]:
        raise ValueError("Expected feasible schedules in the REopt benchmark")

    return {"cases": [
        {
            "id": trial_id,
            "domain": trial_report["domain"],
            "title": "从病种缩写找到可核查的试验",
            "eyebrow": "制药 · 公开历史登记",
            "question": f"研究团队如何从 {trial_result['query'].upper()} 快速找到相关临床试验？",
            "finding": f"在 {trial_source['count']} 条历史记录中找到 {len(trial_hits)} 个候选，"
                       f"首条 {trial_hits[0]['id']} 附登记链接和命中词。",
            "source": {
                "label": "美国 NCBI TrialGPT 历史语料",
                "url": f"https://github.com/ncbi-nlp/TrialGPT/blob/{trial_revision}/dataset/sigir/corpus.jsonl",
            },
            "caveat": "这是固定的小样本。当前招募状态和受试者资格需另外核对。",
        },
        {
            "id": queue_id,
            "domain": queue_report["domain"],
            "title": "用同样的巡检名额多发现故障",
            "eyebrow": "制造 · 合成设备观测",
            "question": f"每批 {queue_output['records_per_batch']} 条观测只能查 {queue_output['slots_per_batch']} 条，"
                        "该优先检查哪些记录？",
            "finding": f"同样巡检 {queue_metrics['records_reviewed']} 条，模型捕获 "
                       f"{queue_metrics['failures_in_queue']} 个故障标签，仅按刀具磨损排序捕获 "
                       f"{queue_metrics['wear_only_failures_at_same_capacity']} 个。",
            "source": {
                "label": "设备模拟器与对照方法",
                "url": "https://github.com/Linxiushen/industry-ai-harnesses/tree/main/verticals/manufacturing",
            },
            "caveat": f"离线合成结果仍有 {queue_metrics['false_alerts']} 条误报和 "
                      f"{queue_metrics['failures_outside_queue']} 条未入队故障，不衡量实际停机时间。",
        },
        {
            "id": schedule_id,
            "domain": reports[schedule_id]["domain"],
            "title": "给可调负荷选一个更低峰的窗口",
            "eyebrow": "能源 · 公开建模负荷",
            "question": "如何在截止时间前完成连续用电，同时压低全天峰值？",
            "finding": f"用 REopt 最后 {reopt['data']['test_days']} 天做离线对照。用电量相同的情况下，"
                       f"平均每日峰值由 {1000 * reopt_metrics['fixed_mean_daily_peak_mw']:.1f} kW "
                       f"降至 {1000 * reopt_metrics['mean_daily_peak_mw']:.1f} kW。",
            "source": {
                "label": "REopt 大型办公楼参考负荷",
                "url": reopt["data"]["source"],
            },
            "caveat": "REopt 对照使用单栋建筑建模负荷。网页使用内置合成样本演示同一调度逻辑。",
        },
    ]}


def extract_runtime(archive, target):
    if hashlib.sha256(archive.read_bytes()).hexdigest() != CORE_SHA256:
        raise ValueError("Unexpected Pyodide archive checksum")
    target.mkdir(exist_ok=True)
    # Preserve ancillary licenses and supporting modules shipped in the official distribution.
    with tarfile.open(archive, "r:bz2") as tar:
        entry = next(m.name for m in tar if Path(m.name).name == "pyodide.js")
        prefix = entry[:-len("pyodide.js")]
        for member in tar.getmembers():
            if not member.isfile() or not member.name.startswith(prefix):
                continue
            relative = Path(member.name[len(prefix):])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Invalid path in runtime archive")
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(member) as src, destination.open("wb") as out:
                shutil.copyfileobj(src, out)
    for required in ("pyodide.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"):
        if not (target / required).is_file():
            raise ValueError(f"Runtime archive lacks {required}")


def build(target, archive):
    target.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "worker.js", *STUDIO_STYLES, *STUDIO_SCRIPTS):
        shutil.copy2(ROOT / "docs" / name, target / name)
    files = set((ROOT / "industry_agent").rglob("*.py"))
    files.update((ROOT / "verticals").glob("*/harness.py"))
    files.update((ROOT / "verticals").glob("*/operations.py"))
    files.update((ROOT / "verticals/pharma/data").glob("*.json"))
    files.add(ROOT / "industry_agent/vendor/pocketflow/LICENSE")
    write_json(target / "bundle.json", {"files": {
        path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8") for path in sorted(files)
    }})
    examples = []
    for domain, request in EXAMPLES.items():
        report = run_agent(request, domain=domain, max_tools=3)
        if not report["tools"] or report["status"] == "error":
            raise ValueError(f"Unusable saved example for {domain}: {report['status']}")
        budget_request = ("检索 COPD 临床试验，筛选美国招募站点，列出需要跟进的结果登记"
                          if domain == "pharma" else request)
        one_tool_report = run_agent(budget_request, domain=domain, max_tools=1)
        expanded = report if budget_request == request else run_agent(budget_request, domain=domain, max_tools=3)
        if len(one_tool_report["tools"]) != 1 or len(expanded["tools"]) != 3:
            raise ValueError(f"Unusable budget comparison for {domain}: {one_tool_report['status']}")
        examples.append({"domain": domain, "request": request, "report": report,
                         "one_tool_report": one_tool_report,
                         **({"expanded_report": expanded} if expanded is not report else {})})
    write_json(target / "replays.json", {"examples": examples})
    catalog = entries()
    if len({item["id"] for item in catalog}) != len(catalog):
        raise ValueError("Scenario IDs must be unique")
    replay_dir = target / "scenarios"
    replay_dir.mkdir(exist_ok=True)
    featured_reports = {}
    for item in catalog:
        tool_id = item["id"]
        report = run_agent(item["prompt"], domain=item["domain"], max_tools=1)
        if (report["status"] not in ("completed", "needs_review")
                or [tool["id"] for tool in report["tools"]] != [tool_id]):
            raise ValueError(f"Unusable replay for {tool_id}: {report['status']}")
        write_json(replay_dir / f"{tool_id}.json", report)
        if tool_id in SHOWCASE_IDS:
            featured_reports[tool_id] = report
    write_json(target / "catalog.json", {"scenarios": catalog})
    write_json(target / "showcase.json", build_showcase(featured_reports))
    capacity_reports = [
        run_agent("inspection-queue", domain="manufacturing", max_tools=1, inspection_slots=slots)
        for slots in range(1, MAX_INSPECTION_SLOTS + 1)
    ]
    if any([tool["id"] for tool in report["tools"]] != ["inspection-queue"] or
           report["tools"][0]["output"]["slots_per_batch"] != slots
           for slots, report in enumerate(capacity_reports, 1)):
        raise ValueError("Unusable inspection capacity report")
    write_json(target / "inspection-capacity.json", {"default_slots": CAPACITY, "reports": capacity_reports})
    shutil.copy2(ROOT / "THIRD_PARTY.md", target)
    shutil.copytree(ROOT / "licenses", target / "licenses", dirs_exist_ok=True)
    shutil.copy2(ROOT / "industry_agent/vendor/pocketflow/LICENSE", target / "licenses/PocketFlow.txt")
    if archive:
        extract_runtime(archive, target / "engine")


def build_standalone(site, artifact):
    """Package fixture-only Studio as a single HTML file that opens directly from disk."""
    def read(name):
        return (site / name).read_text(encoding="utf-8")

    entry = read("index.html")
    def inline(name, start, end, reference):
        nonlocal entry
        content = read(name)
        if reference not in entry or re.search(r"</(?:script|style)\b", content, flags=re.I):
            raise ValueError(f"Cannot inline {name}")
        entry = entry.replace(reference, start + "\n" + content + "\n" + end, 1)

    for name in STUDIO_STYLES:
        inline(name, "<style>", "</style>", f'<link rel="stylesheet" href="./{name}">')
    # Each deferred script becomes an inline script below the DOM, in the same order.
    scripts = []
    for name in STUDIO_SCRIPTS:
        reference = f'<script defer src="./{name}"></script>'
        if reference not in entry:
            raise ValueError(f"Missing script {name}")
        entry = entry.replace(reference, "", 1)
        scripts.append(read(name))
        if re.search(r"</script\b", scripts[-1], flags=re.I):
            raise ValueError(f"Cannot inline {name}")
    fixtures = ["catalog.json", "replays.json", "showcase.json", "inspection-capacity.json",
                *(path.relative_to(site).as_posix() for path in sorted((site / "scenarios").glob("*.json")))]
    payload = json.dumps({"./" + name: json.loads(read(name)) for name in fixtures},
                         ensure_ascii=False, separators=(",", ":")).replace("<", r"\u003c")
    boot = f"""
const studioFixtures = {payload};
window.fetch = async (path, options) => {{
    options?.signal?.throwIfAborted();
    if (!Object.hasOwn(studioFixtures, path)) return new Response(null, {{status: 404}});
    return Response.json(studioFixtures[path]);
}};
"""
    entry = entry.replace("<body>", '<body data-offline-preview>', 1)
    entry = entry.replace("浏览器内运行</span>", "离线回放</span>", 1)
    scripts.insert(0, boot)
    entry = entry.replace("</body>", "\n".join(f"<script>{script}</script>" for script in scripts) + "\n</body>", 1)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(entry, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "output/site")
    parser.add_argument("--runtime-archive", type=Path, help="Pinned Pyodide core distribution for live browser runs")
    parser.add_argument("--standalone-preview", type=Path, help="Also write a single-file fixture-only preview")
    args = parser.parse_args()
    build(args.out, args.runtime_archive)
    if args.standalone_preview:
        build_standalone(args.out, args.standalone_preview)
