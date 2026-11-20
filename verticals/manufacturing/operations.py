"""Decision support cases for a fictional conveyor component plant."""

from collections import Counter, defaultdict
from itertools import accumulate


SCENARIOS = {
    "manufacturing-capacity-plan": {
        "title": "订单产能核算",
        "stage": "需求计划",
        "description": "Net finished stock against order demand and flag weekly line capacity gaps.",
        "prompt": "核算制造订单产能，找出本周和下周的超负荷产线",
        "aliases": "capacity plan|capacity planning|rough-cut capacity|订单产能|产能核算|产能计划",
        "columns": {"week": "计划周", "line": "产线", "required_minutes": "需求分钟",
                    "available_minutes": "可用分钟", "overload_minutes": "缺口分钟"},
    },
    "manufacturing-material-coverage": {
        "title": "物料缺口与补货",
        "stage": "采购与供应",
        "description": "Project dated material balances and suggest purchase quantities and qualified suppliers.",
        "prompt": "检查制造物料缺口，给出补货量和可按期交付的供应商",
        "aliases": "material shortage|material coverage|purchase requisition|物料缺口|物料净需求|补货量",
        "columns": {"item": "物料", "first_stockout_day": "最早缺货日", "draft_purchase_units": "建议采购量",
                    "earliest_qualified_supplier": "交期最短的合格供应商", "action": "建议"},
    },
    "manufacturing-finite-schedule": {
        "title": "有限产能排产",
        "stage": "生产执行",
        "description": "Fit released jobs into eligible machine windows after material readiness and flag late orders.",
        "prompt": "给制造订单做有限产能排产，列出将逾期和排不进去的工单",
        "aliases": "finite schedule|finite scheduling|production scheduling|有限产能排产|有限排产|生产排产|制造排程",
        "columns": {"job": "生产工单", "machine": "机台", "start_time": "开始时间", "finish_time": "结束时间", "status": "状态"},
    },
    "manufacturing-quality-disposition": {
        "title": "抽检与质量处置",
        "stage": "质量管理",
        "description": "Check dimensional samples against tolerance and hold nonconforming or incomplete lots.",
        "prompt": "按规格做制造批次抽检判定，标出需隔离和补检的批次",
        "aliases": "lot disposition|dimensional inspection|sampling disposition|批次抽检|抽检判定|质量处置|批次放行",
        "columns": {"lot": "批次", "units": "件数", "out_of_tolerance": "超差读数", "missing_samples": "待补抽样数",
                    "disposition": "处置建议"},
    },
    "manufacturing-oee-losses": {
        "title": "班次 OEE 损失分析",
        "stage": "现场改进",
        "description": "Calculate shift OEE and rank downtime and reject causes by their measured loss.",
        "prompt": "分析制造班次 OEE，找出最大的停机和废品损失",
        "aliases": "oee|shift losses|downtime pareto|停机损失|废品损失|设备综合效率",
        "columns": {"shift": "班次", "oee_pct": "OEE（%）", "downtime_minutes": "停机分钟", "reject_units": "废品数",
                    "top_downtime_cause": "最大停机原因"},
    },
    "manufacturing-shipment-trace": {
        "title": "异常批次出货追溯",
        "stage": "交付与售后",
        "description": "Trace a blocked supplier lot to finished stock, customer shipments and incomplete records.",
        "prompt": "追溯制造异常原料批次，找出厂内库存、已发客户及待查记录",
        "aliases": "lot trace|shipment trace|batch genealogy|异常批次|出货追溯|批次追溯|交付追溯",
        "columns": {"lot": "成品批次", "status": "追溯状态", "on_hand": "在库件数", "shipped": "已发件数",
                    "customers": "已发客户"},
    },
}


