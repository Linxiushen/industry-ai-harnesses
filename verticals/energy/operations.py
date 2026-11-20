"""Auditable energy business decisions using fictional offline inputs."""

from decimal import Decimal, ROUND_HALF_UP
from statistics import mean


SCENARIOS = {
    "energy-solar-screening": {
        "title": "光伏项目初筛",
        "stage": "项目开发",
        "description": "Compare rooftop PV sizes against self-consumption, installation budget and simple payback.",
        "prompt": "筛选适合办公园区的光伏项目容量",
        "aliases": "光伏|屋顶太阳能|solar screening|rooftop pv|pv sizing",
        "columns": {"size_kw": "装机容量（kW）", "annual_self_used_kwh": "年自用光伏（kWh）",
                    "annual_net_savings_usd": "年净节省（USD）", "simple_payback_years": "回收期（年）",
                    "passes_screen": "通过初筛"},
    },
    "energy-storage-economics": {
        "title": "储能收益评估",
        "stage": "投资评估",
        "description": "Compare hypothetical battery configurations using tariff spreads, energy losses and wear costs.",
        "prompt": "比较三种储能方案的收益和回收期",
        "aliases": "储能|电池收益|battery economics|storage economics|battery investment",
        "columns": {"usable_capacity_kwh": "可用容量（kWh）", "delivered_kwh_per_cycle": "单次送出（kWh）",
                    "annual_net_arbitrage_usd": "年净收益（USD）", "simple_payback_years": "回收期（年）",
                    "passes_screen": "通过初筛"},
    },
    "energy-demand-response": {
        "title": "需求响应核验",
        "stage": "灵活性市场",
        "description": "Verify metered demand response against matched-day baselines and flag incomplete settlement evidence.",
        "prompt": "核验需求响应事件并计算待复核结算金额",
        "aliases": "需求响应|响应结算|demand response|baseline settlement|response verification",
        "columns": {"event_id": "事件", "status": "核验状态", "net_reduction_kwh": "净削减量（kWh）",
                    "provisional_value_usd": "暂估金额（USD）"},
    },
    "energy-reliability-report": {
        "title": "供电可靠性复盘",
        "stage": "服务质量",
        "description": "Aggregate fictional completed service interruptions and track unresolved records separately.",
        "prompt": "复盘历史停电并汇总供电可靠性指标",
        "aliases": "可靠性|停电复盘|停电统计|reliability report|outage recap|saidi|saifi",
        "columns": {"district": "区域", "completed_events": "已结事件", "unresolved_events": "缺时长事件",
                    "saidi_minutes_per_customer": "户均停电分钟", "saifi_interruptions_per_customer": "户均停电次数"},
    },
    "energy-bill-audit": {
        "title": "电费账单对账",
        "stage": "客户结算",
        "description": "Recalculate billed energy and demand charges from matching tariff and meter records.",
        "prompt": "按电表和费率核对三份电费账单",
        "aliases": "电费|账单对账|电费对账|bill audit|bill reconciliation|tariff check",
        "columns": {"account_id": "账户", "charge": "费项", "billed_usd": "账单金额（USD）",
                    "expected_usd": "复算金额（USD）", "billed_minus_expected_usd": "差额（USD）", "status": "对账状态"},
    },
    "energy-carbon-inventory": {
        "title": "购电碳排核算",
        "stage": "可持续披露",
        "description": "Calculate location-based electricity emissions and disclose unmatched emissions factors.",
        "prompt": "用区域排放因子核算购电碳排并列出缺口",
        "aliases": "碳排|范围二|购电碳核算|carbon inventory|scope 2|emissions factors",
        "columns": {"site": "场所", "purchased_mwh": "购电量（MWh）", "factor_kgco2e_per_kwh": "碳因子（kgCO₂e/kWh）",
                    "emissions_tco2e": "购电排放（tCO₂e）", "status": "核算状态"},
    },
}


