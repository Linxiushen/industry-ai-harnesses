"""Offline clinical registry operations demo. All dates use the input snapshot."""
import argparse
import json
import math
import re
from collections import Counter
from datetime import date
from pathlib import Path


DATA = Path(__file__).with_name("data")
ALIASES = {"copd": "chronic obstructive pulmonary disease", "ckd": "chronic kidney disease",
           "t2dm": "type 2 diabetes mellitus", "nsclc": "non small cell lung cancer"}


def tokens(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def rank(studies, query, limit=3, weighted=True):
    """BM25 over condition metadata, with an optional literal-overlap comparator."""
    terms = tokens(query)
    if weighted:
        terms = [token for term in terms for token in ALIASES.get(term, term).split()]
    docs = [Counter(tokens(" ".join(s["conditions"]))) for s in studies]
    lengths = [sum(doc.values()) for doc in docs]
    average = sum(lengths) / max(1, len(docs)) or 1
    frequency = Counter(term for doc in docs for term in doc)
    hits = []
    for study, doc, length in zip(studies, docs, lengths):
        overlap = sorted(set(terms).intersection(doc))
        if not overlap:
            continue
        score = len(overlap)
        if weighted:
            score = sum(math.log1p((len(docs) - frequency[t] + .5) / (frequency[t] + .5))
                        * doc[t] * 2.2 / (doc[t] + 1.2 * (.25 + .75 * length / average))
                        for t in overlap)
        hits.append({"id": study["id"], "conditions": study["conditions"], "phase": study.get("phase", []),
                     "url": study.get("url"), "terms": overlap, "score": round(score, 6)})
    return sorted(hits, key=lambda h: (-h["score"], h["id"]))[:limit]


def age(value, as_of):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        days = (as_of - date.fromisoformat(value)).days
    except ValueError:
        return None
    return days if days >= 0 else None


def shortlist(studies, as_of, country="United States", max_age=180):
    eligible, unknown = [], []
    for study in studies:
        if study.get("status") != "RECRUITING":
            continue
        ref = {"study": study["id"], "url": study.get("url")}
        if not study.get("sites"):
            unknown.append({**ref, "reason": "site list missing"})
            continue
        for site in study["sites"]:
            if site.get("country") and site["country"] != country:
                continue
            if site.get("status") and site["status"] != "RECRUITING":
                continue
            # A city may contain multiple facilities. Queue one study/city follow-up.
            row = {**ref, "city": site.get("city"), "country": site.get("country")}
            days = age(study.get("updated"), as_of)
            if not all((site.get("country"), site.get("city"), site.get("status"))):
                unknown.append({**row, "reason": "missing site field"})
            elif days is None or days > max_age:
                unknown.append({**row, "reason": "registry update stale or undated"})
            elif row not in eligible:
                eligible.append(row)
    return {"shortlist": eligible, "manual_review": unknown, "country": country, "freshness_days": max_age}


def follow_up(studies, as_of, threshold=365):
    queue, unknown = [], []
    for study in studies:
        if study.get("status") != "COMPLETED" or study.get("has_results") is True:
            continue
        row = {"study": study["id"], "url": study.get("url")}
        days = age(study.get("primary_completion"), as_of)
        if study.get("has_results") is not False:
            unknown.append({**row, "reason": "unknown posting status"})
        elif days is None or study.get("completion_type") != "ACTUAL":
            unknown.append({**row, "reason": "need an actual day-precision completion date"})
        elif days >= threshold:
            queue.append({**row, "days_since_primary_completion": days})
    queue.sort(key=lambda r: (-r["days_since_primary_completion"], r["study"]))
    return {"follow_up": queue, "manual_review": unknown, "review_after_days": threshold}


def run(data_dir=None):
    folder = DATA if data_dir is None else Path(data_dir)
    snapshot = json.loads((folder / "registry.json").read_text(encoding="utf-8"))
    landscape_path = folder / "trialgpt.json"
    landscape = json.loads(landscape_path.read_text(encoding="utf-8")) if landscape_path.exists() else snapshot
    search_studies = landscape["studies"]
    search_ids = {s["id"] for s in search_studies}
    if not search_ids or len(search_ids) != len(search_studies):
        raise ValueError("Expected a nonempty search cohort with unique study IDs")
    studies = snapshot["studies"]
    ids = [study["id"] for study in studies]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("Expected a nonempty snapshot with unique study IDs")
    as_of = date.fromisoformat(snapshot["as_of"])
    query_path = folder / "questions.json"
    queries = json.loads(query_path.read_text(encoding="utf-8")) if query_path.exists() else [
        {"query": term} for term in ["CKD", "heart failure", "asthma"]]
    searches, metrics = [], {"queries": len(queries)}
    labeled = [q for q in queries if q.get("relevant")]
    for question in queries:
        if set(question.get("relevant", [])) - search_ids:
            raise ValueError("Relevance labels reference studies outside this snapshot")
        query = question["query"]
        searches.append({"query": query, "hits": rank(search_studies, query)})
    if labeled:
        for key, weighted in (("bm25_alias", True), ("literal_overlap", False)):
            reciprocal_ranks = []
            for question in labeled:
                relevant = set(question["relevant"])
                hits = rank(search_studies, question["query"], weighted=weighted)
                reciprocal_ranks.append(next((1 / i for i, h in enumerate(hits, 1)
                                              if h["id"] in relevant), 0))
            metrics[key + "_mrr_at_3"] = round(sum(reciprocal_ranks) / len(labeled), 4)
        metrics["labeled_positive_queries"] = len(labeled)
    site = shortlist(studies, as_of)
    results = follow_up(studies, as_of)
    checks = {
        "retrieval_evidence_references_snapshot": all(h["id"] in search_ids and h["terms"] for s in searches for h in s["hits"]),
        "review_queues_reference_snapshot": all(r["study"] in ids for r in site["shortlist"] + results["follow_up"]),
        "unique_studies": len(set(ids)) == len(ids),
    }
    if any(q.get("relevant") == [] for q in queries):
        checks["negative_queries_abstained"] = all(not s["hits"] for q, s in zip(queries, searches) if q.get("relevant") == [])
    source_info = {key: value for key, value in landscape.items() if key != "studies"}
    source_info["count"] = len(search_studies)
    ops_info = {key: value for key, value in snapshot.items() if key != "studies"}
    ops_info["count"] = len(studies)
    return {"domain": "pharma", "data": {"kind": "mixed" if landscape_path.exists() else snapshot["kind"],
            "source": {"trial_landscape": source_info, "operations": ops_info}}, "scenarios": [
        {"id": "trial_landscape", "data_source": "trial_landscape", "user": "Clinical intelligence analyst", "output": searches, "metrics": metrics},
        {"id": "recruiting_locations", "data_source": "operations", "user": "Trial feasibility coordinator", "output": site,
         "metrics": {"shortlisted_study_cities": len(site["shortlist"]), "manual_review": len(site["manual_review"])}},
        {"id": "registry_follow_up", "data_source": "operations", "user": "Registry operations lead", "output": results,
         "metrics": {"follow_ups": len(results["follow_up"]), "manual_review": len(results["manual_review"])}}
    ], "checks": checks}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA)
    print(json.dumps(run(parser.parse_args().data_dir), indent=2))
