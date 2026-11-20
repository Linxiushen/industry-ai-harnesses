"""Rebuild the small published search projection from the upstream Git blob."""
import base64
import hashlib
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen


def projection(blob):
    rows = [json.loads(line) for line in blob.splitlines()[:12]]
    return [{"id": row["_id"], "conditions": row["metadata"]["diseases_list"],
             "phase": [row["metadata"]["phase"]] if row["metadata"]["phase"] else [],
             "url": "https://clinicaltrials.gov/study/" + row["_id"]} for row in rows]


if __name__ == "__main__":
    snapshot = json.loads((Path(__file__).with_name("data") / "trialgpt.json").read_text(encoding="utf-8"))
    expected = snapshot["source_blob"]
    if len(sys.argv) > 2:
        raise SystemExit("Usage: python verify_trialgpt.py [original-corpus.jsonl]")
    if len(sys.argv) == 2:
        content = Path(sys.argv[1]).read_bytes()
    else:
        request = Request(f"https://api.github.com/repos/ncbi-nlp/TrialGPT/git/blobs/{expected}",
                          headers={"User-Agent": "industry-ai-harnesses/1.0"})
        with urlopen(request, timeout=60) as response:
            payload = json.load(response)
        content = base64.b64decode(payload["content"])
    actual = hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()
    if actual != expected or projection(content) != snapshot["studies"]:
        raise SystemExit("Upstream blob or projected records differ from the bundled metadata")
    print(f"Verified {len(snapshot['studies'])} studies against Git blob {actual}")
