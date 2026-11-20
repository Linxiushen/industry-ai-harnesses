"""Build a self-contained GitHub Pages artifact, including real agent replays."""
import argparse
import hashlib
import json
import shutil
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from industry_agent.catalog import entries
from industry_agent.runtime import run_agent

CORE_SHA256 = "9bc8f127db6c590b191b9aee754022cb41b1a36c7bac233776c11c5ecb541be8"
EXAMPLES = {
    "pharma": "检索 COPD 临床试验",
    "manufacturing": "按设备风险安排巡检，并生成工单",
    "energy": "预测明天的用电负荷，检查峰值预警，并为可调负荷排班",
}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")


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
    for name in ("index.html", "studio.css", "studio.js", "worker.js"):
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
        examples.append({"domain": domain, "request": request, "report": report})
    write_json(target / "replays.json", {"examples": examples})
    catalog = entries()
    if len({item["id"] for item in catalog}) != len(catalog):
        raise ValueError("Scenario IDs must be unique")
    replay_dir = target / "scenarios"
    replay_dir.mkdir(exist_ok=True)
    for item in catalog:
        tool_id = item["id"]
        report = run_agent(item["prompt"], domain=item["domain"], max_tools=1)
        if (report["status"] not in ("completed", "needs_review")
                or [tool["id"] for tool in report["tools"]] != [tool_id]):
            raise ValueError(f"Unusable replay for {tool_id}: {report['status']}")
        write_json(replay_dir / f"{tool_id}.json", report)
    write_json(target / "catalog.json", {"scenarios": catalog})
    shutil.copy2(ROOT / "THIRD_PARTY.md", target)
    shutil.copytree(ROOT / "licenses", target / "licenses", dirs_exist_ok=True)
    shutil.copy2(ROOT / "industry_agent/vendor/pocketflow/LICENSE", target / "licenses/PocketFlow.txt")
    if archive:
        extract_runtime(archive, target / "engine")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "output/site")
    parser.add_argument("--runtime-archive", type=Path, help="Pinned Pyodide core distribution for live browser runs")
    args = parser.parse_args()
    build(args.out, args.runtime_archive)
