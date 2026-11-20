"""PocketFlow supervisor for read-only industrial decision support."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from industry_agent.vendor.pocketflow import Flow, Node
from verticals.energy import harness as energy
from verticals.manufacturing import harness as manufacturing
from verticals.pharma import harness as pharma


# Only these nine project-owned adapters can be called by a planner.
TOOLS = {
    "trial_landscape": ("pharma", "Retrieve historical trials for a condition with ranked evidence.",
                        "trial search|historical|landscape|find trials|search trials|trial evidence|检索|试验检索|研究证据"),
    "recruiting_locations": ("pharma", "Shortlist study cities accepting recruitment at a snapshot date.",
                             "recruiting|recruitment|site|location|招募|站点|中心筛选"),
    "registry_follow_up": ("pharma", "Queue completed studies for review of results registration.",
                           "registration|follow up|follow-up|result posting|results|登记|随访|结果跟进"),
    "condition-monitoring": ("manufacturing", "Rank machine observations by estimated failure risk.",
                             "risk|condition monitoring|condition-monitoring|failure|sensor|故障|传感器|风险|状态监测"),
    "inspection-queue": ("manufacturing", "Allocate a fixed number of inspection slots per batch.",
                         "inspection|queue|巡检|巡查|点检|检查队列"),
    "work-order-evidence": ("manufacturing", "Draft work orders with sensor readings and ranked categories.",
                            "work order|work-order|工单|维修单"),
    "day-ahead-load": ("energy", "Backtest a 24-hour demand forecast against seasonal baselines.",
                       "forecast|day-ahead|day ahead|负荷预测|预测|日前"),
    "peak-hour-alerts": ("energy", "Identify hourly peak watches and evaluate missed events.",
                         "alert|peak watch|peak hour|peak-hour|peak risk|预警|尖峰时段|告警"),
    "flexible-load-scheduling": ("energy", "Schedule a movable load block against a fixed-start baseline.",
                                 "schedule|scheduling|dispatch|flexible load|flexible-load|排班|调度|移峰|可调负荷|安排充电"),
}
DOMAINS = {
    "pharma": "pharma|pharmaceutical|registry|clinical|trial|studies|制药|临床|试验|登记|招募",
    "manufacturing": "manufacturing|machine|equipment|maintenance|factory|inspection|work order|制造|设备|维修|工单|巡检|传感器",
    "energy": "energy|electricity|power grid|demand response|load|能源|电力|负荷|用电|电网|尖峰",
}
ADAPTIVE = "triage|handoff|shift brief|shift briefing|分诊|交接|值班简报|排查"
ALL = "full workflow|all tools|all scenarios|全流程|全部场景"
CONDITIONS = {
    "非小细胞肺癌": "NSCLC", "慢阻肺": "COPD", "慢性阻塞性肺病": "COPD", "膝骨关节炎": "knee osteoarthritis",
    "双相情感障碍": "bipolar disorder", "偏头痛": "migraine", "血液透析": "hemodialysis",
    "糖尿病": "diabetes", "心力衰竭": "heart failure", "慢性肾病": "CKD", "哮喘": "asthma",
}
COUNTRIES = {"加拿大": "Canada", "美国": "United States", "英国": "United Kingdom", "中国": "China",
             "日本": "Japan", "法国": "France", "德国": "Germany",
             "canada": "Canada", "united states": "United States", "usa": "United States",
             "united kingdom": "United Kingdom", "uk": "United Kingdom", "china": "China",
             "france": "France", "germany": "Germany", "japan": "Japan"}


def _matches(text, choices):
    for term in choices.split("|"):
        if term.isascii():
            if re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?:s|es)?(?![a-z0-9])", text):
                return True
        elif term in text:
            return True
    return False


def _named_condition(text):
    quoted = re.search(r"""["“]([^"”]+)["”]""", text)
    if quoted:
        return quoted[1].strip()
    for cn, alias in CONDITIONS.items():
        if cn in text:
            return alias
    # Resolve names before removing task words so "heart failure" stays intact.
    known = ("nsclc", "copd", "ckd", "t2dm", "bipolar disorder", "diabetes", "asthma", "migraine",
             "hemodialysis", "knee osteoarthritis", "heart failure", "voice disorders", "lung cancer")
    for term in known:
        if _matches(text, term):
            return term


def _condition(text):
    named = _named_condition(text)
    if named:
        return named
    words = re.findall(r"[a-z0-9]+", text)
    stop = set(("a an the and or to for in of by at on with please find search look up list retrieve show "
                "me historical clinical trials trial studies study registry pharma conditions condition "
                "evidence landscape related about get matched matching what are results all tools workflow "
                "full run recruiting recruitment sites locations compare registry follow registration").split())
    words = [word for word in words if word not in stop]
    return " ".join(words) or None