def _result(metrics, records, inputs, review):
    return {"metrics": metrics, "output": {"records": records, "inputs": inputs}, "review": review}


def _solar_screening():
    # Each interval is a multi-hour energy total on one representative day.
    representative_days = [
        {"season": "summer", "days": 122, "load_kwh": [190, 325, 200], "pv_kwh_per_kw": [1.2, 3.2, 1.0]},
        {"season": "shoulder", "days": 151, "load_kwh": [140, 260, 160], "pv_kwh_per_kw": [0.8, 2.5, 0.7]},
        {"season": "winter", "days": 92, "load_kwh": [155, 255, 175], "pv_kwh_per_kw": [0.4, 1.5, 0.4]},
    ]
    sizes_kw = [50, 100, 150, 200]
    roof_limit_kw = 180
    capex_budget_usd = 200_000
    capex_usd_per_kw = 1100
    maintenance_usd_per_kw_year = 15
    import_usd_per_kwh = [0.13, 0.24, 0.17]
    export_usd_per_kwh = 0.055
    max_payback_years = 10
    records = []
    for size_kw in sizes_kw:
        generation_kwh = self_used_kwh = avoided_cost_usd = 0.0
        for day in representative_days:
            for load, yield_per_kw, rate in zip(day["load_kwh"], day["pv_kwh_per_kw"], import_usd_per_kwh):
                generated = size_kw * yield_per_kw
                self_used = min(generated, load)
                generation_kwh += generated * day["days"]
                self_used_kwh += self_used * day["days"]
                avoided_cost_usd += self_used * rate * day["days"]
        export_kwh = generation_kwh - self_used_kwh
        capex_usd = size_kw * capex_usd_per_kw
        operating_savings_usd = avoided_cost_usd + export_kwh * export_usd_per_kwh - size_kw * maintenance_usd_per_kw_year
        payback = capex_usd / operating_savings_usd if operating_savings_usd > 0 else None
        passes = (size_kw <= roof_limit_kw and capex_usd <= capex_budget_usd
                  and payback is not None and payback <= max_payback_years)
        records.append({"size_kw": size_kw, "annual_generation_kwh": round(generation_kwh, 1),
                        "annual_self_used_kwh": round(self_used_kwh, 1), "annual_export_kwh": round(export_kwh, 1),
                        "capex_usd": capex_usd, "annual_net_savings_usd": round(operating_savings_usd, 2),
                        "simple_payback_years": round(payback, 2) if payback is not None else None,
                        "passes_screen": passes})
    passing = [row for row in records if row["passes_screen"]]
    selected = max(passing, key=lambda row: row["annual_net_savings_usd"], default=None)
    return _result(
        {"candidate_sizes": len(records), "passing_sizes": len(passing),
         "selected_size_kw": selected["size_kw"] if selected else None,
         "selected_annual_net_savings_usd": selected["annual_net_savings_usd"] if selected else None},
        records,
        {"intervals": ["morning", "midday", "late afternoon"], "representative_days": representative_days,
         "roof_limit_kw": roof_limit_kw, "capex_budget_usd": capex_budget_usd, "capex_usd_per_kw": capex_usd_per_kw,
         "import_usd_per_kwh": import_usd_per_kwh, "export_usd_per_kwh": export_usd_per_kwh,
         "maintenance_usd_per_kw_year": maintenance_usd_per_kw_year, "max_payback_years": max_payback_years},
        "核查实际屋顶可用面积、分时用电和并网价格。代表日估算未计入融资、税费和组件衰减。",
    )


