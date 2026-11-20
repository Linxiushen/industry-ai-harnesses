"use strict";

(() => {
  const compareText = new Intl.Collator("zh-CN", {numeric: true, sensitivity: "base"});
  const pageSizes = [10, 25, 50, 100];

  function element(tag, content, className) {
    const node = document.createElement(tag);
    if (content !== undefined) node.textContent = content;
    if (className) node.className = className;
    return node;
  }

  function button(text, className) {
    const control = element("button", text, className);
    control.type = "button";
    return control;
  }

  function rawText(value) {
    if (value == null) return "";
    return typeof value === "object" ? JSON.stringify(value) : String(value);
  }

  function searchable(value) {
    return String(value ?? "").normalize("NFKC").toLocaleLowerCase("zh-CN");
  }

  function csvField(value) {
    let text = rawText(value);
    // Keep numbers numeric. Prefix untrusted text that spreadsheet apps could run as a formula.
    const unsafeStart = /^[\t\r\n]|^[\s\p{Cf}\p{Cc}]*[=+@＝＋＠\-－]/u;
    if (typeof value === "string" && unsafeStart.test(text)) text = "'" + text;
    return '"' + text.replaceAll('"', '""') + '"';
  }

  function saveCsv(fields, rows, label) {
    const lines = [fields.map(field => csvField(field.label)).join(",")];
    for (const {values} of rows) lines.push(values.map(csvField).join(","));
    const csv = new Blob(["\ufeff", lines.join("\r\n"), "\r\n"], {type: "text/csv;charset=utf-8"});
    const href = URL.createObjectURL(csv);
    const link = element("a");
    link.href = href;
    const basename = label.replace(/[^\p{L}\p{N} \-]/gu, "").trim().slice(0, 60);
    link.download = (basename || "工具结果") + "-结果.csv";
    link.hidden = true;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(href), 1000);
  }

  const orderTypes = ["boolean", "number", "string", "object"];
  function compareValues(left, right, direction) {
    if (left == null || right == null) return Number(left == null) - Number(right == null);
    const leftType = typeof left;
    const rightType = typeof right;
    if (leftType !== rightType) return direction * (orderTypes.indexOf(leftType) - orderTypes.indexOf(rightType));
    if (leftType === "number" || leftType === "boolean") return direction * (left - right);
    return direction * compareText.compare(rawText(left), rawText(right));
  }

  window.createResultTable = ({rows, columns, format = rawText, renderCell, label = "工具结果"}) => {
    const root = element("section", undefined, "result-table");
    root.setAttribute("aria-label", `${label}记录`);
    const fields = columns.map(column => Array.isArray(column) ? {key: column[0], label: column[1]} : column);
    if (fields.length > 8) root.dataset.wide = "true";
    if (!rows.length || !fields.length) {
      root.append(element("p", "本次没有可浏览的记录。", "result-table-empty"));
      return root;
    }

    const data = rows.map((row, index) => ({
      row,
      index,
      values: fields.map(field => field.value ? field.value(row, index) : row?.[field.key])
    }));
    let matching = data;
    let page = 0;
    let sort = null;

    const toolbar = element("div", undefined, "result-table-toolbar");
    const filterLabel = element("label", undefined, "result-table-filter");
    filterLabel.append(element("span", "搜索结果记录", "sr-only"));
    const filter = element("input");
    filter.type = "search";
    filter.placeholder = "筛选记录";
    filter.autocomplete = "off";
    filter.spellcheck = false;
    filterLabel.append(filter);
    const reset = button("重置视图", "result-table-reset");
    const exportCsv = button("导出 CSV", "result-table-export");
    exportCsv.title = "下载全部匹配记录，保留当前排序";
    const count = element("span", undefined, "result-table-count");
    toolbar.append(filterLabel, reset, count, exportCsv);

    const viewport = element("div", undefined, "result-table-viewport");
    viewport.tabIndex = 0;
    viewport.setAttribute("role", "region");
    viewport.setAttribute("aria-label", `${label}数据表`);
    const table = element("table");
    table.append(element("caption", `${label}记录`, "sr-only"));
    const headers = table.createTHead().insertRow();
    const sortControls = fields.map((field, index) => {
      const header = element("th");
      header.scope = "col";
      const trigger = button(field.label, "result-table-sort");
      const icon = element("span");
      icon.setAttribute("aria-hidden", "true");
      trigger.append(icon);
      trigger.addEventListener("click", () => {
        if (sort?.index !== index) sort = {index, direction: 1};
        else sort = sort.direction === 1 ? {index, direction: -1} : null;
        page = 0;
        updateView();
      });
      header.append(trigger);
      headers.append(header);
      return {header, trigger, icon};
    });
    const body = table.createTBody();
    viewport.append(table);
    const empty = element("p", "没有匹配记录，请更换筛选词。", "result-table-empty");

    const pagination = element("div", undefined, "result-table-pagination");
    pagination.setAttribute("role", "group");
    pagination.setAttribute("aria-label", "结果分页");
    const pageSizeLabel = element("label", "每页 ", "result-table-page-size");
    const pageSize = element("select");
    for (const size of pageSizes) {
      const option = element("option", size);
      option.value = size;
      pageSize.append(option);
    }
    pageSizeLabel.append(pageSize);
    const range = element("span", undefined, "result-table-range");
    const previous = button("上一页", "result-table-page");
    const next = button("下一页", "result-table-page");
    pagination.append(pageSizeLabel, range, previous, next);

    const status = element("p", undefined, "sr-only");
    status.setAttribute("role", "status");
    root.append(toolbar, viewport, empty, pagination, status);

    function paintPage() {
      const size = Number(pageSize.value);
      const pages = Math.ceil(matching.length / size);
      const start = page * size;
      const end = Math.min(start + size, matching.length);
      range.textContent = pages ? `第 ${start + 1}–${end} 条 · ${page + 1} / ${pages} 页` : "0 条记录";
      previous.setAttribute("aria-disabled", String(page === 0));
      next.setAttribute("aria-disabled", String(page + 1 >= pages));
      empty.hidden = matching.length > 0;
      viewport.hidden = !empty.hidden;
      pagination.hidden = matching.length <= pageSizes[0];
      const contents = document.createDocumentFragment();
      for (const {row, values} of matching.slice(start, end)) {
        const tr = contents.appendChild(element("tr"));
        values.forEach((value, columnIndex) => {
          const cell = tr.insertCell();
          const rendered = renderCell?.(value, row, fields[columnIndex]);
          if (rendered instanceof Node) cell.append(rendered);
          else cell.textContent = rendered ?? format(value);
          if (typeof value === "number") cell.classList.add("result-table-number");
        });
      }
      body.replaceChildren(contents);
      status.textContent = `${count.textContent}。${range.textContent}`;
    }

    function updateView() {
      const terms = searchable(filter.value).trim().split(/\s+/).filter(Boolean);
      matching = terms.length ? data.filter(entry => {
        entry.searchText ??= entry.values.map(value => searchable(`${rawText(value)} ${format(value)}`)).join(" ");
        return terms.every(term => entry.searchText.includes(term));
      }) : data;
      if (sort) {
        matching = [...matching].sort((left, right) =>
          compareValues(left.values[sort.index], right.values[sort.index], sort.direction) || left.index - right.index);
      }
      for (const [index, {header, trigger, icon}] of sortControls.entries()) {
        const columnSort = sort?.index === index ? sort.direction : 0;
        if (columnSort) header.setAttribute("aria-sort", columnSort === 1 ? "ascending" : "descending");
        else header.removeAttribute("aria-sort");
        const action = columnSort === 1 ? "按降序排列" : columnSort === -1 ? "恢复原顺序" : "按升序排列";
        trigger.setAttribute("aria-label", `${fields[index].label}，${action}`);
        icon.textContent = columnSort === 1 ? "↑" : columnSort === -1 ? "↓" : "↕";
      }
      count.textContent = terms.length ? `匹配 ${matching.length} / ${data.length} 条` : `共 ${data.length} 条记录`;
      reset.disabled = !filter.value && !sort;
      exportCsv.disabled = !matching.length;
      paintPage();
    }

    filter.addEventListener("input", () => {
      page = 0;
      updateView();
    });
    reset.addEventListener("click", () => {
      filter.value = "";
      sort = null;
      page = 0;
      filter.focus();
      updateView();
    });
    pageSize.addEventListener("change", () => {
      page = 0;
      paintPage();
    });
    for (const [control, delta] of [[previous, -1], [next, 1]]) {
      control.addEventListener("click", () => {
        if (control.getAttribute("aria-disabled") === "true") return;
        page += delta;
        paintPage();
      });
    }
    exportCsv.addEventListener("click", () => saveCsv(fields, matching, label));
    updateView();
    return root;
  };
})();
