"""Fetch a small cohort from ClinicalTrials.gov API v2 and keep selected metadata."""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


def project(study, nct_id):
    protocol = study["protocolSection"]
    if protocol["identificationModule"]["nctId"] != nct_id:
        raise ValueError(f"Registry ID mismatch for {nct_id}")
    status = protocol.get("statusModule", {})
    completion = status.get("primaryCompletionDateStruct", {})
    sites = protocol.get("contactsLocationsModule", {}).get("locations", [])
    return {
        "id": nct_id, "url": f"https://clinicaltrials.gov/study/{nct_id}",
        "phase": protocol.get("designModule", {}).get("phases", []),
        "conditions": protocol.get("conditionsModule", {}).get("conditions", []),
        "status": status.get("overallStatus"), "updated": status.get("lastUpdatePostDateStruct", {}).get("date"),
        "primary_completion": completion.get("date"), "completion_type": completion.get("type"),
        "has_results": study.get("hasResults"),
        "sites": [{k: site.get(k) for k in ("city", "country", "status")} for site in sites],
    }


def fetch(ids, output):
    if not ids or len(ids) > 25 or len(set(ids)) != len(ids) or not all(re.fullmatch(r"NCT[0-9]{8}", i) for i in ids):
        raise ValueError("Provide 1 to 25 different NCT identifiers")
    if output.exists():
        raise FileExistsError(output)
    studies = []
    for nct_id in ids:
        url = f"https://clinicaltrials.gov/api/v2/studies/{nct_id}"
        request = Request(url, headers={"Accept": "application/json", "User-Agent": "industry-ai-harnesses/1.0"})
        with urlopen(request, timeout=30) as response:
            blob = response.read()
        record = project(json.loads(blob), nct_id)
        record["api_url"] = url
        record["retrieved_at"] = datetime.now(timezone.utc).isoformat()
        record["api_payload_sha256"] = hashlib.sha256(blob).hexdigest()
        studies.append(record)
    snapshot = {"kind": "registry", "as_of": datetime.now(timezone.utc).date().isoformat(),
                "source": "ClinicalTrials.gov (U.S. National Library of Medicine), selected API v2 registry fields",
                "terms_url": "https://clinicaltrials.gov/policy/terms-conditions", "studies": studies}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(snapshot, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ids", nargs="+")
    parser.add_argument("--output", required=True, type=Path)
    options = parser.parse_args()
    fetch(options.ids, options.output)