def _storage_economics():
    options = [(100, 50, 32_000), (200, 80, 58_000), (400, 100, 106_000)]
    charge_hours = 4
    discharge_hours = 2
    on_peak_site_load_kw = 65
    charge_site_headroom_kw = 40
    off_peak_usd_per_kwh = 0.09
    on_peak_usd_per_kwh = 0.33
    wear_usd_per_kwh = 0.035
    round_trip_efficiency = 0.88
    duty_days_per_year = 250
    max_payback_years = 10
    records = []
    for usable_kwh, power_kw, capex_usd in options:
        delivery_kwh = min(usable_kwh, discharge_hours * min(power_kw, on_peak_site_load_kw),
                           charge_hours * min(power_kw, charge_site_headroom_kw) * round_trip_efficiency)
        charge_kwh = delivery_kwh / round_trip_efficiency
        net_cycle_value = delivery_kwh * (on_peak_usd_per_kwh - wear_usd_per_kwh) - charge_kwh * off_peak_usd_per_kwh
        economic_cycles = duty_days_per_year if net_cycle_value > 0 else 0
        annual_value = net_cycle_value * economic_cycles
        payback = capex_usd / annual_value if annual_value > 0 else None
        records.append({"usable_capacity_kwh": usable_kwh, "power_kw": power_kw, "capex_usd": capex_usd,
                        "charge_kwh_per_cycle": round(charge_kwh, 2), "delivered_kwh_per_cycle": round(delivery_kwh, 2),
                        "loss_kwh_per_cycle": round(charge_kwh - delivery_kwh, 2), "economic_cycles_per_year": economic_cycles,
                        "annual_net_arbitrage_usd": round(annual_value, 2),
                        "simple_payback_years": round(payback, 2) if payback is not None else None,
                        "passes_screen": payback is not None and payback <= max_payback_years})
    passing = [row for row in records if row["passes_screen"]]
    return _result(
        {"configurations": len(records), "passing_configurations": len(passing),
         "highest_annual_net_arbitrage_usd": max(row["annual_net_arbitrage_usd"] for row in records)},
        records,
        {"round_trip_efficiency": round_trip_efficiency, "charge_hours": charge_hours, "discharge_hours": discharge_hours,
         "charge_site_headroom_kw": charge_site_headroom_kw, "on_peak_site_load_kw": on_peak_site_load_kw,
         "off_peak_usd_per_kwh": off_peak_usd_per_kwh, "on_peak_usd_per_kwh": on_peak_usd_per_kwh,
         "wear_usd_per_kwh_delivered": wear_usd_per_kwh, "duty_days_per_year": duty_days_per_year,
         "max_payback_years": max_payback_years},
        "复核并网限制、实际电价与设备质保。此初筛只计电价套利，供投资人员比较方案。",
    )


def _demand_response():
    events = [
        {"id": "DR-01", "matched_days_kw": [[104, 110], [108, 112], [112, 108]], "event_meter_kw": [83, 89]},
        {"id": "DR-02", "matched_days_kw": [[105, 90], [110, 100], [115, 110]], "event_meter_kw": [86, 110]},
        {"id": "DR-03", "matched_days_kw": [[90, 104], [95, 110], [100, 116]], "event_meter_kw": [73, None]},
    ]
    minimum_avg_reduction_kw = 15
    settlement_usd_per_kwh = 0.35
    interval_hours = 1
    records = []
    for event in events:
        baseline_kw = [mean(samples) for samples in zip(*event["matched_days_kw"])]
        meter_kw = event["event_meter_kw"]
        if any(value is None for value in meter_kw):
            records.append({"event_id": event["id"], "status": "hold_missing_meter", "baseline_kw": baseline_kw,
                            "observed_kw": meter_kw, "net_reduction_kwh": None, "provisional_value_usd": None})
            continue
        reductions_kw = [baseline - observed for baseline, observed in zip(baseline_kw, meter_kw)]
        reduction_kwh = sum(reductions_kw) * interval_hours
        qualifies = mean(reductions_kw) >= minimum_avg_reduction_kw
        records.append({"event_id": event["id"], "status": "qualifies" if qualifies else "below_threshold",
                        "baseline_kw": baseline_kw, "observed_kw": meter_kw, "net_reduction_kwh": round(reduction_kwh, 2),
                        "provisional_value_usd": round(reduction_kwh * settlement_usd_per_kwh, 2) if qualifies else 0})
    return _result(
        {"verified_events": sum(row["status"] != "hold_missing_meter" for row in records),
         "qualifying_events": sum(row["status"] == "qualifies" for row in records),
         "held_events": sum(row["status"] == "hold_missing_meter" for row in records),
         "provisional_value_usd": round(sum(row["provisional_value_usd"] or 0 for row in records), 2)},
        records,
        {"events": events, "interval_hours": interval_hours, "minimum_avg_reduction_kw": minimum_avg_reduction_kw,
         "settlement_usd_per_kwh": settlement_usd_per_kwh, "baseline_method": "arithmetic mean of three matched days"},
        "确认对照日资格、仪表完整性和项目规则。时段内增加的负荷抵扣其他时段的节电量，缺读数的事件暂缓结算。",
    )