def _capacity_plan():
    products = {
        "CB-14": {"line": "CNC", "minutes_per_unit": 12, "finished_stock": 30},
        "CB-22": {"line": "CNC", "minutes_per_unit": 15, "finished_stock": 12},
        "SK-5": {"line": "Assembly", "minutes_per_unit": 9, "finished_stock": 20},
    }
    orders = [
        {"id": "SO-41", "product": "CB-14", "due_week": 1, "units": 125},
        {"id": "SO-43", "product": "CB-22", "due_week": 1, "units": 100},
        {"id": "SO-44", "product": "SK-5", "due_week": 1, "units": 85},
        {"id": "SO-45", "product": "CB-14", "due_week": 2, "units": 100},
        {"id": "SO-48", "product": "CB-22", "due_week": 2, "units": 70},
        {"id": "SO-49", "product": "SK-5", "due_week": 2, "units": 90},
    ]
    capacity = {(1, "CNC"): 2160, (1, "Assembly"): 960, (2, "CNC"): 2400, (2, "Assembly"): 960}
    stock = {sku: product["finished_stock"] for sku, product in products.items()}
    grouped = defaultdict(list)
    for order in sorted(orders, key=lambda row: (row["due_week"], row["id"])):
        sku = order["product"]
        used = min(stock[sku], order["units"])
        stock[sku] -= used
        net = order["units"] - used
        product = products[sku]
        grouped[order["due_week"], product["line"]].append(dict(
            order_id=order["id"], product=sku, units=order["units"], stock_used=used,
            units_to_make=net, required_minutes=net * product["minutes_per_unit"],
        ))
    records = []
    for (week, line), available in capacity.items():
        demands = grouped[week, line]
        used = sum(order["required_minutes"] for order in demands)
        records.append(dict(week=week, line=line, demand_orders=[o["order_id"] for o in demands],
                            required_minutes=used, available_minutes=available,
                            utilization_pct=round(100 * used / available, 1),
                            overload_minutes=max(0, used - available)))
    return {
        "metrics": {"customer_orders": len(orders), "overloaded_line_weeks": sum(r["overload_minutes"] > 0 for r in records),
                    "uncovered_minutes": sum(r["overload_minutes"] for r in records)},
        "output": {"records": records, "order_netting": [o for rows in grouped.values() for o in rows],
                   "standard_times_and_open_stock": products},
        "review": "计划员复核产线标准工时和在手成品，再决定是否协调加班、转线或调整交期。周桶负荷不含换型和设备故障。",
    }