def _offline_plan(request, hint):
    text = request.casefold()
    matches = {d for d, terms in DOMAINS.items() if _matches(text, terms)}
    # Narrow technical phrases such as "peak-hour alert" also identify a domain.
    inferred_tools = [i for i, (_, _, terms) in TOOLS.items() if _matches(text, terms) or i in text]
    if not matches and not hint:
        # "risk", "forecast", and "queue" also describe finance, sales and many
        # other tasks. Require a specific industrial signal to infer a domain.
        if (_named_condition(text) and _matches(text, "search|retrieve|find|检索|查找")
                or _matches(text, "recruiting site|recruitment site|recruiting location|clinical site")):
            matches.add("pharma")
        elif _matches(text, "condition monitoring|condition-monitoring|work-order|sensor|故障"):
            matches.add("manufacturing")
        elif _matches(text, "day-ahead|peak-hour|peak hour|peak watch|peak alerts|移峰"):
            matches.add("energy")
        else:
            matches = {TOOLS[i][0] for i in inferred_tools if i in text}
    if hint:
        if matches - {hint}:
            return {"domain": None, "tools": []}
        matches = {hint}
    if len(matches) != 1:
        return {"domain": None, "tools": []}
    domain = matches.pop()
    ids = [i for i in inferred_tools if TOOLS[i][0] == domain]
    if _matches(text, ALL):
        ids = [i for i in TOOLS if TOOLS[i][0] == domain]
    if not ids and domain == "pharma" and _matches(text, "trial|studies|search|retrieve|find|试验|检索|查找"):
        ids = ["trial_landscape"]
    if not ids and _matches(text, ADAPTIVE):
        ids = [{"manufacturing": "condition-monitoring", "energy": "day-ahead-load",
                "pharma": "registry_follow_up"}[domain]]
    return {"domain": domain, "tools": ids}


