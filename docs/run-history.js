"use strict";

(() => {
  const storageKey = "industry-agent-studio:history:v1";
  const maxEntries = 12;
  const maxFileBytes = 512 * 1024;
  const maxStorageChars = 1024 * 1024;
  const domains = new Map([["pharma", "制药临床"], ["manufacturing", "制造运营"], ["energy", "能源运营"]]);
  const statuses = new Map([
    ["completed", "已完成"], ["needs_review", "待人工复核"], ["needs_clarification", "待补充任务"],
    ["budget_exhausted", "用完工具预算"], ["error", "运行失败"]
  ]);
  const origins = new Map([["live", "实时运行"], ["replay", "示例回放"], ["import", "导入报告"]]);
  const stepKinds = new Set(["plan", "tool", "observe", "review", "complete", "clarify", "budget", "error"]);
  const formatDate = new Intl.DateTimeFormat("zh-CN", {dateStyle: "short", timeStyle: "short"});
  const isRecord = value => value !== null && typeof value === "object" && !Array.isArray(value);

  // Keep imported and stored reports within what the result renderer can display.
  function isBoundedJson(value, depth = 0, budget = {nodes: 30000}) {
    if (--budget.nodes < 0 || depth > 18) return false;
    if (value === null || typeof value === "boolean") return true;
    if (typeof value === "number") return Number.isFinite(value);
    if (typeof value === "string") return value.length <= 24000;
    if (Array.isArray(value)) return value.length <= 4096 && value.every(child => isBoundedJson(child, depth + 1, budget));
    return isRecord(value) && Object.entries(value).every(([key, child]) =>
      key.length <= 160 && key !== "prototype" && !Object.hasOwn(Object.prototype, key)
      && isBoundedJson(child, depth + 1, budget));
  }

  function isTool(tool) {
    if (!isRecord(tool) || typeof tool.id !== "string" || !/^[a-z][a-z0-9_-]{0,79}$/.test(tool.id)
        || Object.hasOwn(Object.prototype, tool.id) || !isRecord(tool.metrics) || !isRecord(tool.output)
        || (tool.data !== undefined && !isRecord(tool.data))) return false;

    // This legacy output has a specialized table that expects object rows.
    const forecasts = tool.output.daily_24h_forecasts;
    return tool.id !== "day-ahead-load" || !Array.isArray(forecasts) || forecasts.every(isRecord);
  }

  function isReport(report) {
    if (!isRecord(report) || typeof report.request !== "string" || !report.request.trim()
        || [...report.request].length > 4000 || !statuses.has(report.status)
        || !Number.isInteger(report.max_tools) || report.max_tools < 1 || report.max_tools > 3
        || !isRecord(report.data) || !Array.isArray(report.tools) || report.tools.length > report.max_tools
        || !Array.isArray(report.steps) || report.steps.length > 24
        || !Array.isArray(report.review) || report.review.length > 16) return false;
    const unmatched = report.domain === null && !report.tools.length
      && ["needs_clarification", "error"].includes(report.status);
    return (domains.has(report.domain) || unmatched)
      && isBoundedJson(report)
      && report.tools.every(isTool)
      && report.steps.every(step => isRecord(step) && stepKinds.has(step.kind) && typeof step.message === "string")
      && report.review.every(message => typeof message === "string");
  }

  function isEntry(entry) {
    return isRecord(entry) && typeof entry.id === "string" && /^[a-z0-9-]{1,40}$/.test(entry.id)
      && Number.isSafeInteger(entry.savedAt) && entry.savedAt > 0 && entry.savedAt <= 8640000000000000
      && origins.has(entry.origin) && isReport(entry.report);
  }

  function pack(entries) {
    return JSON.stringify({version: 1, entries});
  }

  function node(tag, label, className) {
    const child = document.createElement(tag);
    if (label) child.textContent = label;
    if (className) child.className = className;
    return child;
  }

  function button(label, className) {
    const child = node("button", label, className);
    child.type = "button";
    return child;
  }

  window.isStudioRunReport = isReport;
  window.createRunHistory = ({root, onOpen}) => {
    let entries = [];
    let sessionOnly = false;
    let importSerial = 0;

    const toolbar = node("div", "", "history-toolbar");
    const importButton = button("导入 JSON", "history-import");
    const fileInput = node("input");
    fileInput.type = "file";
    fileInput.accept = ".json,application/json";
    fileInput.hidden = true;
    const count = node("span", "", "history-count");
    toolbar.append(importButton, fileInput, count);
    const message = node("p", "", "history-message");
    message.setAttribute("role", "status");
    message.hidden = true;
    const empty = node("p", "暂无记录。运行任务后可在此重新打开结果。", "history-empty");
    const list = node("ol", "", "history-list");
    root.replaceChildren(toolbar, message, empty, list);

    function feedback(text, error = false) {
      message.textContent = text;
      message.dataset.error = String(error);
      message.hidden = !text;
    }

    function readStorage() {
      if (sessionOnly) return;
      try {
        const raw = window.localStorage.getItem(storageKey);
        if (raw === null) {
          entries = [];
          return;
        }
        if (raw.length > maxStorageChars) throw new Error("History is too large");
        const saved = JSON.parse(raw);
        if (!isRecord(saved) || saved.version !== 1 || !Array.isArray(saved.entries)
            || saved.entries.length > maxEntries || !saved.entries.every(isEntry)
            || new Set(saved.entries.map(entry => entry.id)).size !== saved.entries.length) {
          throw new Error("Unsupported history format");
        }
        entries = saved.entries;
      } catch {
        sessionOnly = true;
        feedback("无法读取浏览器历史。新记录仅保留在当前页面。", true);
      }
    }

    function writeStorage(value) {
      if (sessionOnly) return;
      try {
        window.localStorage.setItem(storageKey, value);
      } catch {
        sessionOnly = true;
      }
    }

    function render() {
      count.textContent = entries.length + " / " + maxEntries + " 条" + (sessionOnly ? " · 仅当前页面" : " · 此浏览器");
      empty.hidden = entries.length > 0;
      list.hidden = !entries.length;
      list.replaceChildren(...entries.map(entry => {
        const row = node("li", "", "history-entry");
        const detail = node("div", "", "history-detail");
        const request = entry.report.request;
        const summary = request.length > 140 ? request.slice(0, 140).trimEnd() + "…" : request;
        detail.append(node("p", summary, "history-request"),
          node("p", [
            domains.get(entry.report.domain) ?? "未匹配行业", statuses.get(entry.report.status),
            entry.report.tools.length + " / " + entry.report.max_tools + " 个工具",
            origins.get(entry.origin), formatDate.format(entry.savedAt)
          ].join(" · "), "history-meta"));
        const actions = node("div", "", "history-actions");
        const open = button("打开", "history-open");
        open.setAttribute("aria-label", "打开运行记录：" + summary);
        open.addEventListener("click", () => onOpen(entry.report, "history", entry.origin));
        const remove = button("删除", "history-delete");
        remove.setAttribute("aria-label", "删除运行记录：" + summary);
        remove.addEventListener("click", () => {
          const index = entries.findIndex(candidate => candidate.id === entry.id);
          readStorage();
          entries = entries.filter(candidate => candidate.id !== entry.id);
          writeStorage(pack(entries));
          feedback(sessionOnly ? "已在当前页面删除。浏览器存储不可用。" : "已删除这条记录。");
          render();
          const openButtons = list.querySelectorAll(".history-open");
          (openButtons[Math.max(0, Math.min(index, openButtons.length - 1))] ?? importButton).focus();
        });
        actions.append(open, remove);
        row.append(detail, actions);
        return row;
      }));
    }

    function save(report, origin = "live") {
      if (!origins.has(origin) || !isReport(report)) {
        feedback("这份报告的格式无法保存到历史。", true);
        return false;
      }
      const serializedReport = JSON.stringify(report);
      if (serializedReport.length > maxFileBytes) {
        feedback("报告太大。可下载 JSON 保存。", true);
        return false;
      }
      readStorage();
      if (entries.some(entry => JSON.stringify(entry.report) === serializedReport)) {
        feedback("这份报告已经在历史中。");
        render();
        return true;
      }
      const savedAt = Date.now();
      const id = savedAt.toString(36) + "-" + Math.random().toString(36).slice(2);
      const next = [{id, savedAt, origin, report: JSON.parse(serializedReport)}, ...entries].slice(0, maxEntries);
      let packed = pack(next);
      while (packed.length > maxStorageChars) {
        next.pop();
        packed = pack(next);
      }
      const removed = entries.length + 1 - next.length;
      entries = next;
      writeStorage(packed);
      let status = sessionOnly ? "已添加。记录仅保留在当前页面。" : "已保存到此浏览器。";
      if (removed) status += " 已达到容量上限，移除最早的 " + removed + " 条。";
      feedback(status);
      render();
      return true;
    }

    importButton.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", async () => {
      const file = fileInput.files[0];
      fileInput.value = "";
      if (!file) return;
      const currentImport = ++importSerial;
      if (file.size > maxFileBytes) {
        feedback("请选择小于 512 KB 的 JSON 报告。", true);
        return;
      }
      let report;
      try {
        report = JSON.parse(await file.text());
      } catch {
        if (currentImport === importSerial) feedback("无法读取该文件。请选择工作台导出的 JSON。", true);
        return;
      }
      if (currentImport !== importSerial) return;
      if (!isReport(report)) {
        feedback("报告格式不兼容。请选择工作台导出的 JSON。", true);
        return;
      }
      onOpen(report, "import");
      feedback("已打开报告。可在结果区选择保存。");
    });

    window.addEventListener("storage", event => {
      if (!sessionOnly && (event.key === storageKey || event.key === null)) {
        readStorage();
        render();
      }
    });
    readStorage();
    render();
    return {save};
  };
})();
