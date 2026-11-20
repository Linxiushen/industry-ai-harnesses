"use strict";

(() => {
  const prefix = "industry-agent-studio:review:v1:";
  const schema = "industry-agent-studio-review.v1";
  const maxBundleBytes = 4 * 1024 * 1024;
  const notesLimit = 1200;
  const sessionEntries = new Map();
  const refreshPanels = new WeakMap();
  let serial = 0;

  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function canonicalReport(report) {
    return JSON.stringify(report, (_, value) => {
      if (typeof value === "number" && !Number.isFinite(value)) throw new Error("Invalid report number");
      if (value === null || typeof value !== "object" || Array.isArray(value)) return value;
      return Object.fromEntries(Object.keys(value).sort().map(key => [key, value[key]]));
    });
  }

  function hasFields(value, expected) {
    return value !== null && typeof value === "object" && !Array.isArray(value)
      && Object.keys(value).length === expected.length
      && expected.every(key => Object.hasOwn(value, key));
  }

  function isIsoTimestamp(value) {
    const parsed = typeof value === "string" ? new Date(value) : null;
    return parsed !== null && Number.isFinite(parsed.getTime()) && parsed.toISOString() === value;
  }

  function validateBundle(bundle, messages, fingerprint, canonical) {
    if (!hasFields(bundle, ["schema", "report_sha256", "exported_at", "updated_at", "findings", "notes", "report"])
        || bundle.schema !== schema || !isIsoTimestamp(bundle.exported_at)
        || (bundle.updated_at !== null && !isIsoTimestamp(bundle.updated_at))
        || typeof bundle.notes !== "string" || bundle.notes.length > notesLimit
        || !Array.isArray(bundle.findings)) {
      return "请选择工作台下载的复核包。";
    }
    if (bundle.report_sha256 !== fingerprint || canonicalReport(bundle.report) !== canonical) {
      return "这份复核包不对应当前报告。请先打开原报告。";
    }
    if (bundle.findings.length !== messages.length || !bundle.findings.every((finding, index) =>
      hasFields(finding, ["index", "message", "checked"])
      && finding.index === index && finding.message === messages[index] && typeof finding.checked === "boolean")) {
      return "复核条目与当前报告不一致。";
    }
    return "";
  }

  async function sha256(text) {
    try {
      const bytes = await window.crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
      return Array.from(new Uint8Array(bytes), byte => byte.toString(16).padStart(2, "0")).join("");
    } catch {
      return null;
    }
  }

  function getStored(key, findingCount) {
    const raw = window.localStorage.getItem(key);
    if (raw === null) return null;
    if (raw.length > 8000) throw new Error("Invalid review length");
    const saved = JSON.parse(raw);
    if (!hasFields(saved, ["checked", "notes", "updated_at"])
        || !Array.isArray(saved.checked) || saved.checked.length !== findingCount
        || !saved.checked.every(value => typeof value === "boolean")
        || typeof saved.notes !== "string" || saved.notes.length > notesLimit
        || !isIsoTimestamp(saved.updated_at)) {
      throw new Error("Invalid local review");
    }
    return saved;
  }

  function rememberSession(identity, state) {
    sessionEntries.delete(identity);
    sessionEntries.set(identity, state);
    if (sessionEntries.size > 24) sessionEntries.delete(sessionEntries.keys().next().value);
  }

  function downloadReview(bundle, fingerprint, domain) {
    const file = new Blob([JSON.stringify(bundle, null, 2) + "\n"], {type: "application/json"});
    const href = URL.createObjectURL(file);
    const link = document.createElement("a");
    link.href = href;
    link.download = "industry-review-" + domain + (fingerprint ? "-" + fingerprint.slice(0, 12) : "") + ".json";
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(href), 1000);
  }

  window.addEventListener("storage", event => {
    if (event.key && !event.key.startsWith(prefix)) return;
    try {
      if (event.storageArea !== window.localStorage) return;
    } catch {
      return;
    }
    for (const panel of document.querySelectorAll("[data-result-review-key]")) {
      if (event.key === null || event.key === panel.dataset.resultReviewKey) refreshPanels.get(panel)?.();
    }
  });

  window.createResultReview = report => {
    const messages = report.review;
    if (!Array.isArray(messages) || !messages.length) return null;
    const canonical = canonicalReport(report);
    const identity = ++serial;
    const empty = () => ({checked: messages.map(() => false), notes: "", updated_at: null});
    let state = empty();
    let fingerprint = null;
    let key = null;
    let sessionOnly = false;
    let importSerial = 0;

    const panel = node("section", "record-section result-review");
    const heading = node("h3", "result-review-title", "人工复核");
    heading.id = "result-review-title-" + identity;
    panel.setAttribute("aria-labelledby", heading.id);
    const header = node("div", "result-review-header");
    const progressWrap = node("div", "result-review-progress");
    const progress = node("progress");
    progress.max = messages.length;
    progress.value = 0;
    progress.setAttribute("aria-label", "人工复核进度");
    const count = node("span", "result-review-count", "已核对 0 / " + messages.length);
    count.setAttribute("role", "status");
    progressWrap.append(progress, count);
    header.append(heading, progressWrap);

    const fields = node("fieldset", "result-review-fields");
    fields.disabled = true;
    const list = node("ol", "result-review-list");
    const rows = messages.map((message, index) => {
      const item = node("li", "result-review-item");
      const label = node("label", "result-review-choice");
      const input = node("input");
      input.type = "checkbox";
      const pill = node("span", "result-review-pill", "待复核");
      pill.setAttribute("aria-hidden", "true");
      label.append(input, node("span", "result-review-message", message), pill);
      item.append(label);
      input.addEventListener("change", () => update(previous => {
        const checked = [...previous.checked];
        checked[index] = input.checked;
        return {...previous, checked};
      }));
      list.append(item);
      return {input, pill};
    });

    const notesLabel = node("label", "result-review-label", "复核备注");
    const notes = node("textarea", "result-review-notes");
    notes.id = "result-review-notes-" + identity;
    notesLabel.htmlFor = notes.id;
    notes.maxLength = notesLimit;
    notes.rows = 2;
    notes.placeholder = "记录核对依据或后续动作";
    notes.addEventListener("input", () => update(previous => ({...previous, notes: notes.value})));

    const footer = node("div", "result-review-footer");
    const storageStatus = node("span", "result-review-storage", "正在读取复核记录…");
    storageStatus.setAttribute("role", "status");
    const save = node("button", "secondary result-review-export", "下载复核包 ↓");
    save.type = "button";
    save.addEventListener("click", () => {
      const domain = ["pharma", "manufacturing", "energy"].includes(report.domain) ? report.domain : "run";
      downloadReview({
        schema,
        report_sha256: fingerprint,
        exported_at: new Date().toISOString(),
        updated_at: state.updated_at,
        findings: messages.map((message, index) => ({index, message, checked: state.checked[index]})),
        notes: state.notes,
        report: JSON.parse(canonical)
      }, fingerprint, domain);
    });
    const upload = node("input", "result-review-file");
    upload.type = "file";
    upload.accept = "application/json,.json";
    upload.hidden = true;
    const load = node("button", "secondary result-review-import", "导入复核包");
    load.type = "button";
    load.addEventListener("click", () => upload.click());
    const actions = node("div", "result-review-actions");
    actions.append(load, save, upload);
    footer.append(storageStatus, actions);

    const importStatus = node("p", "result-review-import-status");
    importStatus.setAttribute("role", "status");
    importStatus.hidden = true;
    const incoming = node("details", "result-review-incoming");
    incoming.hidden = true;
    const incomingText = node("textarea", "result-review-incoming-note");
    incomingText.readOnly = true;
    incomingText.rows = 2;
    incomingText.setAttribute("aria-label", "复核包中的备注");
    incoming.append(node("summary", "", "查看导入的备注"), incomingText);
    fields.append(list, notesLabel, notes, footer, importStatus, incoming);
    panel.append(header, fields);

    function importFeedback(message, failed = false, conflictingNote = "") {
      importStatus.textContent = message;
      importStatus.hidden = !message;
      importStatus.dataset.error = String(failed);
      incoming.hidden = !conflictingNote;
      incoming.open = false;
      incomingText.value = conflictingNote;
    }

    upload.addEventListener("change", async () => {
      const file = upload.files[0];
      upload.value = "";
      if (!file || !fingerprint) return;
      const attempt = ++importSerial;
      if (file.size > maxBundleBytes) {
        importFeedback("请选择小于 4 MB 的复核包。", true);
        return;
      }
      try {
        const bundle = JSON.parse(await file.text());
        if (attempt !== importSerial || !panel.isConnected) return;
        const error = validateBundle(bundle, messages, fingerprint, canonical);
        if (error) {
          importFeedback(error, true);
          return;
        }
        let conflict = "";
        let added = 0;
        let importedNote = false;
        update(previous => {
          conflict = previous.notes && bundle.notes && previous.notes !== bundle.notes ? bundle.notes : "";
          importedNote = !previous.notes && Boolean(bundle.notes);
          const checked = previous.checked.map((done, index) => {
            if (!done && bundle.findings[index].checked) added += 1;
            return done || bundle.findings[index].checked;
          });
          if (!added && !importedNote) return previous;
          return {...previous, checked, notes: previous.notes || bundle.notes};
        });
        const outcome = added ? "新增 " + added + " 条已核对记录。" : "没有新增已核对记录。";
        const detail = conflict ? " 已保留当前备注，可展开查看导入的备注。"
          : (importedNote ? " 已导入备注。" : "");
        importFeedback(outcome + detail, false, conflict);
      } catch {
        if (attempt === importSerial && panel.isConnected) importFeedback("无法读取该复核包。", true);
      }
    });

    function render() {
      const done = state.checked.filter(Boolean).length;
      progress.value = done;
      const progressText = "已核对 " + done + " / " + messages.length;
      if (count.textContent !== progressText) count.textContent = progressText;
      for (const [index, {input, pill}] of rows.entries()) {
        input.checked = state.checked[index];
        const status = input.checked ? "已核对" : "待复核";
        if (pill.textContent !== status) pill.textContent = status;
      }
      if (notes.value !== state.notes) notes.value = state.notes;
      const storageText = !fingerprint ? "仅保留在当前页面 · 无法校验复核包" : (sessionOnly ? "仅保留在当前页面"
        : (state.updated_at ? "已保存到此浏览器" : "复核进度保存在此浏览器"));
      if (storageStatus.textContent !== storageText) storageStatus.textContent = storageText;
      storageStatus.dataset.sessionOnly = String(sessionOnly);
    }

    function update(change) {
      if (key && !sessionOnly) {
        try {
          state = getStored(key, messages.length) ?? empty();
        } catch {
          sessionOnly = true;
        }
      }
      const next = change(state);
      if (next === state) {
        render();
        return;
      }
      state = {...next, updated_at: new Date().toISOString()};
      if (key && !sessionOnly) {
        try {
          window.localStorage.setItem(key, JSON.stringify(state));
        } catch {
          sessionOnly = true;
        }
      }
      if (sessionOnly) rememberSession(key ?? canonical, state);
      render();
    }

    sha256(canonical).then(digest => {
      fingerprint = digest;
      key = digest ? prefix + digest : null;
      const sessionState = sessionEntries.get(key ?? canonical);
      if (sessionState || !key) {
        sessionOnly = true;
        state = sessionState ?? empty();
      } else {
        try {
          state = getStored(key, messages.length) ?? empty();
        } catch {
          sessionOnly = true;
        }
      }
      if (key && !sessionOnly) {
        panel.dataset.resultReviewKey = key;
        refreshPanels.set(panel, () => {
          if (sessionOnly) return;
          try {
            state = getStored(key, messages.length) ?? empty();
          } catch {
            sessionOnly = true;
            rememberSession(key, state);
          }
          render();
        });
      }
      render();
      load.disabled = !fingerprint;
      fields.disabled = false;
    });
    return panel;
  };
})();