def _reliability_report():
    service_counts = {"District A": 4000, "District B": 2500, "District C": 3500}
    events = [
        {"district": "District A", "customers_interrupted": 120, "duration_minutes": 40},
        {"district": "District A", "customers_interrupted": 55, "duration_minutes": 70},
        {"district": "District B", "customers_interrupted": 250, "duration_minutes": 95},
        {"district": "District C", "customers_interrupted": 150, "duration_minutes": None},
    ]
    records = []
    for district, served in service_counts.items():
        local_events = [event for event in events if event["district"] == district]
        completed = [event for event in local_events if event["duration_minutes"] is not None]
        interruptions = sum(event["customers_interrupted"] for event in completed)
        customer_minutes = sum(event["customers_interrupted"] * event["duration_minutes"] for event in completed)
        records.append({"district": district, "customers_served": served, "completed_events": len(completed),
                        "unresolved_events": len(local_events) - len(completed), "customer_interruptions": interruptions,
                        "customer_minutes_interrupted": customer_minutes, "saidi_minutes_per_customer": round(customer_minutes / served, 4),
                        "saifi_interruptions_per_customer": round(interruptions / served, 4)})
    customers_served = sum(service_counts.values())
    interruptions = sum(row["customer_interruptions"] for row in records)
    customer_minutes = sum(row["customer_minutes_interrupted"] for row in records)
    return _result(
        {"completed_events": sum(row["completed_events"] for row in records),
         "unresolved_events": sum(row["unresolved_events"] for row in records),
         "saidi_minutes_per_customer": round(customer_minutes / customers_served, 4),
         "saifi_interruptions_per_customer": round(interruptions / customers_served, 4),
         "caidi_minutes_per_interruption": round(customer_minutes / interruptions, 2) if interruptions else None},
        records,
        {"period": "2026-08", "customers_served_by_district": service_counts, "events": events,
         "scope": "completed sustained interruption records with a common duration per event"},
        "未补齐恢复时长的事件暂不计入口径分子。存在待补记录的地区指标是当前下界，须复核事件拆分、恢复记录和本地报送规则。",
    )


