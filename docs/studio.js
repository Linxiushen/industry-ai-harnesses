"use strict";

const domains = {
  pharma: "检索 CKD 临床试验，筛选招募站点，列出需要跟进的登记记录。",
  manufacturing: "按故障风险排序，安排限额巡检，并生成工单草稿。",
  energy: "预测日前负荷，标出尖峰预警时段，并安排可调负荷排班。"
};
const workspaces = {
  pharma: ["制药临床", "查询试验登记，评估站点进度，整理临床运营待办。", [
    ["trial_landscape", "检", "从历史登记记录查找相关试验"],
    ["pharma-enrollment-forecast", "趋", "估算四周入组进度和目标差距"],
    ["pharma-closeout-readiness", "档", "核对关站前的文件和未完成事项"]
  ]],
  manufacturing: ["制造运营", "检查产能、质量和交付，让每项建议都有依据。", [
    ["manufacturing-finite-schedule", "排", "按机台、物料和班次约束排产"],
    ["manufacturing-quality-disposition", "质", "查看哪些批次需要质量复核"],
    ["manufacturing-shipment-trace", "溯", "定位受影响的库存和出货记录"]
  ]],
  energy: ["能源运营", "分析负荷、项目收益和账单，定位需要复核的差异。", [
    ["day-ahead-load", "荷", "查看日前负荷曲线和预测误差"],
    ["energy-bill-audit", "账", "按费率和用量复算账单"],
    ["energy-carbon-inventory", "碳", "核算购电排放并标出数据缺口"]
  ]]
};
const industryProfiles = {
  pharma: ["PHARMA", "面向临床运营人员，覆盖试验启动、招募执行、质量监查和项目结题。"],
  manufacturing: ["MANUFACTURING", "面向生产和设备团队，串起需求、物料、排产、质量、巡检和异常追溯。"],
  energy: ["ENERGY", "面向能源运营人员，涵盖项目初筛、负荷调度、服务结算和碳排报告。"]
};
const toolNames = {
  trial_landscape: "试验检索", recruiting_locations: "招募站点筛选", registry_follow_up: "登记跟进",
  "condition-monitoring": "故障风险排序", "inspection-queue": "限额巡检", "work-order-evidence": "工单草稿",
  "day-ahead-load": "日前负荷预测", "peak-hour-alerts": "尖峰时段预警", "flexible-load-scheduling": "可调负荷排班"
};
const statusNames = {
  completed: "已完成", needs_review: "等待人工复核", needs_clarification: "需要补充任务",
  budget_exhausted: "已用完工具预算", error: "运行失败"
};
const stepNames = {
  plan: "规划", tool: "调用", observe: "观察", review: "复核", complete: "结束",
  clarify: "澄清", budget: "预算", error: "错误"
};
const sourceKinds = {
  synthetic: "合成数据", mixed: "混合来源",
  historical_registry_metadata: "历史试验登记数据", external_csv: "外部 CSV"
};
const metricNames = {
  hit_count: "检索命中数", shortlisted_study_cities: "候选试验 / 城市", manual_review: "待核记录",
  follow_ups: "跟进记录", average_precision: "平均精确率", wear_only_average_precision: "磨损基线平均精确率",
  prevalence: "故障占比", records_reviewed: "入列巡检数", failures_in_queue: "入列的已知故障",
  failures_outside_queue: "未入列的已知故障", false_alerts: "误报数", recall_at_capacity: "名额内召回率",
  wear_only_failures_at_same_capacity: "磨损基线捕获故障", draft_count: "工单草稿数",
  known_category_matches: "工单类别匹配数", queued_confirmed_failures: "队列中已知故障",
  category_accuracy_among_queued_failures: "已知故障类别命中率", mae_mw: "平均绝对误差 (MW)",
  prior_day_mae_mw: "前日基线误差 (MW)", prior_week_mae_mw: "上周基线误差 (MW)",
  test_hours: "测试小时数", true_positives: "预警命中", false_positives: "误报小时",
  missed_hours: "漏报小时", precision: "精确率", recall: "召回率", f1: "F1",
  prior_day_f1: "前日基线 F1", mean_daily_peak_mw: "排班日均峰值 (MW)",
  fixed_mean_daily_peak_mw: "固定时段日均峰值 (MW)", mean_peak_reduction_mw: "日均峰值降幅 (MW)",
  peak_worse_days: "峰值升高天数", total_incremental_energy_mwh: "新增用电量 (MWh)"
};
const previewSpecs = {
  trial_landscape: ["hits", [["id","试验"], ["conditions","相关病症"], ["score","检索得分"]]],
  recruiting_locations: ["shortlist", [["study","试验"], ["city","城市"], ["country","国家"]]],
  registry_follow_up: ["follow_up", [["study","试验"], ["days_since_primary_completion","距主要完成日（天）"]]],
  "condition-monitoring": ["highest_risk_records", [["sequence","记录号"], ["ranking_score","风险排序分"]]],
  "inspection-queue": ["batches", null],
  "work-order-evidence": ["draft_cases", [["sequence","记录号"], ["review_batch","巡检批次"], ["suggested_category","建议类别"]]],
  "day-ahead-load": ["daily_24h_forecasts", null],
  "peak-hour-alerts": ["daily_watch_hours", [["date","日期"], ["utc_hours","预警小时 (UTC)"]]],
  "flexible-load-scheduling": ["daily_schedules", [["date","日期"], ["start_hour_utc","开始 (UTC)"], ["end_hour_utc","结束 (UTC)"], ["observed_peak_mw","峰值 (MW)"]]]
};
const byId = id => document.getElementById(id);
const offlinePreview = document.body.hasAttribute("data-offline-preview");
const numeric = new Intl.NumberFormat("zh-CN", {maximumFractionDigits: 4});
const examples = new Map();
const scenarios = new Map();
const savedReports = new Map();
const drafts = new Map();
let current = "pharma";
let selected = null;
let inspectionSlots = null;
let requestedReplay = 0;
let running = false;
let batchBusy = false;
let currentRun = null;
let runView = null;
let examplesState = "loading";
const mobile = window.matchMedia("(max-width: 800px)");
let tabsSerial = 0;
const runHistory = window.createRunHistory({root: byId("history-content"), onOpen: viewStoredRun});
const runtime = window.createStudioRuntime();
const batch = window.createBatchWorkspace({
  root: byId("batch-workspace"),
  offlinePreview,
  canRun: () => !running,
  onBusyChange: busy => {
    batchBusy = busy;
    refreshRunControls();
  },
  runTask: (task, options) => runtime.run(task, options),
  loadReplay: loadScenarioReplay,
  onOpen: (report, {item, live}) => {
    requestedReplay++;
    showReport(report, live, live ? "批量运行" : undefined, live ? null : item);
    focusResult();
  }
});
const inspectionCapacity = window.createInspectionCapacity({
  root: byId("capacity-content"),
  onOpen(report) {
    requestedReplay++;
    showReport(report, false, "容量推演 · 样本回放");
    focusResult();
  },
  onPrepare: offlinePreview ? null : prepareInspectionTask
});

