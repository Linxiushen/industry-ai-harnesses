"use strict";

const domains = {
  pharma: "检索 CKD 临床试验，筛选招募站点，列出需要跟进的登记记录。",
  manufacturing: "按故障风险排序，安排限额巡检，并生成工单草稿。",
  energy: "预测日前负荷，标出尖峰预警时段，并安排可调负荷排班。"
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
  synthetic: "合成数据", mixed: "历史试验记录与模拟运营数据",
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
const numeric = new Intl.NumberFormat("zh-CN", {maximumFractionDigits: 4});
const examples = new Map();
const drafts = new Map();
let current = "pharma";
let worker = null;
let running = false;
let timeout;
let examplesState = "loading";

function element(tag, content, style) {
  const node = document.createElement(tag);
  if (content !== undefined) node.textContent = content;
  if (style) node.className = style;
  return node;
}
function describe(value) {
  if (value == null) return "未定义";
  if (typeof value === "number") return numeric.format(value);
  if (Array.isArray(value)) return value.length ? value.map(describe).join("、") : "无";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}
function frame(title) {
  const box = element("section", undefined, "record-section");
  box.append(element("h3", title));
  return box;
}
function showFeedback(message = "", error = false) {
  const node = byId("feedback");
  node.hidden = !message;
  node.dataset.error = String(error);
  node.textContent = message;
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
  const spec = previewSpecs[id];
  if (!spec || !output || !Array.isArray(output[spec[0]])) return null;
  const rows = output[spec[0]];
  if (!rows.length) return element("p", "本次没有符合条件的条目。", "empty");
  let headings, values;
  if (id === "inspection-queue") {
    headings = ["批次", "安排巡检的记录号"];
    values = rows.slice(0, 3).map((row, i) => [i + 1, row]);
  } else if (id === "day-ahead-load") {
    headings = ["日期", "00:00 (MW)", "08:00 (MW)", "16:00 (MW)"];
    values = rows.slice(0, 3).map(row => [row.date, ...[0, 8, 16].map(hour => row.forecast_mw?.[hour])]);
  } else {
    headings = spec[1].map(([,label]) => label);
    values = rows.slice(0, 3).map(row => spec[1].map(([key]) => row?.[key]));
  }
  const viewport = element("div", undefined, "table-wrap");
  const table = element("table");
  table.append(element("caption", "输出预览 · " + values.length + " / " + rows.length + " 条"));
  const headers = table.createTHead().insertRow();
  for (const heading of headings) {
    const th = element("th", heading);
    th.scope = "col";
    headers.append(th);
  }
  const body = table.createTBody();
  for (const [rowIndex, row] of values.entries()) {
    const tr = body.insertRow();
    for (const [column, value] of row.entries()) {
      const cell = element("td", describe(value));
      if (id === "trial_landscape" && column === 0 && /^NCT[0-9]{8}$/.test(value)) {
        const registryUrl = "https://clinicaltrials.gov/study/" + value;
        if (registryUrl === rows[rowIndex].url) {
          const link = element("a", value);
          link.href = registryUrl;
          cell.replaceChildren(link);
        }
      }
      tr.append(cell);
    }
  }
  viewport.append(table);
  return viewport;
}
function makeTool(tool, open) {
  const detail = element("details", undefined, "tool");
  detail.open = open;
  const label = element("div");
  label.append(element("span", toolNames[tool.id] ?? tool.id, "tool-title"), element("code", tool.id, "tool-id"));
  const summary = element("summary");
  summary.append(label);
  detail.append(summary);
  const metrics = element("dl", undefined, "metric-grid");
  for (const [name, value] of Object.entries(tool.metrics ?? {})) {
    const metric = element("div");
    const key = element("dt", metricNames[name] ?? name);
    key.title = name;
    metric.append(key, element("dd", describe(value)));
    metrics.append(metric);
  }
  detail.append(metrics);
  const table = preview(tool.id, tool.output);
  if (table) detail.append(table);
  detail.append(makeDisclosure("查看完整工具输出", tool.output));
  return detail;
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
function showReport(report, live) {
  const mode = byId("record-mode");
  mode.textContent = live ? "本机实时运行" : "已保存的运行";
  mode.dataset.live = String(live);
  const content = byId("record-content");
  const summary = element("div", undefined, "record-summary");
  summary.append(element("p", report.request, "request-line"));
  const tools = report.tools ?? [];
  const steps = report.steps ?? [];
  const meta = [statusNames[report.status] ?? report.status, "调用 " + tools.length + " 个工具", steps.length + " 步"];
  if (report.data?.kind) meta.push(sourceKinds[report.data.kind] ?? report.data.kind);
  summary.append(element("p", meta.join("　·　"), "summary-meta"));
  content.replaceChildren(summary);
  if (tools.length) {
    const section = frame("工具结果");
    tools.forEach((tool, index) => section.append(makeTool(tool, index === 0)));
    content.append(section);
  }
  if (report.review?.length) {
    const review = frame("人工复核");
    review.classList.add("review");
    const notes = element("ul");
    for (const message of report.review) notes.append(element("li", describe(message)));
    review.append(notes);
    content.append(review);
  }
  if (steps.length) {
    const section = frame("执行轨迹");
    const track = element("ol", undefined, "steps");
    for (const step of steps) {
      const li = element("li");
      li.append(element("span", stepNames[step.kind] ?? step.kind, "step-kind"), document.createTextNode(step.message ?? ""));
      track.append(li);
    }
    section.append(track);
    content.append(section);
  }
  const source = frame("数据与导出");
  const data = report.data;
  if (data && Object.keys(data).length) {
    const label = sourceKinds[data.kind] ?? data.kind;
    const description = [label, typeof data.source === "string" && data.source].filter(Boolean).join(" · ");
    if (description) source.append(element("p", description, "provenance"));
    source.append(makeDisclosure("数据来源和参数", data));
  }
  const download = element("button", "下载本次运行 JSON ↓", "download");
  download.type = "button";
  download.addEventListener("click", () => downloadReport(report, live));
  source.append(download);
  content.append(source);
  content.setAttribute("aria-busy", "false");
}
function emptyRecord(modeText, message, busy = false) {
  const mode = byId("record-mode");
  mode.textContent = modeText;
  mode.dataset.live = "false";
  const content = byId("record-content");
  content.replaceChildren(element("p", message, "empty"));
  content.setAttribute("aria-busy", String(busy));
}
function showSaved() {
  const example = examples.get(current);
  byId("load-example").disabled = !example || running;
  if (example) showReport(example.report, false);
  else if (examplesState === "loading") emptyRecord("读取中", "正在读取已保存的示例。", true);
  else emptyRecord("暂无示例", "示例文件未能读取。你仍可点击「运行 Agent」执行任务。");
}
function releaseWorker() {
  if (worker) worker.terminate();
  worker = null;
}
function setRunning(next) {
  clearTimeout(timeout);
  running = next;
  byId("stop").hidden = !next;
  byId("run").disabled = next;
  byId("request").readOnly = next;
  document.querySelectorAll('input[name="budget"]').forEach(input => { input.disabled = next; });
  byId("load-example").disabled = next || !examples.has(current);
}
function stopRun() {
  releaseWorker();
  setRunning(false);
  showFeedback("已停止本次运行。");
  emptyRecord("已停止", "可以修改任务重试，或查看已保存的运行。");
}
function failRun(message) {
  releaseWorker();
  setRunning(false);
  showFeedback("运行未完成。" + message, true);
  emptyRecord("运行失败", "可以重试，或查看该行业已保存的运行。");
}
function startRun(event) {
  event.preventDefault();
  const request = byId("request").value.trim();
  if (!request) {
    byId("request").setCustomValidity("请输入要完成的业务任务。");
    byId("request").reportValidity();
    return;
  }
  if (running) return;
  const budget = Number(document.querySelector('input[name="budget"]:checked').value);
  setRunning(true);
  emptyRecord("执行中", "正在执行当前任务。", true);
  showFeedback("正在启动运行环境…");
  try {
    worker ??= new Worker("./worker.js");
    const active = worker;
    active.onmessage = ({data}) => {
      if (worker !== active || !running) return;
      if (data.type === "progress") showFeedback(data.message);
      if (data.type === "error") failRun(data.message);
      if (data.type === "result") {
        setRunning(false);
        showReport(data.report, true);
        showFeedback("运行记录已更新。");
      }
    };
    active.onerror = event => { if (worker === active) failRun(event.message || "浏览器未能加载执行环境。"); };
    active.postMessage({request, domain: current, max_tools: budget});
    timeout = setTimeout(() => failRun("加载或执行超时，请检查网络后重试。"), 180000);
  } catch (error) {
    failRun(error.message);
  }
}
function switchDomain(domain) {
  drafts.set(current, byId("request").value);
  if (running) stopRun();
  current = domain;
  byId("request").setCustomValidity("");
  byId("request").value = drafts.get(domain) ?? examples.get(domain)?.request ?? domains[domain];
  byId("method-link").href = "https://github.com/Linxiushen/industry-ai-harnesses/tree/main/verticals/" + domain;
  showFeedback();
  showSaved();
}
byId("request-form").addEventListener("submit", startRun);
byId("stop").addEventListener("click", stopRun);
byId("request").addEventListener("input", event => event.target.setCustomValidity(""));
byId("load-example").addEventListener("click", () => {
  showSaved();
  showFeedback("正在查看随项目发布的运行记录。");
});
document.querySelectorAll('input[name="domain"]').forEach(input =>
  input.addEventListener("change", () => switchDomain(input.value))
);
byId("request").value = domains[current];
fetch("./replays.json").then(response => {
  if (!response.ok) throw new Error("Replay HTTP " + response.status);
  return response.json();
}).then(data => {
  for (const example of data.examples) examples.set(example.domain, example);
  examplesState = "ready";
  if (!running && byId("request").value === domains[current] && examples.has(current)) {
    byId("request").value = examples.get(current).request;
  }
}).catch(() => { examplesState = "error"; }).finally(() => {
  byId("load-example").disabled = running || !examples.has(current);
  if (!running && byId("record-mode").dataset.live !== "true" && ["读取示例中", "读取中"].includes(byId("record-mode").textContent)) showSaved();
});