def _material_coverage():
    materials = [
        {"item": "Steel blank", "opening": 80, "safety": 20, "lot_multiple": 50,
         "demand": [(2, 70), (5, 120), (7, 30)], "receipts": [("PO-380", 4, 60)],
         "suppliers": [("SUP-N", True, 2), ("SUP-W", True, 6), ("SUP-H", False, 1)]},
        {"item": "Fastener kit", "opening": 140, "safety": 30, "lot_multiple": 25,
         "demand": [(2, 80), (4, 75)], "receipts": [("PO-394", 5, 50)],
         "suppliers": [("SUP-Z", True, 7), ("SUP-H", False, 2)]},
        {"item": "Bearing", "opening": 100, "safety": 15, "lot_multiple": 10,
         "demand": [(2, 30), (7, 45)], "receipts": [("PO-401", 3, 30)],
         "suppliers": [("SUP-Y", True, 4)]},
    ]
    records = []
    ledgers = {}
    for item in materials:
        days = set(day for day, _ in item["demand"]) | {day for _, day, _ in item["receipts"]}
        movements = []
        balance = item["opening"]
        for day in sorted(days):
            demand = sum(units for due, units in item["demand"] if due == day)
            receipt = sum(units for _, due, units in item["receipts"] if due == day)
            balance += receipt - demand
            movements.append(dict(day=day, demand=demand, confirmed_receipt=receipt, projected_balance=balance))
        ledgers[item["item"]] = movements
        first_breach = next((m["day"] for m in movements if m["projected_balance"] < item["safety"]), None)
        first_stockout = next((m["day"] for m in movements if m["projected_balance"] < 0), None)
        gap = max(0, item["safety"] - min(m["projected_balance"] for m in movements))
        multiple = item["lot_multiple"]
        draft = ((gap + multiple - 1) // multiple) * multiple
        qualified = [(lead, sid) for sid, active, lead in item["suppliers"] if active]
        lead, supplier = min(qualified) if qualified and draft else (None, None)
        action = "covered"
        if draft:
            action = "draft purchase" if lead is not None and lead <= first_breach else "expedite review"
        records.append(dict(item=item["item"], first_below_safety_day=first_breach,
                            first_stockout_day=first_stockout, gap_to_safety_units=gap, draft_purchase_units=draft,
                            earliest_qualified_supplier=supplier, earliest_arrival_day=lead, action=action))
    return {
        "metrics": {"materials": len(records), "stockout_items": sum(r["first_stockout_day"] is not None for r in records),
                    "expedite_items": sum(r["action"] == "expedite review" for r in records)},
        "output": {"records": records, "projected_balances_without_new_purchases": ledgers,
                   "supplier_and_material_inputs": materials,
                   "input_fields": {"demand": ["need_day", "units"], "receipts": ["purchase_order", "arrival_day", "units"],
                                    "suppliers": ["supplier_id", "qualified", "lead_days"]},
                   "assumption": "Day 0 is the planning date. Same-day confirmed receipts are available before issues."},
        "review": "采购员确认供应商实时交期、现有采购单和安全库存口径。需要催交的物料保留现有缺口，不视为已补货。",
    }


def _reserve(windows, index, start, finish):
    low, high = windows[index]
    remaining = [(a, b) for a, b in ((low, start), (finish, high)) if a < b]
    windows[index:index + 1] = remaining


def _clock(minutes):
    hour, minute = divmod(minutes, 60)
    return f"{hour:02d}:{minute:02d}"


def _finite_schedule():
    machine_windows = {"CNC-A": [(480, 660), (720, 960)], "CNC-B": [(480, 600), (660, 960)],
                       "Assembly-1": [(480, 720), (780, 960)]}
    jobs = [
        {"job": "MO-41", "order": "SO-41", "machines": ["CNC-A", "CNC-B"], "ready": 510, "due": 660, "duration": 110},
        {"job": "MO-43", "order": "SO-43", "machines": ["CNC-A"], "ready": 540, "due": 740, "duration": 150},
        {"job": "MO-44", "order": "SO-44", "machines": ["Assembly-1"], "ready": 540, "due": 720, "duration": 130},
        {"job": "MO-45", "order": "SO-45", "machines": ["CNC-A", "CNC-B"], "ready": 690, "due": 900, "duration": 195},
        {"job": "MO-48", "order": "SO-48", "machines": ["CNC-A", "CNC-B"], "ready": 855, "due": 960, "duration": 125},
        {"job": "MO-49", "order": "SO-49", "machines": ["Assembly-1"], "ready": 585, "due": 955, "duration": 100},
    ]
    available = {machine: list(windows) for machine, windows in machine_windows.items()}
    records = []
    for job in sorted(jobs, key=lambda row: (row["due"], row["job"])):
        options = []
        for machine in job["machines"]:
            for index, (low, high) in enumerate(available[machine]):
                start = max(low, job["ready"])
                finish = start + job["duration"]
                if finish <= high:
                    options.append((finish, start, machine, index))
        if not options:
            records.append(dict(job=job["job"], order=job["order"], status="unscheduled", due_minute=job["due"],
                                reason="No contiguous eligible window after material readiness."))
            continue
        finish, start, machine, index = min(options)
        _reserve(available[machine], index, start, finish)
        records.append(dict(job=job["job"], order=job["order"], machine=machine, start_minute=start, finish_minute=finish,
                            start_time=_clock(start), finish_time=_clock(finish),
                            due_minute=job["due"], late_minutes=max(0, finish - job["due"]),
                            status="late" if finish > job["due"] else "on time"))
    return {
        "metrics": {"jobs": len(records), "on_time_jobs": sum(r["status"] == "on time" for r in records),
                    "late_jobs": sum(r["status"] == "late" for r in records),
                    "unscheduled_jobs": sum(r["status"] == "unscheduled" for r in records)},
        "output": {"records": records, "job_constraints": jobs, "machine_windows": machine_windows,
                   "method": "Earliest due date first, earliest feasible finish on an eligible machine. Times are minutes after midnight."},
        "review": "调度员核对换型、检具和人员班次。未排入的工单需协调物料或下一工作日的窗口。",
    }


def _quality_disposition():
    lots = [
        {"lot": "FG-501", "units": 120, "readings_mm": [19.97, 20.02, 20.01, 19.99, 20.00]},
        {"lot": "FG-502", "units": 100, "readings_mm": [20.02, 20.04, 20.08, 20.04, 20.01]},
        {"lot": "FG-503", "units": 72, "readings_mm": [19.97, 20.02, 19.99]},
        {"lot": "FG-505", "units": 60, "readings_mm": [19.95, 20.05, 20.03, 19.98, 20.00]},
    ]
    lower, upper, required = 19.95, 20.05, 5
    records = []
    for lot in lots:
        readings = lot["readings_mm"]
        failures = [dict(sample=i, value_mm=reading) for i, reading in enumerate(readings, 1) if not lower <= reading <= upper]
        disposition = "release review"
        if failures:
            disposition = "quarantine review"
        elif len(readings) < required:
            disposition = "sample again"
        records.append({**lot, "disposition": disposition, "out_of_tolerance": failures,
                        "missing_samples": max(0, required - len(readings))})
    return {
        "metrics": {"lots": len(records), "out_of_tolerance_lots": sum(bool(r["out_of_tolerance"]) for r in records),
                    "units_pending_review": sum(r["units"] for r in records if r["disposition"] != "release review")},
        "output": {"records": records, "criterion": {"minimum_mm": lower, "maximum_mm": upper, "required_samples": required},
                   "inspection": "Conveyor bracket bore diameter, drawing revision B"},
        "review": "质量工程师核对图纸版本和量具校准。判定仅作批次处置建议，超差批次与未完成抽检的批次都要复核。",
    }


def _pareto(totals, unit):
    values = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    total = sum(totals.values())
    return [dict(cause=cause, **{unit: loss}, cumulative_pct=round(100 * cumulative / total, 1))
            for (cause, loss), cumulative in zip(values, accumulate(loss for _, loss in values))]


def _oee_losses():
    shifts = [
        {"shift": "CNC-A / day", "planned_minutes": 420, "ideal_cycle_seconds": 75, "total_units": 267,
         "downtime_by_cause": {"Tool change": 32, "Fixture adjustment": 24, "Waiting for material": 14},
         "rejects_by_cause": {"Burr": 9, "Bore out of tolerance": 7}},
        {"shift": "CNC-A / evening", "planned_minutes": 420, "ideal_cycle_seconds": 75, "total_units": 286,
         "downtime_by_cause": {"Tool change": 22, "Fixture adjustment": 12, "Waiting for material": 25},
         "rejects_by_cause": {"Burr": 4, "Bore out of tolerance": 6}},
        {"shift": "CNC-B / day", "planned_minutes": 390, "ideal_cycle_seconds": 70, "total_units": 289,
         "downtime_by_cause": {"Tool change": 15, "Waiting for material": 20, "Gauge check": 10},
         "rejects_by_cause": {"Burr": 7, "Bore out of tolerance": 3}},
    ]
    records = []
    downtime, rejects = Counter(), Counter()
    total_good_time = 0
    for shift in shifts:
        downtime.update(shift["downtime_by_cause"])
        rejects.update(shift["rejects_by_cause"])
        planned = shift["planned_minutes"]
        lost = sum(shift["downtime_by_cause"].values())
        running = planned - lost
        total = shift["total_units"]
        good = total - sum(shift["rejects_by_cause"].values())
        cycle = shift["ideal_cycle_seconds"]
        good_time = good * cycle
        total_good_time += good_time
        records.append(dict(shift=shift["shift"], downtime_minutes=lost, good_units=good, reject_units=total - good,
                            top_downtime_cause=max(shift["downtime_by_cause"], key=shift["downtime_by_cause"].get),
                            availability_pct=round(100 * running / planned, 1),
                            performance_pct=round(100 * cycle * total / (60 * running), 1),
                            quality_pct=round(100 * good / total, 1),
                            oee_pct=round(100 * good_time / (60 * planned), 1)))
    planned_total = sum(r["planned_minutes"] for r in shifts)
    return {
        "metrics": {"shifts": len(records), "weighted_oee_pct": round(100 * total_good_time / (60 * planned_total), 1),
                    "downtime_minutes": downtime.total(), "reject_units": rejects.total()},
        "output": {"records": records, "downtime_pareto": _pareto(downtime, "lost_minutes"),
                   "reject_pareto": _pareto(rejects, "rejected_units"), "shift_evidence": shifts},
        "review": "班组长核对停机原因是否重复计时、工序的标准节拍是否有效，再分派损失最大的改善项。",
    }


def _shipment_trace():
    blocked = "STEEL-240C"
    lots = [
        {"lot": "FG-501", "input_lots": ["STEEL-240C", "FAST-95"], "units": 120, "on_hand": 40},
        {"lot": "FG-502", "input_lots": ["STEEL-240C", "FAST-98"], "units": 100, "on_hand": 100},
        {"lot": "FG-503", "input_lots": None, "units": 72, "on_hand": 52},
        {"lot": "FG-505", "input_lots": ["STEEL-241B", "FAST-95"], "units": 60, "on_hand": 30},
    ]
    shipments = [
        {"shipment": "SHP-71", "lot": "FG-501", "order": "SO-41", "customer": "Customer-A", "units": 60},
        {"shipment": "SHP-72", "lot": "FG-501", "order": "SO-45", "customer": "Customer-B", "units": 20},
        {"shipment": "SHP-73", "lot": "FG-503", "order": "SO-48", "customer": "Customer-C", "units": 20},
        {"shipment": "SHP-74", "lot": "FG-505", "order": "SO-49", "customer": "Customer-B", "units": 30},
    ]
    records = []
    for lot in lots:
        matches = [shipment for shipment in shipments if shipment["lot"] == lot["lot"]]
        shipped = sum(shipment["units"] for shipment in matches)
        status = "other supplier lot"
        if lot["input_lots"] is None:
            status = "genealogy missing"
        elif blocked in lot["input_lots"]:
            status = "affected"
        records.append(dict(lot=lot["lot"], status=status, input_lots=lot["input_lots"], on_hand=lot["on_hand"],
                            shipped=shipped, shipments=[s["shipment"] for s in matches],
                            customers=sorted({s["customer"] for s in matches}),
                            unreconciled_units=lot["units"] - lot["on_hand"] - shipped))
    affected = [row for row in records if row["status"] == "affected"]
    return {
        "metrics": {"affected_lots": len(affected), "affected_units_in_stock": sum(r["on_hand"] for r in affected),
                    "affected_units_shipped": sum(r["shipped"] for r in affected),
                    "lots_with_missing_genealogy": sum(r["status"] == "genealogy missing" for r in records)},
        "output": {"records": records, "blocked_supplier_lot": blocked, "shipment_records": shipments,
                   "finished_lot_records": lots},
        "review": "质量与物流负责人核对在库数量和缺失谱系，再决定库存冻结、客户通知和追溯范围。",
    }


_RUNNERS = {
    "manufacturing-capacity-plan": _capacity_plan,
    "manufacturing-material-coverage": _material_coverage,
    "manufacturing-finite-schedule": _finite_schedule,
    "manufacturing-quality-disposition": _quality_disposition,
    "manufacturing-oee-losses": _oee_losses,
    "manufacturing-shipment-trace": _shipment_trace,
}


def run(tool_id):
    report = _RUNNERS[tool_id]()
    report["data"] = {"kind": "synthetic", "source": "Conveyor component plant operations fixtures",
                      "fixture": "conveyor-components-v1"}
    return report