function element(tag, content, style) {
  const node = document.createElement(tag);
  if (content !== undefined) node.textContent = content;
  if (style) node.className = style;
  return node;
}
function describe(value) {
  if (value == null) return "未定义";
  if (typeof value === "number") return numeric.format(value);
  if (typeof value === "boolean") return value ? "是" : "否";
  if (Array.isArray(value)) return value.length ? value.map(describe).join("、") : "无";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}
function frame(title) {
  const box = element("section", undefined, "record-section");
  box.append(element("h3", title));
  return box;
}
function focusResult() {
  focusHeading("record-title");
}
function focusHeading(id) {
  const heading = byId(id);
  heading.focus({preventScroll: true});
  heading.scrollIntoView({block: "start"});
}
function showFeedback(message = "", error = false, openResult = false, linkLabel = "查看结果") {
  const node = byId("feedback");
  node.hidden = !message;
  node.dataset.error = String(error);
  node.textContent = message;
  if (openResult) {
    const link = element("a", linkLabel);
    link.href = "#record-title";
    link.addEventListener("click", event => {
      event.preventDefault();
      if (typeof openResult === "function") openResult();
      else focusResult();
    });
    node.append(" ", link);
  }
}
function makeDisclosure(caption, data) {
  const details = element("details", undefined, "raw");
  details.append(element("summary", caption));
  details.addEventListener("toggle", () => {
    if (!details.open || details.querySelector("pre")) return;
    const pre = element("pre", JSON.stringify(data, null, 2) ?? "null");
    pre.tabIndex = 0;
    details.append(pre);
  });
  return details;
}
function preview(id, output) {
  const columns = scenarios.get(id)?.columns;
  const sample = output?.records?.[0];
  const grid = columns && Object.keys(columns).length ? Object.entries(columns) :
    Object.keys(sample ?? {}).slice(0, 5).map(key => [key, key.replaceAll("_", " ")]);
  const spec = previewSpecs[id] ?? (Array.isArray(output?.records) && ["records", grid]);
  if (!spec || !output || !Array.isArray(output[spec[0]])) return null;
  const rows = output[spec[0]];
  let fields = spec[1];
  if (id === "inspection-queue") {
    fields = [
      {key: "batch", label: "批次", value: (_, index) => index + 1},
      {key: "records", label: "安排巡检的记录号", value: row => row}
    ];
  } else if (id === "day-ahead-load") {
    fields = [["date", "日期"], ...Array.from({length: 24}, (_, hour) => {
      const clock = String(hour).padStart(2, "0") + ":00";
      return {key: clock, label: clock + " (MW)", value: row => row?.forecast_mw?.[hour]};
    })];
  }
  if (!fields?.length && !rows.length) return element("p", "本次没有符合条件的条目。", "empty");
  return window.createResultTable({
    rows, columns: fields,
    label: scenarios.get(id)?.title ?? toolNames[id] ?? id,
    format: describe,
    renderCell(value, row, column) {
      if (id === "trial_landscape" && column.key === "id" && /^NCT[0-9]{8}$/.test(value)) {
        const registryUrl = "https://clinicaltrials.gov/study/" + value;
        if (registryUrl === row?.url) {
          const link = element("a", value);
          link.href = registryUrl;
          return link;
        }
      }
      return null;
    }
  });
}
function makeTool(tool, open) {
  const detail = element("details", undefined, "tool");
  detail.open = open;
  const label = element("div");
  label.append(element("span", scenarios.get(tool.id)?.title ?? toolNames[tool.id] ?? tool.id, "tool-title"), element("code", tool.id, "tool-id"));
  const summary = element("summary");
  summary.append(label);
  detail.append(summary);
  const metrics = element("dl", undefined, "metric-grid");
  for (const [name, value] of Object.entries(tool.metrics ?? {})) {
    const metric = element("div");
    const key = element("dt", metricNames[name] ?? name.replaceAll("_", " "));
    key.title = name;
    metric.append(key, element("dd", describe(value)));
    metrics.append(metric);
  }
  detail.append(metrics);
  const table = preview(tool.id, tool.output);
  if (table) detail.append(table);
  const evidence = window.createToolEvidence(tool, describe);
  if (evidence) detail.append(evidence);
  detail.append(makeDisclosure("查看完整工具输出", tool.output));
  return detail;
}
function makeResultTabs(sections) {
  const row = element("div", undefined, "record-tabs");
  row.setAttribute("role", "tablist");
  row.setAttribute("aria-label", "结果视图");
  const serial = ++tabsSerial;
  const tabs = [];
  const panels = [];
  sections.forEach(([title, body], index) => {
    const tab = element("button", title);
    const panel = element("div", undefined, "record-panel");
    tab.type = "button";
    tab.id = `tab-${serial}-${index}`;
    panel.id = `panel-${serial}-${index}`;
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-controls", panel.id);
    panel.setAttribute("role", "tabpanel");
    panel.setAttribute("aria-labelledby", tab.id);
    panel.tabIndex = 0;
    panel.append(...body);
    tab.addEventListener("click", () => activate(index));
    tab.addEventListener("keydown", event => {
      const targets = {ArrowRight: (index + 1) % tabs.length, ArrowLeft: (index + tabs.length - 1) % tabs.length,
                       Home: 0, End: tabs.length - 1};
      if (!(event.key in targets)) return;
      event.preventDefault();
      activate(targets[event.key]);
      tabs[targets[event.key]].focus();
    });
    tabs.push(tab);
    panels.push(panel);
    row.append(tab);
  });
  function activate(selected) {
    tabs.forEach((tab, index) => {
      tab.setAttribute("aria-selected", String(index === selected));
      tab.tabIndex = index === selected ? 0 : -1;
      panels[index].hidden = index !== selected;
    });
  }
  activate(0);
  return [row, ...panels];
}
function downloadReport(report, live) {
  const link = document.createElement("a");
  const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2) + "\n"], {type: "application/json"}));
  link.href = url;
  link.download = "industry-agent-" + (domains[report.domain] ? report.domain : "run") + (live ? "-live" : "-replay") + ".json";
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function showReport(report, live, label, scenario = null) {
  const mode = byId("record-mode");
  mode.textContent = label ?? (live ? "本机实时运行" : "已保存的运行");
  mode.dataset.live = String(live);
  mode.dataset.status = report.status;
  const content = byId("record-content");
  const summary = element("div", undefined, "record-summary");
  summary.append(element("p", report.request, "request-line"));
  const tools = report.tools ?? [];
  const steps = report.steps ?? [];
  const meta = [
    workspaces[report.domain]?.[0] ?? "未匹配行业",
    statusNames[report.status] ?? report.status,
    `工具 ${tools.length} / ${report.max_tools}`,
    steps.length + " 步"
  ];
  if (report.data?.kind) meta.push(sourceKinds[report.data.kind] ?? report.data.kind);
  summary.append(element("p", meta.join("　·　"), "summary-meta"));
  content.replaceChildren(summary);
  const overview = [];
  const evidence = [];
  const trace = [];
  if (tools.length) {
    const section = frame("工具结果");
    tools.forEach((tool, index) => section.append(makeTool(tool, index === 0)));
    overview.push(section);
  }
  const review = window.createResultReview(report);
  if (review) overview.unshift(review);
  if (steps.length) {
    const section = frame("执行轨迹");
    const track = element("ol", undefined, "steps");
    for (const step of steps) {
      const li = element("li");
      li.append(element("span", stepNames[step.kind] ?? step.kind, "step-kind"), document.createTextNode(step.message ?? ""));
      track.append(li);
    }
    section.append(track);
    trace.push(section);
  }
  const source = frame("数据来源");
  const data = report.data;
  if (data && Object.keys(data).length) {
    const label = sourceKinds[data.kind] ?? data.kind;
    const description = [label, typeof data.source === "string" && data.source].filter(Boolean).join(" · ");
    if (description) source.append(element("p", description, "provenance"));
    source.append(makeDisclosure("数据来源和参数", data));
  }
  for (const tool of tools) {
    if (tool.data) source.append(makeDisclosure((scenarios.get(tool.id)?.title ?? tool.id) + " · 输入来源", tool.data));
    if (tool.output?.inputs) source.append(makeDisclosure((scenarios.get(tool.id)?.title ?? tool.id) + " · 计算输入", tool.output.inputs));
  }
  evidence.push(source);
  if (!overview.length) overview.push(element("p", "本次未生成工具结果。", "empty"));
  if (!trace.length) trace.push(element("p", "本次未记录工具步骤。", "empty"));
  content.append(...makeResultTabs([["概览", overview], ["数据依据", evidence], ["执行轨迹", trace]]));
  const actions = element("div", undefined, "record-actions");
  if (scenario) {
    const share = element("a", "场景永久链接 ↗", "scenario-link");
    const url = new URL(location.href);
    url.search = new URLSearchParams({scenario: scenario.id}).toString();
    url.hash = "record-title";
    share.href = url.href;
    actions.append(share);
    const add = element("button", "加入批量", "secondary");
    add.type = "button";
    add.addEventListener("click", () => {
      batch.addScenario(scenario.id);
      focusHeading("batch-title");
    });
    actions.append(add);
  }
  if (tools.some(tool => tool.id === "inspection-queue")) {
    const capacityLink = element("a", "巡检容量推演 ↓", "scenario-link");
    capacityLink.href = "#inspection-capacity";
    capacityLink.addEventListener("click", event => {
      event.preventDefault();
      inspectionCapacity.load();
      focusHeading("capacity-title");
    });
    actions.append(capacityLink);
  }
  const download = element("button", "下载 JSON ↓", "download");
  download.type = "button";
  download.addEventListener("click", () => downloadReport(report, live));
  actions.append(download);
  if (!live && (!label || label === "导入的运行")) {
    const save = element("button", "存入历史", "secondary");
    save.type = "button";
    save.addEventListener("click", () => {
      runHistory.save(report, label ? "import" : "replay");
      focusHeading("history-title");
    });
    actions.append(save);
  }
  content.append(actions);
  content.setAttribute("aria-busy", "false");
}
function emptyRecord(modeText, message, busy = false) {
  const mode = byId("record-mode");
  mode.textContent = modeText;
  mode.dataset.live = "false";
  delete mode.dataset.status;
  const content = byId("record-content");
  content.replaceChildren(element("p", message, "empty"));
  content.setAttribute("aria-busy", String(busy));
}
function showSaved() {
  if (selected) {
    void showScenarioReplay(selected);
    return;
  }
  const example = examples.get(current);
  byId("load-example").disabled = !example || running;
  if (example) showReport(example.report, false);
  else if (examplesState === "loading") emptyRecord("读取中", "正在读取已保存的示例。", true);
  else emptyRecord("暂无示例", "示例文件未能读取。你仍可点击「运行 Agent」执行任务。");
}
function renderScenarios() {
  const stages = byId("scenario-stages");
  const groups = new Map();
  const search = byId("scenario-search").value.trim().toLowerCase();
  for (const item of scenarios.values()) {
    if (item.domain !== current) continue;
    if (search && ![item.title, item.stage, item.phase, item.id].some(value => value.toLowerCase().includes(search))) continue;
    if (!groups.has(item.phase)) groups.set(item.phase, []);
    groups.get(item.phase).push(item);
  }
  const columns = [];
  for (const [phase, items] of groups) {
    const column = element("section", undefined, "scenario-stage");
    column.append(element("h3", phase));
    for (const item of items) {
      const button = element("button", item.title, "scenario");
      button.type = "button";
      button.dataset.scenario = item.id;
      button.setAttribute("aria-pressed", String(selected?.id === item.id));
      button.addEventListener("click", () => selectScenario(item));
      column.append(button);
    }
    columns.push(column);
  }
  stages.replaceChildren(...(columns.length ? columns : [element("p", search ? "没有匹配的场景。" : "正在读取场景。", "empty")]));
}
function renderQuickStart() {
  const cards = workspaces[current][2].flatMap(([id, mark, note]) => {
    const item = scenarios.get(id);
    if (!item) return [];
    const card = element("button", undefined, "quick-card");
    card.type = "button";
    card.dataset.quickScenario = id;
    card.setAttribute("aria-pressed", String(selected?.id === id));
    const icon = element("span", mark, "quick-icon");
    icon.setAttribute("aria-hidden", "true");
    card.append(icon, element("strong", item.title), element("span", note, "quick-note"));
    card.addEventListener("click", () => selectScenario(item));
    return [card];
  });
  byId("quick-grid").replaceChildren(...cards);
}
function openScenario(item) {
  if (current !== item.domain) {
    document.querySelector(`input[name="domain"][value="${item.domain}"]`).checked = true;
    switchDomain(item.domain);
  }
  selectScenario(item);
  focusResult();
}
function renderAtlas() {
  byId("industry-count").textContent = new Set([...scenarios.values()].map(item => item.domain)).size;
  byId("scenario-count").textContent = scenarios.size;
  const cards = [];
  for (const [domain, [label, description]] of Object.entries(industryProfiles)) {
    const items = [...scenarios.values()].filter(item => item.domain === domain);
    const groups = new Map();
    for (const item of items) {
      if (!groups.has(item.phase)) groups.set(item.phase, []);
      groups.get(item.phase).push(item);
    }
    const card = element("article", undefined, "explore-card");
    card.dataset.domain = domain;
    card.append(element("p", label, "section-kicker"), element("h3", workspaces[domain][0]), element("p", description));
    for (const [phase, choices] of groups) {
      const details = element("details", undefined, "atlas-phase");
      const summary = element("summary", phase);
      summary.append(element("span", String(choices.length)));
      const list = element("ul");
      for (const item of choices) {
        const entry = element("li");
        const action = element("button", item.title, "atlas-choice");
        action.type = "button";
        action.dataset.atlasScenario = item.id;
        action.addEventListener("click", () => openScenario(item));
        entry.append(action);
        list.append(entry);
      }
      details.append(summary, list);
      card.append(details);
    }
    cards.push(card);
  }
  byId("explore-grid").replaceChildren(...cards);
}
function renderCasebook(cases) {
  const shortcuts = [];
  const cards = [];
  for (const [index, sample] of cases.entries()) {
    const item = scenarios.get(sample.id);
    if (!item) continue;
    const entry = element("li");
    const action = element("button");
    action.type = "button";
    action.dataset.featuredScenario = sample.id;
    action.addEventListener("click", () => openScenario(item));
    const label = element("span", undefined, "hero-case-copy");
    label.append(element("strong", sample.title), element("small", sample.eyebrow));
    const arrow = element("span", "↗", "hero-case-arrow");
    arrow.setAttribute("aria-hidden", "true");
    const marker = element("span", ["临", "制", "能"][index] ?? "", "hero-case-index");
    marker.setAttribute("aria-hidden", "true");
    action.append(marker, label, arrow);
    entry.append(action);
    shortcuts.push(entry);

    const card = element("article", undefined, "explore-card case-card");
    card.dataset.domain = item.domain;
    card.append(element("p", sample.eyebrow, "section-kicker"), element("h3", sample.title), element("p", sample.question));
    card.append(element("p", sample.finding, "case-finding"), element("p", sample.caveat, "case-caveat"));
    const links = element("div", undefined, "explore-links");
    const replay = element("button", "打开回放 ↗");
    replay.type = "button";
    replay.addEventListener("click", () => openScenario(item));
    links.append(replay);
    const source = element("a", sample.source.label + " ↗");
    source.href = sample.source.url;
    links.append(source);
    card.append(links);
    cards.push(card);
  }
  byId("featured-case-list").replaceChildren(...shortcuts);
  byId("casebook-grid").replaceChildren(...cards);
}
function setDrawer(open, restoreFocus = true) {
  open = mobile.matches && open;
  document.body.dataset.drawer = open ? "open" : "closed";
  byId("drawer-overlay").hidden = !open;
  byId("sidebar").inert = mobile.matches && !open;
  byId("app-main").inert = open;
  byId("menu-toggle").setAttribute("aria-expanded", String(open));
  if (open) byId("drawer-close").focus();
  else if (restoreFocus && mobile.matches) byId("menu-toggle").focus();
}
function selectScenario(item) {
  if (running) stopRun();
  byId("budget-comparison").hidden = true;
  setInspectionSlots(null);
  selected = item;
  byId("request").setCustomValidity("");
  byId("request").value = item.prompt;
  for (const button of document.querySelectorAll("button[data-scenario], button[data-quick-scenario]")) {
    button.setAttribute("aria-pressed", String((button.dataset.scenario ?? button.dataset.quickScenario) === item.id));
  }
  showFeedback();
  showSaved();
  if (mobile.matches && document.body.dataset.drawer === "open") {
    setDrawer(false, false);
    byId("request").focus({preventScroll: true});
  }
}
async function showScenarioReplay(item) {
  const request = ++requestedReplay;
  byId("load-example").disabled = running;
  emptyRecord("读取中", "正在读取该场景的示例结果。", true);
  try {
    const report = await loadScenarioReplay(item);
    if (request === requestedReplay && selected === item && !running) {
      showReport(report, false, undefined, item);
    }
  } catch {
    if (request === requestedReplay && selected === item && !running) {
      emptyRecord("暂无示例", "示例暂时无法读取。仍可点击「运行 Agent」。");
    }
  }
}
async function loadScenarioReplay(item, {signal} = {}) {
  if (signal?.aborted) throw signal.reason;
  if (!savedReports.has(item.id)) {
    const response = await fetch("./scenarios/" + encodeURIComponent(item.id) + ".json", {signal});
    if (!response.ok) throw new Error("无法读取该场景的回放。");
    const report = await response.json();
    if (signal?.aborted) throw signal.reason;
    savedReports.set(item.id, report);
  }
  return savedReports.get(item.id);
}
function refreshRunControls() {
  byId("stop").hidden = !running;
  byId("run").disabled = running || batchBusy || offlinePreview;
  byId("compare-budget").disabled = running || (offlinePreview ? !examples.get(current)?.one_tool_report : batchBusy);
  byId("request").readOnly = running;
  byId("reset-inspection-setting").disabled = running;
  inspectionCapacity.setBusy(running);
  document.querySelectorAll('input[name="budget"]').forEach(input => { input.disabled = running; });
  byId("load-example").disabled = running || (!selected && !examples.has(current));
}
function setRunning(next) {
  running = next;
  refreshRunControls();
  batch.refreshAvailability?.();
}
function setInspectionSlots(slots) {
  inspectionSlots = Number.isInteger(slots) && slots >= 1 && slots <= 8 ? slots : null;
  byId("inspection-setting").hidden = inspectionSlots === null;
  byId("inspection-setting-text").textContent = inspectionSlots === null ? "" : `每批 ${inspectionSlots} 个巡检名额`;
}
function prepareInspectionTask(slots) {
  const scenario = scenarios.get("inspection-queue");
  if (!scenario) return;
  document.querySelector('input[name="domain"][value="manufacturing"]').checked = true;
  switchDomain("manufacturing");
  selectScenario(scenario);
  document.querySelector('input[name="budget"][value="1"]').checked = true;
  setInspectionSlots(slots);
  focusHeading("console-title");
}
function stopRun() {
  currentRun?.abort();
  currentRun = null;
  setRunning(false);
  showFeedback("已停止本次运行。");
  if (runView === requestedReplay) {
    emptyRecord("已停止", "可以修改任务重试，或查看已保存的运行。");
  }
  runView = null;
}
function startRun(event) {
  event.preventDefault();
  if (offlinePreview) return;
  const budget = Number(document.querySelector('input[name="budget"]:checked').value);
  executeRun([budget]);
}
async function executeRun(budgets) {
  if (running || batchBusy || offlinePreview) return;
  const request = byId("request").value.trim();
  if (!request) {
    byId("request").setCustomValidity("请输入要完成的业务任务。");
    byId("request").reportValidity();
    return;
  }
  const domain = current;
  const slots = inspectionSlots;
  const comparing = budgets.length === 2;
  const reports = [];
  const run = new AbortController();
  currentRun = run;
  const view = ++requestedReplay;
  runView = view;
  byId("budget-comparison").hidden = true;
  setRunning(true);
  emptyRecord("执行中", "正在执行当前任务。", true);
  showFeedback("正在启动运行环境…");
  try {
    for (const budget of budgets) {
      const task = {request, domain, max_tools: budget};
      if (slots !== null) task.inspection_slots = slots;
      reports.push(await runtime.run(task, {
        signal: run.signal,
        onProgress: message => showFeedback(comparing ? `预算 ${budget} · ${message}` : message)
      }));
    }
    if (currentRun !== run) return;
    reports.forEach(report => runHistory.save(report));
    if (view === requestedReplay) {
      showReport(reports.at(-1), true);
      if (comparing) renderComparison(reports, true);
      else showFeedback("运行完成。", false, true);
    } else {
      const open = () => {
        requestedReplay++;
        showReport(reports.at(-1), true);
        if (comparing) renderComparison(reports, true);
        else focusResult();
      };
      showFeedback("运行完成。", false, open, comparing ? "查看本次对比" : "查看本次结果");
    }
  } catch (error) {
    if (currentRun !== run) return;
    showFeedback("运行未完成。" + error.message, true);
    if (view === requestedReplay) {
      emptyRecord("运行失败", "可以重试，或查看该行业已保存的运行。");
    }
  } finally {
    if (currentRun === run) {
      currentRun = null;
      runView = null;
      setRunning(false);
    }
  }
}
function viewStoredRun(report, origin) {
  const domain = report.domain ?? current;
  document.querySelector(`input[name="domain"][value="${domain}"]`).checked = true;
  switchDomain(domain);
  byId("request").value = report.request;
  document.querySelector(`input[name="budget"][value="${report.max_tools}"]`).checked = true;
  if (report.domain === "manufacturing") {
    const savedCapacity = report.data?.inspection_capacity ?? report.data?.source?.original?.inspection_capacity;
    setInspectionSlots(savedCapacity?.slots_per_batch);
  }
  showReport(report, false, origin === "import" ? "导入的运行" : "历史运行");
  focusResult();
}
function renderComparison(reports, live) {
  const content = byId("comparison-content");
  const [narrow, wide] = reports;
  const base = new Set(narrow.tools.map(tool => tool.id));
  const grid = element("div", undefined, "comparison-grid");
  for (const report of reports) {
    const card = element("article", undefined, "comparison-card");
    card.append(
      element("h3", `最多 ${report.max_tools} 个工具`),
      element("p", `${statusNames[report.status] ?? report.status} · 实际调用 ${report.tools.length} · 待核 ${report.review.length}`)
    );
    if (report.tools.length) {
      const tools = element("ol");
      for (const tool of report.tools) {
        const name = scenarios.get(tool.id)?.title ?? toolNames[tool.id] ?? tool.id;
        const row = element("li", name);
        if (report === wide && !base.has(tool.id)) row.append(element("strong", " 新增"));
        tools.append(row);
      }
      card.append(tools);
    }
    const open = element("button", "查看完整结果", "secondary");
    open.type = "button";
    open.addEventListener("click", () => {
      showReport(report, live, live ? "预算对比 · 实时运行" : "预算对比 · 回放");
      focusResult();
    });
    card.append(open);
    grid.append(card);
  }
  content.replaceChildren(element("p", `${live ? "实时对比" : "示例回放"} · ${narrow.request}`, "comparison-note"), grid);
  byId("budget-comparison").hidden = false;
  showFeedback();
  focusHeading("comparison-title");
}
function switchDomain(domain) {
  drafts.set(current, byId("request").value);
  if (running) stopRun();
  current = domain;
  setInspectionSlots(null);
  byId("budget-comparison").hidden = true;
  selected = null;
  requestedReplay++;
  byId("request").setCustomValidity("");
  byId("scenario-search").value = "";
  byId("breadcrumb-domain").textContent = workspaces[domain][0];
  byId("console-domain").textContent = workspaces[domain][0];
  byId("domain-label").textContent = workspaces[domain][1];
  byId("request").value = drafts.get(domain) ?? examples.get(domain)?.request ?? domains[domain];
  byId("method-link").href = "https://github.com/Linxiushen/industry-ai-harnesses/tree/main/verticals/" + domain;
  showFeedback();
  renderScenarios();
  renderQuickStart();
  showSaved();
  refreshRunControls();
}
byId("request-form").addEventListener("submit", startRun);
byId("compare-budget").addEventListener("click", () => {
  if (!offlinePreview) {
    executeRun([1, 3]);
    return;
  }
  const example = examples.get(current);
  if (example?.one_tool_report) renderComparison([example.one_tool_report, example.expanded_report ?? example.report], false);
});
byId("close-comparison").addEventListener("click", () => {
  byId("budget-comparison").hidden = true;
  byId("compare-budget").focus();
});
byId("stop").addEventListener("click", stopRun);
byId("reset-inspection-setting").addEventListener("click", () => {
  setInspectionSlots(null);
  byId("request").focus();
});
byId("request").addEventListener("input", event => {
  event.target.setCustomValidity("");
  setInspectionSlots(null);
});
byId("request").addEventListener("keydown", event => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey) && !event.isComposing) {
    event.preventDefault();
    if (!running && !batchBusy && !offlinePreview) byId("request-form").requestSubmit();
  }
});
if (/mac/i.test(navigator.userAgent)) byId("run-shortcut").textContent = "⌘";
byId("scenario-search").addEventListener("input", renderScenarios);
byId("menu-toggle").addEventListener("click", () => setDrawer(true));
byId("drawer-close").addEventListener("click", () => setDrawer(false));
byId("drawer-overlay").addEventListener("click", () => setDrawer(false));
document.addEventListener("keydown", event => {
  if (document.body.dataset.drawer !== "open") return;
  if (event.key === "Escape") {
    event.preventDefault();
    setDrawer(false);
  } else if (event.key === "Tab") {
    const controls = [...byId("sidebar").querySelectorAll('a[href], button, input:not([type="radio"]), input[type="radio"]:checked')];
    if (event.shiftKey && document.activeElement === controls[0]) {
      event.preventDefault();
      controls.at(-1).focus();
    } else if (!event.shiftKey && document.activeElement === controls.at(-1)) {
      event.preventDefault();
      controls[0].focus();
    }
  }
});
mobile.addEventListener("change", () => setDrawer(false, false));
setDrawer(false, false);
byId("load-example").addEventListener("click", () => {
  showSaved();
  showFeedback();
  focusResult();
});
document.querySelectorAll('input[name="domain"]').forEach(input =>
  input.addEventListener("change", () => switchDomain(input.value))
);
byId("request").value = domains[current];
if (offlinePreview) {
  const home = new URL(location.href);
  home.search = "";
  home.hash = "";
  document.querySelector(".brand").href = home.href;
  byId("compare-budget").textContent = "对比示例";
  byId("run").textContent = "实时运行需在线";
}
refreshRunControls();
inspectionCapacity.load();
fetch("./replays.json").then(response => {
  if (!response.ok) throw new Error("Replay HTTP " + response.status);
  return response.json();
}).then(data => {
  for (const example of data.examples) examples.set(example.domain, example);
  examplesState = "ready";
  if (!selected && !running && byId("request").value === domains[current] && examples.has(current)) {
    byId("request").value = examples.get(current).request;
  }
}).catch(() => { examplesState = "error"; }).finally(() => {
  refreshRunControls();
  if (!selected && !running && byId("record-mode").dataset.live !== "true" && ["读取示例中", "读取中"].includes(byId("record-mode").textContent)) showSaved();
});
const bootView = requestedReplay;
const bootRequest = byId("request").value;
const catalogReady = fetch("./catalog.json").then(response => {
  if (!response.ok) throw new Error("Catalog HTTP " + response.status);
  return response.json();
}).then(data => {
  for (const item of data.scenarios) scenarios.set(item.id, item);
  renderScenarios();
  renderQuickStart();
  renderAtlas();
  batch.setCatalog(data.scenarios);
  const item = scenarios.get(new URLSearchParams(location.search).get("scenario"));
  if (item && requestedReplay === bootView &&
      (byId("request").value === bootRequest || byId("request").value === examples.get(current)?.request)) {
    openScenario(item);
  }
}).catch(() => {
  byId("scenario-stages").append(element("p", "场景目录暂时无法读取。仍可在工作台运行任务。", "empty"));
  byId("explore-grid").append(element("p", "场景目录暂时无法读取。", "empty"));
  batch.setCatalogError?.();
});
Promise.all([catalogReady, fetch("./showcase.json").then(response => {
  if (!response.ok) throw new Error("Showcase HTTP " + response.status);
  return response.json();
})]).then(([, data]) => {
  if (!scenarios.size) throw new Error("Missing scenario catalog");
  renderCasebook(data.cases);
}).catch(() => {
  byId("featured-case-list").replaceChildren(element("li", "案例暂时无法读取，可从场景库打开回放。", "hero-case-loading"));
  byId("casebook-grid").append(element("p", "案例暂时无法读取。", "empty"));
});
