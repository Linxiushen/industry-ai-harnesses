"""Administrative trial workflows backed by a dated synthetic snapshot."""

import json
from datetime import date, timedelta
from pathlib import Path


FIXTURE = Path(__file__).with_name("data") / "operations.json"

SCENARIOS = {
    "pharma-site-startup": {
        "title": "站点启动清单",
        "stage": "试验启动",
        "description": "Screen upcoming or overdue site activations against documented prerequisites.",
        "prompt": "检查临床试验站点启动条件，列出到期阻塞和需要补证的事项。",
        "aliases": "站点启动|启动清单|site startup|site activation",
        "columns": {"site": "站点", "planned": "计划启动", "status": "处理建议",
                    "owner": "负责团队", "incomplete": "待办条件"},
    },
    "pharma-enrollment-forecast": {
        "title": "招募进度预测",
        "stage": "招募执行",
        "description": "Compare a capacity-limited rolling enrollment projection with the study target.",
        "prompt": "估算临床试验未来四周的招募进度，并标出目标缺口。",
        "aliases": "招募进度|招募预测|目标缺口|enrollment forecast|recruitment forecast",
        "columns": {"site": "站点", "current": "累计入组", "additional": "预测新增",
                    "projected_total": "预测累计", "status": "说明"},
    },
    "pharma-monitoring-queue": {
        "title": "监查访视排程",
        "stage": "质量监查",
        "description": "Allocate limited monitoring visit slots by documented findings, due date and availability.",
        "prompt": "安排临床试验监查访视，按问题优先级和已确认档期分配名额。",
        "aliases": "监查访视|监查排程|monitoring visit|monitoring queue",
        "columns": {"site": "站点", "due": "到期日", "high_priority_findings": "高优先问题",
                    "status": "排程建议", "owner": "监查团队"},
    },
    "pharma-data-query-aging": {
        "title": "数据质疑账龄",
        "stage": "数据管理",
        "description": "Calculate response aging and route open operational data queries to accountable teams.",
        "prompt": "查看临床试验数据质疑账龄，把待响应事项按优先级和时限排序。",
        "aliases": "数据质疑|质疑账龄|data query aging|query backlog",
        "columns": {"query": "质疑单", "site": "站点", "age_days": "账龄（天）",
                    "status": "处理建议", "owner": "负责团队"},
    },
    "pharma-supply-triage": {
        "title": "试验物资库存",
        "stage": "物资保障",
        "description": "Project nonmedical materials inventory through lead time and identify replenishment or expedited needs.",
        "prompt": "检查试验物资库存，按每日消耗和到货日期区分补货与加急需求。",
        "aliases": "物资库存|物资补货|临床物资|trial supplies|supply triage",
        "columns": {"site": "站点", "material": "行政耗材", "status": "处理建议",
                    "first_shortage": "预计缺货日", "coverage_gap_units": "常规补货缺口"},
    },
    "pharma-closeout-readiness": {
        "title": "关站归档检查",
        "stage": "项目结题",
        "description": "Check closeout readiness using retrievable evidence IDs and unclosed actions.",
        "prompt": "检查临床试验关站归档，找出缺失证据和尚未关闭的事项。",
        "aliases": "关站归档|关站检查|结题归档|closeout readiness|site closeout",
        "columns": {"site": "站点", "planned": "计划关站", "status": "准备状态",
                    "open_actions": "未结事项", "missing_evidence": "缺少证据"},
    },
}


def _startup(config, as_of):
    lookahead = config["lookahead_days"]
    rows = []
    for site in config["sites"]:
        days_until = (date.fromisoformat(site["planned"]) - as_of).days
        blocked = [check for check in config["required"] if site["checks"].get(check) is False]
        unknown = [check for check in config["required"] if site["checks"].get(check) is None]
        if days_until > lookahead:
            status = "后续排期"
        elif blocked:
            status = "已到期且受阻" if days_until <= 0 else "需解除阻塞"
        elif unknown:
            status = "需补证"
        else:
            status = "可提交启动复核"
        rows.append({
            "site": site["site"], "planned": site["planned"], "status": status,
            "owner": site["owner"], "incomplete": "、".join(blocked + unknown),
            "days_until": days_until, "blocking_checks": blocked, "unknown_checks": unknown,
            "reported_checks": site["checks"],
        })

    order = ("已到期且受阻", "需解除阻塞", "需补证", "可提交启动复核", "后续排期")
    rows.sort(key=lambda row: (order.index(row["status"]), row["planned"], row["site"]))
    metrics = {
        "窗口内站点": sum(row["days_until"] <= lookahead for row in rows),
        "到期受阻": sum(row["status"] == "已到期且受阻" for row in rows),
        "待补证": sum(row["status"] == "需补证" for row in rows),
        "可提交复核": sum(row["status"] == "可提交启动复核" for row in rows),
    }
    return metrics, {"records": rows, "lookahead_days": lookahead, "required_checks": config["required"]}