def _bill_audit():
    rates = {"peak_energy": "0.24", "off_peak_energy": "0.11", "demand": "12.50"}
    accounts = [
        {"id": "ACC-01", "meter": [1120, 2400, 42], "invoice": ["268.80", "264.00", "525.00"]},
        {"id": "ACC-02", "meter": [1500, 3000, 48], "invoice": ["380.00", "330.00", "580.00"]},
        {"id": "ACC-03", "meter": [810, 1800, None], "invoice": ["194.40", "198.00", "437.50"]},
    ]
    tolerance = Decimal("0.01")
    records = []
    absolute_exception_usd = Decimal(0)
    for account in accounts:
        for (charge, rate_str), measured, invoice_str in zip(rates.items(), account["meter"], account["invoice"]):
            rate = Decimal(rate_str)
            billed = Decimal(invoice_str)
            expected = ((Decimal(measured) * rate).quantize(tolerance, rounding=ROUND_HALF_UP)
                        if measured is not None else None)
            variance = billed - expected if expected is not None else None
            status = "matched"
            if variance is None:
                status = "hold_missing_meter"
            elif abs(variance) > tolerance:
                status = "variance"
                absolute_exception_usd += abs(variance)
            records.append({"account_id": account["id"], "charge": charge, "meter_quantity": measured,
                            "unit": "kW" if charge == "demand" else "kWh", "rate_usd_per_unit": float(rate),
                            "billed_usd": float(billed), "expected_usd": float(expected) if expected is not None else None,
                            "billed_minus_expected_usd": float(variance) if variance is not None else None, "status": status})
    return _result(
        {"invoices": len(accounts), "variance_lines": sum(row["status"] == "variance" for row in records),
         "held_lines": sum(row["status"] == "hold_missing_meter" for row in records),
         "absolute_exception_usd": float(absolute_exception_usd)},
        records,
        {"statement_period": "2026-08", "tariff_revision": "DEMO-TOU-2026-08", "variance_tolerance_usd": float(tolerance),
         "rates_usd_per_unit": rates, "meter_and_invoice_records": accounts},
        "按明细追查相互抵销的差异。待补的需量读数复核后再结算，示例仅包含电量和需量两类费用。",
    )


def _carbon_inventory():
    meter_rows = [
        {"site": "Office A", "period": "2026-08", "region": "Zone 1", "purchased_mwh": 44.8},
        {"site": "Office B", "period": "2026-08", "region": "Zone 2", "purchased_mwh": 67.2},
        {"site": "Office C", "period": "2026-08", "region": "Zone 3", "purchased_mwh": 35.0},
    ]
    factors = {("2026-08", "Zone 1"): 0.38, ("2026-08", "Zone 2"): 0.52, ("2026-07", "Zone 3"): 0.43}
    records = []
    for row in meter_rows:
        factor = factors.get((row["period"], row["region"]))
        emissions = round(row["purchased_mwh"] * factor, 4) if factor is not None else None
        records.append({**row, "factor_kgco2e_per_kwh": factor, "emissions_tco2e": emissions,
                        "status": "calculated" if factor is not None else "hold_missing_period_factor"})
    purchased_mwh = sum(row["purchased_mwh"] for row in records)
    covered = [row for row in records if row["emissions_tco2e"] is not None]
    covered_mwh = sum(row["purchased_mwh"] for row in covered)
    return _result(
        {"purchased_mwh": round(purchased_mwh, 3), "covered_mwh": round(covered_mwh, 3),
         "coverage_percent": round(100 * covered_mwh / purchased_mwh, 2),
         "covered_emissions_tco2e": round(sum(row["emissions_tco2e"] for row in covered), 4),
         "sites_missing_factors": len(records) - len(covered)},
        records,
        {"method": "Scope 2 location-based illustration", "factor_version": "DEMO-2026-v1",
         "factors": [{"period": period, "region": region, "kgco2e_per_kwh": factor}
                     for (period, region), factor in factors.items()]},
        "为缺失月份补齐同区排放因子并核对购电量来源。当前排放合计只覆盖已匹配用电量，保留覆盖率供披露复核。",
    )


_HANDLERS = {
    "energy-solar-screening": _solar_screening,
    "energy-storage-economics": _storage_economics,
    "energy-demand-response": _demand_response,
    "energy-reliability-report": _reliability_report,
    "energy-bill-audit": _bill_audit,
    "energy-carbon-inventory": _carbon_inventory,
}


def run(tool_id):
    result = _HANDLERS[tool_id]()
    result["data"] = {"kind": "synthetic", "source": "Fictional energy operations fixtures",
                      "suite": "energy-operations-v1", "fixture_id": tool_id}
    return result
