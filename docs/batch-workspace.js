"use strict";

window.createBatchWorkspace = function createBatchWorkspace({
  root, offlinePreview, runTask, loadReplay, onOpen, canRun = () => true, onBusyChange = () => {}
}) {
  const LIMIT = 12;
  const STORAGE_KEY = "industry-agent-studio:batch:v1";
  const MAX_CHECKPOINT_CHARS = 1024 * 1024;
  const domainLabels = {pharma: "制药临床", manufacturing: "制造运营", energy: "能源运营"};
  const exampleIds = ["trial_landscape", "inspection-queue", "flexible-load-scheduling"];
  const outcomeLabels = {
    completed: "已完成", needs_review: "待复核", needs_clarification: "待补充", budget_exhausted: "预算用完", error: "失败"
  };
  const statuses = {queued: "排队", running: "执行中", paused: "已暂停", failed: "失败"};
  const seconds = new Intl.NumberFormat("zh-CN", {maximumFractionDigits: 2});
  const chosen = new Set();
  let catalog = new Map();
  let catalogState = "loading";
  let batch = null;
  let controller = null;
  let restoreStopFocus = false;
  let checkpointReady = false;
  let checkpointDisabled = false;
  let lastCheckpoint = null;

  root.innerHTML = `
    <div class="batch-heading">
      <div><h2 id="batch-title" tabindex="-1">批量运行</h2><p>每批最多 12 项，按选择顺序运行。</p></div>
      <button type="button" class="secondary" data-batch="examples" disabled>加入三行业示例</button>
    </div>
    <div class="batch-grid">
      <div class="batch-picker">
        <div class="batch-filter">
          <div class="batch-field"><label for="batch-domain">行业</label><select id="batch-domain" data-batch="domain"><option value="">全部行业</option></select></div>
          <div class="batch-field"><label for="batch-search">搜索场景</label><input id="batch-search" data-batch="search" type="search" maxlength="120" placeholder="场景名、阶段或任务"></div>
        </div>
        <div class="batch-pick-actions">
          <label class="batch-selected-filter"><input type="checkbox" data-batch="show-selected"> 仅看已选</label>
          <button type="button" class="batch-text" data-batch="select-visible" disabled>选中当前列表</button>
          <button type="button" class="batch-text" data-batch="clear" disabled>清空选择</button>
        </div>
        <div class="batch-catalog" data-batch="catalog" role="group" aria-label="场景选择"></div>
      </div>
      <div class="batch-controls">
        <div class="batch-count"><strong data-batch="selected-count" aria-live="polite">已选 0 / 12</strong><span data-batch="visible-count"></span></div>
        <div class="batch-settings">
          <div class="batch-field"><label for="batch-mode">运行方式</label><select id="batch-mode" data-batch="mode"><option value="live">实时运行</option><option value="replay">保存的示例</option></select></div>
          <div class="batch-field" data-batch="budget-field"><label for="batch-budget">每项工具上限</label><select id="batch-budget" data-batch="budget"><option value="1">1 个</option><option value="2">2 个</option><option value="3" selected>3 个</option></select></div>
          <p class="batch-mode-note" data-batch="mode-note" hidden>示例采用各报告保存时的工具预算。</p>
        </div>
        <div class="batch-start-actions">
          <button type="button" class="primary" data-batch="start" disabled>开始批量运行</button>
          <button type="button" class="secondary" data-batch="stop" hidden>暂停批次</button>
        </div>
        <p class="batch-mode-note" data-batch="availability" role="status" hidden>当前有单项任务在运行。结束后可开始或继续批次。</p>
        <p class="batch-mode-note" data-batch="selection-note" role="status" hidden></p>
        <p class="batch-mode-note batch-storage-note" data-batch="storage-note" role="status" hidden></p>
      </div>
    </div>
    <div class="batch-summary" data-batch="summary" hidden>
      <div class="batch-summary-head">
        <div><h3>批次结果</h3><p data-batch="batch-info"></p></div>
        <div class="batch-summary-actions">
          <button type="button" class="secondary" data-batch="resume" hidden>继续暂停项</button>
          <button type="button" class="secondary" data-batch="retry" hidden>重试失败项</button>
          <button type="button" class="secondary" data-batch="export">导出 CSV</button>
        </div>
      </div>
      <progress data-batch="progress" value="0" max="1" aria-label="批次已处理场景数"></progress>
      <p class="batch-feedback" data-batch="feedback" role="status" aria-live="polite" aria-atomic="true"></p>
      <div class="batch-table-wrap" role="region" aria-label="批次结果明细" tabindex="0">
        <table class="batch-table" role="table">
          <thead role="rowgroup"><tr role="row"><th role="columnheader" scope="col">场景</th><th role="columnheader" scope="col">运行状态</th><th role="columnheader" scope="col">工具</th><th role="columnheader" scope="col">待复核</th><th role="columnheader" scope="col" data-batch="duration-head">耗时</th><th role="columnheader" scope="col"><span class="sr-only">报告操作</span></th></tr></thead>
          <tbody data-batch="rows" role="rowgroup"></tbody>
        </table>
      </div>
    </div>`;

  const get = name => root.querySelector(`[data-batch="${name}"]`);
  const mode = get("mode");
  const domainFilter = get("domain");
  const search = get("search");
  const showSelected = get("show-selected");
  const progress = get("progress");
  const selectors = [];

  for (const [value, label] of Object.entries(domainLabels)) domainFilter.add(new Option(label, value));
  if (offlinePreview) {
    mode.querySelector('[value="live"]').remove();
    mode.value = "replay";
  }

  function node(tag, text, className) {
    const result = document.createElement(tag);
    if (text !== undefined) result.textContent = text;
    if (className) result.className = className;
    return result;
  }

  function visibleItems() {
    const term = search.value.trim().toLocaleLowerCase();
    return [...catalog.values()].filter(item =>
      (!domainFilter.value || domainFilter.value === item.domain) && (!showSelected.checked || chosen.has(item.id)) &&
      `${item.title} ${item.phase ?? ""} ${item.stage ?? ""} ${item.prompt} ${item.id}`.toLocaleLowerCase().includes(term));
  }

  function refreshControls() {
    const locked = controller !== null;
    const available = canRun();
    const atLimit = chosen.size >= LIMIT;
    const count = `已选 ${chosen.size} / ${LIMIT}`;
    if (get("selected-count").textContent !== count) get("selected-count").textContent = count;
    get("visible-count").textContent = catalog.size ? `显示 ${selectors.length} / ${catalog.size}` : "";
    get("clear").disabled = locked || !chosen.size;
    get("start").disabled = locked || !available || !chosen.size;
    get("stop").hidden = !locked;
    get("stop").disabled = controller?.signal.aborted === true;
    get("examples").disabled = locked || atLimit || !exampleIds.some(id => catalog.has(id) && !chosen.has(id));
    get("select-visible").disabled = locked || atLimit || !selectors.some(({item}) => !chosen.has(item.id));
    mode.disabled = locked || offlinePreview;
    get("budget").disabled = locked;
    get("budget-field").hidden = mode.value === "replay";
    get("mode-note").hidden = mode.value === "live";
    get("availability").hidden = locked || available;
    for (const {item, input} of selectors) {
      input.checked = chosen.has(item.id);
      input.disabled = locked || (atLimit && !input.checked);
    }
  }

  function renderCatalog() {
    const target = get("catalog");
    target.replaceChildren();
    selectors.length = 0;
    for (const item of visibleItems()) {
      const label = node("label", undefined, "batch-option");
      const input = node("input");
      input.type = "checkbox";
      input.value = item.id;
      input.addEventListener("change", () => {
        if (controller) return;
        announceSelection();
        if (input.checked && chosen.size < LIMIT) chosen.add(item.id);
        if (!input.checked) chosen.delete(item.id);
        saveCheckpoint();
        if (showSelected.checked && !input.checked) {
          renderCatalog();
          const next = selectors.find(({input}) => !input.disabled)?.input;
          (next ?? showSelected).focus();
        } else {
          refreshControls();
        }
      });
      const caption = node("span");
      caption.append(node("strong", item.title), node("small", `${domainLabels[item.domain]} · ${item.phase ?? item.stage ?? "工作流"}`));
      label.append(input, caption);
      target.append(label);
      selectors.push({item, input});
    }
    if (!selectors.length) {
      const message = {
        loading: "正在读取场景目录…", error: "无法读取目录，请刷新后重试。",
        ready: showSelected.checked ? "当前筛选下没有已选场景。" : "没有匹配的场景。"
      };
      target.append(node("p", message[catalogState], "batch-empty"));
    }
    refreshControls();
  }

  function addToSelection(ids) {
    if (controller) return;
    announceSelection();
    for (const id of ids) {
      if (chosen.size >= LIMIT) break;
      if (catalog.has(id)) chosen.add(id);
    }
    saveCheckpoint();
    if (showSelected.checked) renderCatalog();
    else refreshControls();
  }

  function announceSelection(message = "") {
    const notice = get("selection-note");
    notice.textContent = message;
    notice.hidden = !message;
  }

  function showStorageWarning(message) {
    checkpointDisabled = true;
    const notice = get("storage-note");
    notice.textContent = message;
    notice.hidden = false;
  }

  function saveCheckpoint() {
    if (!checkpointReady || checkpointDisabled) return;
    try {
      const savedBatch = batch && {
        live: batch.live,
        budget: batch.budget,
        entries: batch.entries.map(({item, state, report, error, elapsed, attempts}) => ({
          id: item.id, domain: item.domain, prompt: item.prompt, state, report, error: error ?? "", elapsed, attempts
        }))
      };
      const encoded = JSON.stringify({
        version: 1,
        selected: [...chosen],
        mode: mode.value,
        budget: Number(get("budget").value),
        batch: savedBatch
      });
      if (encoded === lastCheckpoint) return;
      if (encoded.length > MAX_CHECKPOINT_CHARS) throw new Error("Batch checkpoint exceeds its size limit");
      window.sessionStorage.setItem(STORAGE_KEY, encoded);
      lastCheckpoint = encoded;
    } catch {
      showStorageWarning("无法保存当前进度。刷新可能丢失新结果，请先导出。");
    }
  }

  function restoreBatch(saved) {
    const validBudget = value => Number.isInteger(value) && value >= 1 && value <= 3;
    if (!saved || saved.version !== 1 || !Array.isArray(saved.selected) || saved.selected.length > LIMIT ||
        new Set(saved.selected).size !== saved.selected.length || !saved.selected.every(id => catalog.has(id)) ||
        !["live", "replay"].includes(saved.mode) || !validBudget(saved.budget) ||
        (offlinePreview && saved.mode !== "replay")) throw new Error("Incompatible batch checkpoint");
    if (saved.batch === null) return null;

    const value = saved.batch;
    if (!value || typeof value.live !== "boolean" || (value.live && offlinePreview) || !validBudget(value.budget) ||
        !Array.isArray(value.entries) || !value.entries.length || value.entries.length > LIMIT) {
      throw new Error("Invalid saved batch");
    }
    const ids = new Set();
    const entries = value.entries.map(row => {
      const item = catalog.get(row?.id);
      if (!item || ids.has(item.id) || row.domain !== item.domain || row.prompt !== item.prompt ||
          !["queued", "running", "paused", "done", "failed"].includes(row.state) ||
          !Number.isSafeInteger(row.attempts) || row.attempts < 0 ||
          typeof row.error !== "string" || row.error.length > 160 ||
          (row.elapsed !== null && (!value.live || !Number.isFinite(row.elapsed) || row.elapsed < 0))) {
        throw new Error("Invalid saved batch row");
      }
      const report = row.report;
      if (report !== null && (!window.isStudioRunReport(report) || report.domain !== item.domain ||
          report.request !== item.prompt || (value.live && report.max_tools !== value.budget))) {
        throw new Error("Saved report does not belong to its scenario");
      }
      if (row.state === "done" && (!report || report.status === "error") ||
          row.state === "failed" && (report ? report.status !== "error" : !row.error) ||
          ["queued", "running", "paused"].includes(row.state) && (report || row.error || row.elapsed !== null)) {
        throw new Error("Saved report is inconsistent with its status");
      }
      ids.add(item.id);
      const state = row.state === "queued" || row.state === "running" ? "paused" : row.state;
      return {item, state, report, error: row.error, elapsed: row.elapsed, attempts: row.attempts};
    });
    return {live: value.live, budget: value.budget, entries};
  }

  function readCheckpoint() {
    if (checkpointReady) return;
    checkpointReady = true;
    try {
      const raw = window.sessionStorage.getItem(STORAGE_KEY);
      if (raw === null) return;
      if (raw.length > MAX_CHECKPOINT_CHARS) throw new Error("Batch checkpoint exceeds its size limit");
      const saved = JSON.parse(raw);
      const restored = restoreBatch(saved);
      lastCheckpoint = raw;
      saved.selected.forEach(id => chosen.add(id));
      mode.value = saved.mode;
      get("budget").value = String(saved.budget);
      batch = restored;
      if (batch) {
        renderBatch();
        const hasPaused = batch.entries.some(entry => entry.state === "paused");
        refreshSummary(hasPaused ? "已恢复上次批次。可继续暂停项。" : "已恢复上次批次。");
      }
    } catch {
      showStorageWarning("无法读取上次批次。本页的新批次可运行和导出。");
    }
  }

  function makeResultRow(entry) {
    const row = node("tr");
    row.setAttribute("role", "row");
    const title = node("th");
    title.scope = "row";
    title.setAttribute("role", "rowheader");
    title.append(node("strong", entry.item.title), node("small", domainLabels[entry.item.domain]));
    const status = node("td", undefined, "batch-status-cell");
    status.setAttribute("role", "cell");
    const metrics = [["tools", "工具"], ["review", "待复核"], ["duration", "耗时"]].map(([key, caption]) => {
      const cell = node("td", undefined, "batch-metric-cell");
      cell.setAttribute("role", "cell");
      const mobileLabel = node("span", caption, "batch-cell-label");
      mobileLabel.setAttribute("aria-hidden", "true");
      const value = node("span");
      cell.append(mobileLabel, value);
      cell.hidden = key === "duration" && !batch.live;
      return {key, cell, value};
    });
    const open = node("button", "查看报告", "batch-text");
    open.type = "button";
    open.setAttribute("aria-label", `查看报告：${entry.item.title}`);
    open.addEventListener("click", () => onOpen(entry.report, {item: entry.item, live: batch.live}));
    const action = node("td", undefined, "batch-action-cell");
    action.setAttribute("role", "cell");
    action.append(open);
    row.append(title, status, ...metrics.map(({cell}) => cell), action);
    entry.elements = {status, open, ...Object.fromEntries(metrics.map(({key, value}) => [key, value]))};
    return row;
  }

  function refreshRow(entry) {
    const {elements, state, report, error, elapsed, attempts} = entry;
    const chip = node("span", statuses[state] ?? outcomeLabels[report?.status] ?? "已返回", "batch-state");
    chip.dataset.state = state === "done" ? report.status : state;
    elements.status.replaceChildren(chip);
    if (error) elements.status.append(node("small", error, "batch-error"));
    if (attempts > 1) elements.status.append(node("small", `尝试 ${attempts} 次`));
    elements.tools.textContent = report ? `${report.tools.length} / ${report.max_tools}` : "—";
    elements.review.textContent = report ? String(report.review.length) : "—";
    elements.duration.textContent = elapsed == null ? "—" : `${seconds.format(elapsed / 1000)} 秒`;
    elements.open.hidden = !report;
  }

  function refreshSummary(message) {
    if (!batch) return;
    const failed = batch.entries.filter(entry => entry.state === "failed").length;
    const done = batch.entries.filter(entry => entry.state === "done").length;
    const needsReview = batch.entries.filter(entry => entry.report?.status === "needs_review" || entry.report?.review.length > 0).length;
    const paused = batch.entries.filter(entry => entry.state === "paused").length;
    progress.max = batch.entries.length;
    progress.value = done + failed;
    const modeLabel = batch.live ? `实时运行 · 每项最多 ${batch.budget} 个工具` : "示例回放";
    get("batch-info").textContent = `${modeLabel} · 已返回 ${done}/${batch.entries.length} · 待复核 ${needsReview} · 失败 ${failed}`;
    if (message !== undefined) get("feedback").textContent = message;
    get("resume").hidden = paused === 0;
    get("resume").disabled = controller !== null || !canRun();
    get("retry").hidden = failed === 0;
    get("retry").disabled = controller !== null || !canRun();
  }

  async function execute(state) {
    if (!batch || controller || !canRun()) return;
    const entries = batch.entries.filter(entry => entry.state === state);
    if (!entries.length) return;
    controller = new AbortController();
    const {signal} = controller;
    onBusyChange(true);
    for (const entry of entries) {
      Object.assign(entry, {state: "queued", report: null, error: "", elapsed: null});
      refreshRow(entry);
    }
    saveCheckpoint();
    refreshControls();
    try {
      for (const entry of entries) {
        if (signal.aborted) break;
        entry.state = "running";
        entry.attempts += 1;
        refreshRow(entry);
        saveCheckpoint();
        const started = performance.now();
        const position = batch.entries.indexOf(entry) + 1;
        const taskLabel = `${position}/${batch.entries.length} · ${entry.item.title}`;
        refreshSummary(taskLabel);
        try {
          const report = batch.live ? await runTask({request: entry.item.prompt, domain: entry.item.domain, max_tools: batch.budget}, {
            signal,
            onProgress(message) {
              if (!signal.aborted && entry.state === "running") refreshSummary(`${taskLabel} · ${message}`);
            }
          }) : await loadReplay(entry.item, {signal});
          if (signal.aborted) break;
          if (!report || !Array.isArray(report.tools) || !Array.isArray(report.review) ||
            report.domain !== entry.item.domain || report.request !== entry.item.prompt ||
            !Number.isInteger(report.max_tools) || (batch.live && report.max_tools !== batch.budget) ||
            !Object.hasOwn(outcomeLabels, report.status)) throw new Error("报告与选定场景不匹配。");
          entry.report = report;
          entry.state = report.status === "error" ? "failed" : "done";
        } catch (error) {
          if (signal.aborted) break;
          entry.state = "failed";
          entry.error = (error instanceof Error ? error.message : String(error)).slice(0, 160) || "运行未返回报告。";
        }
        if (batch.live) entry.elapsed = performance.now() - started;
        refreshRow(entry);
        saveCheckpoint();
      }
    } finally {
      if (signal.aborted) {
        for (const entry of entries) {
          if (entry.state !== "queued" && entry.state !== "running") continue;
          entry.state = "paused";
          refreshRow(entry);
        }
        saveCheckpoint();
      }
      const moveFocus = document.activeElement === get("stop") || (restoreStopFocus && document.activeElement === document.body);
      restoreStopFocus = false;
      controller = null;
      onBusyChange(false);
      refreshControls();
      refreshSummary(signal.aborted ? "已暂停。已返回的报告仍可查看和导出。" : "本轮批次处理结束。");
      if (moveFocus) get(signal.aborted ? "resume" : "export").focus({preventScroll: true});
    }
  }

  function start() {
    if (controller || !canRun() || !chosen.size) return;
    announceSelection();
    batch = {
      live: mode.value === "live", budget: Number(get("budget").value),
      entries: [...chosen].map(id => ({item: catalog.get(id), state: "queued", report: null, elapsed: null, attempts: 0}))
    };
    renderBatch();
    void execute("queued");
    if (controller) get("stop").focus({preventScroll: true});
  }

  function renderBatch() {
    get("duration-head").hidden = !batch.live;
    const rows = get("rows");
    rows.replaceChildren(...batch.entries.map(makeResultRow));
    batch.entries.forEach(refreshRow);
    get("summary").hidden = false;
    get("start").textContent = "开始新批次";
  }

  function exportResults() {
    if (!batch) return;
    const csvCell = value => {
      let text = String(value ?? "");
      if (typeof value === "string" && /^[\s]*[=+@-]|^[\t\r\n]/u.test(text)) text = `'${text}`;
      return `"${text.replaceAll('"', '""')}"`;
    };
    const rows = [["场景 ID", "场景", "行业", "运行方式", "状态", "已调用工具", "工具上限", "待复核数", "耗时（毫秒）", "尝试次数", "错误"]];
    for (const {item, state, report, elapsed, attempts, error} of batch.entries) rows.push([
      item.id, item.title, domainLabels[item.domain], batch.live ? "实时运行" : "示例回放",
      statuses[state] ?? outcomeLabels[report?.status], report?.tools.length,
      report?.max_tools ?? (batch.live ? batch.budget : null), report?.review.length,
      elapsed == null ? null : Math.round(elapsed), attempts, error
    ]);
    const blob = new Blob(["\uFEFF", rows.map(row => row.map(csvCell).join(",")).join("\r\n")], {type: "text/csv;charset=utf-8"});
    const url = URL.createObjectURL(blob);
    const link = node("a");
    link.href = url;
    link.download = "industry-agent-batch.csv";
    root.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  search.addEventListener("input", renderCatalog);
  domainFilter.addEventListener("change", renderCatalog);
  showSelected.addEventListener("change", renderCatalog);
  mode.addEventListener("change", () => { refreshControls(); saveCheckpoint(); });
  get("budget").addEventListener("change", saveCheckpoint);
  get("examples").addEventListener("click", () => addToSelection(exampleIds));
  get("select-visible").addEventListener("click", () => addToSelection(selectors.map(({item}) => item.id)));
  get("clear").addEventListener("click", () => { announceSelection(); chosen.clear(); renderCatalog(); saveCheckpoint(); });
  get("start").addEventListener("click", start);
  get("stop").addEventListener("click", () => {
    restoreStopFocus = document.activeElement === get("stop");
    controller?.abort();
    refreshControls();
  });
  get("resume").addEventListener("click", () => void execute("paused"));
  get("retry").addEventListener("click", () => void execute("failed"));
  get("export").addEventListener("click", exportResults);
  renderCatalog();

  return {
    setCatalog(items) {
      catalog = new Map(items.filter(item => Object.hasOwn(domainLabels, item.domain)).map(item => [item.id, item]));
      for (const id of chosen) if (!catalog.has(id)) chosen.delete(id);
      catalogState = "ready";
      readCheckpoint();
      renderCatalog();
    },
    setCatalogError() { catalogState = "error"; renderCatalog(); },
    addScenario(id) {
      if (chosen.has(id)) {
        announceSelection("此场景已在当前选择中。");
        return true;
      }
      if (controller) announceSelection("暂停或等待批次结束后再加入场景。");
      else if (chosen.size >= LIMIT) announceSelection("已达 12 项上限。移除一项后可继续加入。");
      else if (!catalog.has(id)) announceSelection("场景暂时不可用，请刷新后重试。");
      else {
        addToSelection([id]);
        announceSelection(`已加入「${catalog.get(id).title}」。`);
        return true;
      }
      return false;
    },
    refreshAvailability() { refreshControls(); refreshSummary(); }
  };
};