def _enrollment(config, as_of):
    horizon = config["horizon_weeks"]
    window = config["window_weeks"]
    rows = []
    for site in config["sites"]:
        observations = site["weekly"][-window:]
        rate = None
        remaining_capacity = max(0, site["capacity"] - site["current"])
        if not site["recruiting"]:
            additional, status = 0, "暂停招募"
        elif len(observations) < window:
            additional, status = None, "历史不足，人工估算"
        else:
            rate = sum(observations) / window
            expected = rate * horizon
            additional = min(remaining_capacity, expected)
            status = "受站点容量限制" if expected > remaining_capacity else "按近周均值推算"
        projected_total = None if additional is None else round(site["current"] + additional, 1)
        rows.append({
            "site": site["site"], "current": site["current"],
            "additional": None if additional is None else round(additional, 1),
            "projected_total": projected_total, "status": status,
            "observed_weeks": len(observations), "weekly_aggregate": observations,
            "weekly_rate": rate, "remaining_capacity": remaining_capacity,
        })

    current = sum(row["current"] for row in rows)
    projected = current + sum(row["additional"] or 0 for row in rows)
    missing = sum(row["additional"] is None for row in rows)
    target = config["study_target"]
    metrics = {
        "当前累计入组": current, "已知预测累计": round(projected, 1),
        "研究目标": target, "按已知预测仍差": round(max(0, target - projected), 1),
        "历史不足站点": missing,
    }
    return metrics, {
        "records": rows, "target_date": (as_of + timedelta(weeks=horizon)).isoformat(),
        "forecast_weeks": horizon, "history_weeks": window, "partial_projection": bool(missing),
    }


def _monitoring(config, as_of):
    window_end = as_of + timedelta(days=config["window_days"])
    ordered = sorted(config["sites"], key=lambda site: (
        -site["high_priority_findings"], site["due"], site["site"],
    ))
    rows = []
    slots_used = 0
    candidates = 0
    for site in ordered:
        due = date.fromisoformat(site["due"])
        urgent = site["high_priority_findings"] > 0
        if not urgent and due > window_end:
            status = "窗口外"
        else:
            candidates += 1
            if not site["confirmed_availability"]:
                status = "待确认档期"
            elif slots_used == config["visit_slots"]:
                status = "候补"
            else:
                slots_used += 1
                status = "建议安排"
        rows.append({
            "site": site["site"], "due": site["due"],
            "high_priority_findings": site["high_priority_findings"], "status": status,
            "owner": site["owner"], "availability_confirmed": site["confirmed_availability"],
            "days_until": (due - as_of).days,
        })

    metrics = {
        "进入排程的候选": candidates, "已分配名额": slots_used,
        "候补站点": sum(row["status"] == "候补" for row in rows),
        "待确认档期": sum(row["status"] == "待确认档期" for row in rows),
    }
    return metrics, {
        "records": rows, "slots": config["visit_slots"], "window_end": window_end.isoformat(),
        "ordering": "高优先问题数量由多到少，其次按到期日由早到晚",
    }


def _query_aging(config, as_of):
    thresholds = config["sla_days"]
    rows = []
    for query in config["queries"]:
        if query["state"] == "closed":
            continue
        limit = thresholds.get(query["priority"])
        opened = query["opened"]
        age_days = (as_of - date.fromisoformat(opened)).days if opened else None
        if age_days is None or age_days < 0 or limit is None:
            status, overdue = "核对开单日期或优先级", None
        else:
            overdue = max(0, age_days - limit)
            if overdue:
                status = "已超时"
            elif age_days == limit:
                status = "今日到期"
            else:
                status = "时限内"
        rows.append({
            "query": query["query"], "site": query["site"], "age_days": age_days,
            "status": status, "owner": query["owner"], "topic": query["topic"],
            "priority": query["priority"], "opened": opened, "sla_days": limit, "overdue_days": overdue,
        })

    state_order = ("已超时", "今日到期", "核对开单日期或优先级", "时限内")
    rows.sort(key=lambda row: (
        state_order.index(row["status"]), row["priority"] != "high",
        -(row["overdue_days"] or 0), row["query"],
    ))
    metrics = {
        "待响应质疑": len(rows), "已超时": sum(row["status"] == "已超时" for row in rows),
        "今日到期": sum(row["status"] == "今日到期" for row in rows),
        "缺少核算依据": sum(row["overdue_days"] is None for row in rows),
    }
    return metrics, {"records": rows, "sla_calendar_days": thresholds}