def _proposal(raw, hint):
    if not isinstance(raw, dict) or set(raw) - {"domain", "tools", "query", "country"}:
        raise ValueError("Planner must return domain, tools, and optional query or country.")
    domain, ids = raw.get("domain"), raw.get("tools")
    if not isinstance(ids, list) or len(ids) > 3 or any(not isinstance(i, str) for i in ids):
        raise ValueError("Planner tools must be a list of at most three tool IDs.")
    if domain is None and ids == [] and "domain" in raw:
        return None, [], {}
    if not isinstance(domain, str) or domain not in DOMAINS or (hint and hint != domain):
        raise ValueError("Planner selected an unregistered or conflicting domain.")
    if any(i not in TOOLS or TOOLS[i][0] != domain for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("Planner selected a duplicate, unknown, or cross-domain tool.")
    params = {}
    for key, allowed in (("query", {"trial_landscape", "recruiting_locations", "registry_follow_up"}),
                         ("country", {"recruiting_locations"})):
        if key not in raw:
            continue
        value = raw[key]
        if not allowed.intersection(ids) or not isinstance(value, str) or not 1 <= len(value.strip()) <= 256:
            raise ValueError(f"Planner supplied an invalid {key} for this plan.")
        params[key] = value.strip()
    return domain, list(ids), params


def _step(s, kind, message, **fields):
    s["report"]["steps"].append(dict(kind=kind, message=message, **fields))


def _read_pharma(s, key):
    if key not in s["cache"]:
        folder = Path(s["data_dir"]) if s["data_dir"] is not None else pharma.DATA
        source = folder / "registry.json"
        if key == "trial_landscape" and (folder / "trialgpt.json").exists():
            source = folder / "trialgpt.json"
        payload = json.loads(source.read_text(encoding="utf-8"))
        ids = [row["id"] for row in payload["studies"]]
        if not ids or len(set(ids)) != len(ids):
            raise ValueError("Registry snapshot requires unique study IDs.")
        info = {k: v for k, v in payload.items() if k != "studies"}
        info["count"] = len(ids)
        s["cache"][key] = payload
        provenance = s["report"]["data"].setdefault("source", {})
        provenance[key] = info
        kinds = {v["kind"] for v in provenance.values()}
        s["report"]["data"]["kind"] = next(iter(kinds)) if len(kinds) == 1 else "mixed"
    return s["cache"][key]


def _tool(s, tool):
    domain = s["report"]["domain"]
    if domain != "pharma":
        if domain not in s["cache"]:
            module = {"energy": energy, "manufacturing": manufacturing}[domain]
            report = module.run(s["data_dir"])
            if not all(report["checks"].values()):
                raise ValueError("Domain evaluation failed its data or workload checks.")
            s["report"]["data"] = report["data"]
            s["cache"][domain] = {row["id"]: row for row in report["scenarios"]}
        return s["cache"][domain][tool]
    if tool == "trial_landscape":
        query = s["params"]["query"]
        payload = _read_pharma(s, tool)
        hits = pharma.rank(payload["studies"], query)
        return {"id": tool, "data_source": tool, "metrics": {"hit_count": len(hits)},
                "output": {"query": query, "hits": hits}}
    payload = _read_pharma(s, "operations")
    studies, as_of = payload["studies"], date.fromisoformat(payload["as_of"])
    # The registry and the historical search corpus can be different snapshots.
    # Apply a named condition to each cohort independently, never join by rank.
    condition = s["params"].get("query")
    if condition:
        # Ranking allows partial overlap. A filtered operational queue should
        # not admit CKD for COPD simply because both names contain "disease".
        terms = {token for word in pharma.tokens(condition) for token in pharma.ALIASES.get(word, word).split()}
        matches = {row["id"] for row in pharma.rank(studies, condition, limit=len(studies))
                   if terms.issubset(row["terms"])}
        studies = [row for row in studies if row["id"] in matches]
    if tool == "recruiting_locations":
        output = pharma.shortlist(studies, as_of, country=s["params"]["country"])
        metrics = {"shortlisted_study_cities": len(output["shortlist"]), "manual_review": len(output["manual_review"])}
    else:
        output = pharma.follow_up(studies, as_of)
        metrics = {"follow_ups": len(output["follow_up"]), "manual_review": len(output["manual_review"])}
    if condition:
        output["condition_filter"] = condition
        metrics["condition_matched_studies"] = len(studies)
    return {"id": tool, "data_source": "operations", "metrics": metrics, "output": output}


class Plan(Node):
    def post(self, s, prep_res, exec_res):
        report = s["report"]
        request = report["request"]
        planner = s["planner"]
        catalog = [{"id": i, "domain": d, "description": desc} for i, (d, desc, _) in TOOLS.items()
                   if not s["hint"] or d == s["hint"]]
        if planner:
            try:
                raw = planner(request, catalog)
            except Exception as exc:
                # Provider errors can contain headers, request text and credentials.
                s["reason"] = f"Planner unavailable ({type(exc).__name__})."
                return "error"
        else:
            raw = _offline_plan(request, s["hint"])
        try:
            domain, pending, params = _proposal(raw, s["hint"])
        except ValueError as exc:
            s["reason"] = str(exc)
            return "error"
        report["domain"] = domain
        if not pending:
            s["reason"] = "Specify one domain and its task, such as finding trials, allocating inspections or forecasting load."
            return "clarify"
        if "trial_landscape" in pending:
            if not params.get("query"):
                params["query"] = _condition(request.casefold())
            if not params["query"]:
                s["reason"] = "Which condition should the historical trial search use?"
                return "clarify"
        if domain == "pharma" and "query" not in params and _named_condition(request.casefold()):
            params["query"] = _named_condition(request.casefold())
        if "recruiting_locations" in pending and "country" not in params:
            country = next((name for term, name in COUNTRIES.items() if _matches(request.casefold(), term)), None)
            if not country:
                location = re.search(r"\b(?:in|country[:=])\s+([a-zA-Z][a-zA-Z -]*?)(?:[.,?!]|\s+for\b|$)",
                                     request, flags=re.IGNORECASE)
                country = location[1].strip().title() if location else "United States"
            params["country"] = country
        s.update(pending=pending, params=params, adaptive=planner is None and _matches(request.casefold(), ADAPTIVE))
        _step(s, "plan", "Selected registered tools for this request.", tools=list(pending), parameters=params,
              planner="external" if planner else "offline")
        return "tool"


class ExecuteTool(Node):
    def post(self, s, prep_res, exec_res):
        tool = s["pending"].pop(0)
        _step(s, "tool", TOOLS[tool][1], tool=tool)
        try:
            result = _tool(s, tool)
        except (OSError, KeyError, ValueError, TypeError, IndexError, ArithmeticError) as exc:
            s["reason"] = f"{tool} could not read or evaluate its input ({type(exc).__name__})."
            return "error"
        s["report"]["tools"].append(result)
        return "observe"


def _observe(tool):
    """Return an observation, a review reason, and a candidate evidence-driven next action."""
    key, m, out = tool["id"], tool["metrics"], tool["output"]
    if key == "trial_landscape":
        n = m["hit_count"]
        return (f"{n} historical registry hits for '{out['query']}'.",
                None if n else "No matching condition terms in this snapshot. Verify the query and registry coverage.", None)
    if key == "recruiting_locations":
        n, manual = m["shortlisted_study_cities"], m["manual_review"]
        return (f"{n} study/city pairs in {out['country']}; {manual} entries need manual review.",
                "Verify site availability and stale or missing fields against current registry records.", None)
    if key == "registry_follow_up":
        return (f"{m['follow_ups']} results-posting follow-ups; {m['manual_review']} incomplete records.",
                "Registry staff must verify dates, applicability and posting status before outreach.", None)
    if key == "condition-monitoring":
        n = len(out["highest_risk_records"])
        return f"Ranked {n} high-risk examples on the held-out observations.", None, "inspection-queue" if n else None
    if key == "inspection-queue":
        n = m["records_reviewed"]
        return (f"{n} inspection slots selected; {m['failures_in_queue']} confirmed failures on retrospective labels.",
                "Review the queue against available technicians and false-alert workload.",
                "work-order-evidence" if n else None)
    if key == "work-order-evidence":
        return (f"{m['draft_count']} draft work orders include associated sensor evidence.",
                "A technician must validate the suggested category and authorize each work order.", None)
    if key == "day-ahead-load":
        baseline = min(m["prior_day_mae_mw"], m["prior_week_mae_mw"])
        worse = m["mae_mw"] > baseline
        return (f"Forecast MAE {m['mae_mw']} MW; best seasonal baseline {baseline} MW.",
                "A seasonal baseline has lower held-out MAE. Review model selection before operational use." if worse else None,
                "peak-hour-alerts" if m["test_hours"] else None)
    if key == "peak-hour-alerts":
        return (f"{m['alert_hours']} forecast watch hours; {m['event_hours']} observed high-load hours.",
                "No observed threshold crossings. Alert recall cannot be estimated." if not m["event_hours"] else None,
                "flexible-load-scheduling" if m["alert_hours"] else None)
    return (f"Mean daily peak reduction {m['mean_peak_reduction_mw']} MW; {m['peak_worse_days']} days had higher peaks.",
            "Check physical constraints and obtain operator authorization before changing a load schedule.", None)


class Observe(Node):
    def post(self, s, prep_res, exec_res):
        report = s["report"]
        tool = report["tools"][-1]
        message, review, follow = _observe(tool)
        known = set(s["pending"]) | {r["id"] for r in report["tools"]}
        added = follow if s["adaptive"] and follow and follow not in known else None
        if added:
            s["pending"].append(added)
        _step(s, "observe", message, tool=tool["id"], follow_up=added)
        if review:
            report["review"].append(review)
        if not s["pending"]:
            return "review" if report["review"] else "complete"
        if len(report["tools"]) >= report["max_tools"]:
            s["reason"] = "Tool budget reached. Pending: " + ", ".join(s["pending"]) + "."
            return "budget"
        return "tool"


class Finish(Node):
    def __init__(self, kind, status):
        super().__init__()
        self.kind, self.status = kind, status

    def post(self, s, prep_res, exec_res):
        report = s["report"]
        report["status"] = self.status
        if "reason" in s:
            report["review"].append(s["reason"])
        message = s.get("reason") or ("Human review requested." if report["review"] else "All requested evidence collected.")
        _step(s, self.kind, message)


def run_agent(request: str, *, domain: str | None = None, max_tools: int = 3,
              planner=None, data_dir=None) -> dict:
    """Run a bounded local graph. An optional planner receives (request, tool catalog)."""
    if not isinstance(request, str) or not request.strip() or len(request) > 4000:
        raise ValueError("Request must contain 1 to 4000 characters.")
    if domain is not None and domain not in DOMAINS:
        raise ValueError("Unknown domain.")
    if type(max_tools) is not int or not 1 <= max_tools <= 3:
        raise ValueError("max_tools must be an integer from 1 to 3.")
    report = dict(request=request, domain=domain, status=None, max_tools=max_tools, steps=[], tools=[], review=[], data={})
    shared = dict(report=report, hint=domain, planner=planner, data_dir=data_dir, cache={})
    plan, execute, observe = Plan(), ExecuteTool(), Observe()
    error = Finish("error", "error")
    plan - "clarify" >> Finish("clarify", "needs_clarification")
    plan - "error" >> error
    plan - "tool" >> execute
    execute - "error" >> error
    execute - "observe" >> observe
    observe - "tool" >> execute
    observe - "budget" >> Finish("budget", "budget_exhausted")
    observe - "review" >> Finish("review", "needs_review")
    observe - "complete" >> Finish("complete", "completed")
    Flow(start=plan).run(shared)
    return report
