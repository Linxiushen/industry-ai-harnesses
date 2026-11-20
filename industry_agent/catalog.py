"""The public scenario library, shared by the agent and the browser build."""
from verticals.energy import operations as energy
from verticals.manufacturing import operations as manufacturing
from verticals.pharma import operations as pharma


OPERATIONS = {"pharma": pharma, "manufacturing": manufacturing, "energy": energy}
ADDITIONAL = {tool: (domain, scenario) for domain, module in OPERATIONS.items()
              for tool, scenario in module.SCENARIOS.items()}
ORIGINAL = {
    "trial_landscape": ("pharma", "试验检索", "立项与启动", "检索 COPD 临床试验"),
    "recruiting_locations": ("pharma", "招募站点筛选", "立项与启动", "筛选美国招募站点"),
    "registry_follow_up": ("pharma", "结果登记跟进", "结题与归档", "列出需要跟进的结果登记"),
    "condition-monitoring": ("manufacturing", "故障风险排序", "设备与交付", "对制造设备做故障风险排序"),
    "inspection-queue": ("manufacturing", "限额巡检", "设备与交付", "给制造设备安排限额巡检"),
    "work-order-evidence": ("manufacturing", "维修工单草稿", "设备与交付", "为制造设备生成维修工单"),
    "day-ahead-load": ("energy", "日前负荷预测", "运行与响应", "预测日前用电负荷"),
    "peak-hour-alerts": ("energy", "尖峰预警", "运行与响应", "标出电力尖峰预警时段"),
    "flexible-load-scheduling": ("energy", "可调负荷排班", "运行与响应", "安排电力可调负荷排班"),
}
STAGES = {
    "pharma": {
        "立项与启动": ("立项与启动", "试验启动"),
        "招募与试验执行": ("招募执行", "物资保障"),
        "质量与数据": ("质量监查", "数据管理"),
        "结题与归档": ("结题与归档", "项目结题"),
    },
    "manufacturing": {
        "计划与供应": ("需求计划", "采购与供应"),
        "生产与质检": ("生产执行", "质量管理"),
        "设备与效率": ("设备与交付", "现场改进"),
        "发运与追溯": ("交付与售后",),
    },
    "energy": {
        "项目与投资": ("项目开发", "投资评估"),
        "运行与响应": ("运行与响应", "灵活性市场"),
        "服务与结算": ("服务质量", "客户结算"),
        "碳排报告": ("可持续披露",),
    },
}


def entries():
    published = [dict(id=tool, domain=domain, title=title, stage=stage, prompt=prompt)
                 for tool, (domain, title, stage, prompt) in ORIGINAL.items()]
    for tool, (domain, scenario) in ADDITIONAL.items():
        item = {key: scenario[key] for key in ("title", "stage", "prompt")}
        item.update(id=tool, domain=domain, columns=scenario.get("columns", {}))
        published.append(item)
    for item in published:
        item["phase"] = next(phase for phase, stages in STAGES[item["domain"]].items()
                             if item["stage"] in stages)
    phases = {domain: {phase: index for index, phase in enumerate(stages)}
              for domain, stages in STAGES.items()}
    return sorted(published, key=lambda item: (item["domain"], phases[item["domain"]][item["phase"]]))