def _inventory_projection(item, buffer_days, as_of):
    """Compute days after snapshot close, with receipts posted before daily consumption."""
    usage = item["daily_usage"]
    if usage is None:
        return None, None, None
    lead = item["lead_days"]
    horizon = lead + buffer_days
    receipts = {}
    for shipment in item["incoming"]:
        offset = (date.fromisoformat(shipment["due"]) - as_of).days
        if 0 < offset <= horizon:
            receipts[offset] = receipts.get(offset, 0) + shipment["units"]

    balance = item["on_hand"]
    first_shortage = None
    early_gap = ordinary_gap = 0
    for offset in range(1, horizon + 1):
        balance += receipts.get(offset, 0) - usage
        if balance < 0 and first_shortage is None:
            first_shortage = (as_of + timedelta(days=offset)).isoformat()
        if offset < lead:
            early_gap = max(early_gap, -balance)
        else:
            ordinary_gap = max(ordinary_gap, -balance)
    # An expedited transfer has already covered the deficit when normal replenishment arrives.
    return first_shortage, early_gap, max(0, ordinary_gap - early_gap)


def _supplies(config, as_of):
    rows = []
    for item in config["items"]:
        lead = item["lead_days"]
        shortage, early_gap, ordinary_gap = _inventory_projection(item, config["buffer_days"], as_of)
        if early_gap is None:
            status = "核对消耗记录"
        elif early_gap:
            status = "复核加急调拨"
        elif ordinary_gap:
            status = "建议常规补货"
        else:
            status = "库存覆盖计划期"
        rows.append({
            "site": item["site"], "sku": item["sku"], "material": item["material"],
            "status": status, "first_shortage": shortage, "coverage_gap_units": ordinary_gap,
            "expedited_gap_units": early_gap, "on_hand": item["on_hand"],
            "daily_usage": item["daily_usage"], "incoming": item["incoming"],
            "ordinary_arrival": (as_of + timedelta(days=lead)).isoformat(),
            "projection_through": (as_of + timedelta(days=lead + config["buffer_days"])).isoformat(),
        })

    order = ("复核加急调拨", "建议常规补货", "核对消耗记录", "库存覆盖计划期")
    rows.sort(key=lambda row: (order.index(row["status"]), row["site"], row["sku"]))
    metrics = {
        "物资条目": len(rows), "需加急复核": sum(bool(row["expedited_gap_units"]) for row in rows),
        "需常规补货": sum(bool(row["coverage_gap_units"]) for row in rows),
        "消耗缺失": sum(row["status"] == "核对消耗记录" for row in rows),
    }
    return metrics, {"records": rows, "buffer_days": config["buffer_days"]}


def _closeout(config, as_of):
    rows = []
    for site in config["sites"]:
        missing = [key for key in config["required_evidence"] if not site["documents"].get(key)]
        open_actions = site["open_actions"]
        due = date.fromisoformat(site["planned"]) <= as_of
        if missing or open_actions:
            status = "到期仍缺条件" if due else "待补条件"
        else:
            status = "可提交关站复核"
        rows.append({
            "site": site["site"], "planned": site["planned"], "status": status,
            "open_actions": open_actions, "missing_evidence": "、".join(missing),
            "owner": site["owner"], "evidence_refs": site["documents"],
        })

    order = ("到期仍缺条件", "待补条件", "可提交关站复核")
    rows.sort(key=lambda row: (order.index(row["status"]), row["planned"], row["site"]))
    metrics = {
        "可提交复核": sum(row["status"] == "可提交关站复核" for row in rows),
        "到期仍缺条件": sum(row["status"] == "到期仍缺条件" for row in rows),
        "证据缺失站点": sum(bool(row["missing_evidence"]) for row in rows),
        "未关闭事项": sum(row["open_actions"] for row in rows),
    }
    return metrics, {"records": rows, "required_evidence": config["required_evidence"]}


_EXECUTION = {
    "pharma-site-startup": (
        "site_startup", _startup, "启动团队核验缺失材料和审批记录后签发站点启动通知。",
    ),
    "pharma-enrollment-forecast": (
        "enrollment_forecast", _enrollment, "运营负责人核对站点停招状态和统计周覆盖。招募预测以近期的站点汇总数据为依据。",
    ),
    "pharma-monitoring-queue": (
        "monitoring_queue", _monitoring, "监查负责人确认日程、职责分配及需要升级处理的问题。",
    ),
    "pharma-data-query-aging": (
        "data_query_aging", _query_aging, "数据管理团队核对开单日期和项目内部时限后联系负责人。",
    ),
    "pharma-supply-triage": (
        "supply_triage", _supplies, "物资协调员核对库存和预计到货时间后决定调拨或补货数量。样本只涉及行政耗材。",
    ),
    "pharma-closeout-readiness": (
        "closeout_readiness", _closeout, "结题负责人根据证据编号核对原件并签核关站。",
    ),
}


def run(tool_id):
    fixture_key, execute, review = _EXECUTION[tool_id]
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    config = fixture[fixture_key]
    as_of = date.fromisoformat(fixture["as_of"])
    metrics, output = execute(config, as_of)
    return {
        "metrics": metrics,
        "output": {**output, "study": config["study"], "as_of": fixture["as_of"]},
        "review": review,
        "data": {"kind": "synthetic", "source": "临床运营项目合成快照",
                 "path": "verticals/pharma/data/operations.json", "as_of": fixture["as_of"]},
    }
