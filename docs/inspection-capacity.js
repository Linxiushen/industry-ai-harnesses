"use strict";

window.createInspectionCapacity = ({root, onOpen, onPrepare}) => {
  function node(tag, text, className) {
    const element = document.createElement(tag);
    if (text) element.textContent = text;
    if (className) element.className = className;
    return element;
  }

  const status = node("p", "正在读取推演结果。", "empty");
  status.setAttribute("role", "status");
  root.append(status);
  let loaded = false;
  let prepareButton = null;
  let busy = false;
  function setBusy(value) {
    busy = value;
    if (prepareButton) prepareButton.disabled = busy;
  }

  function load() {
    if (loaded) return;
    loaded = true;
    fetch("./inspection-capacity.json").then(response => {
      if (!response.ok) throw new Error("Unable to read capacity sweep");
      return response.json();
    }).then(show).catch(() => {
      status.textContent = "无法读取巡检推演。";
      root.replaceChildren(status);
      const retry = node("button", "重试", "secondary");
      retry.type = "button";
      retry.addEventListener("click", () => {
        status.textContent = "正在读取推演结果。";
        retry.remove();
        loaded = false;
        load();
      });
      root.append(retry);
    });
  }

  function show(data) {
    const baseline = data.default_slots;
    const reports = new Map(data.reports.map(report => [report.tools[0].output.slots_per_batch, report]));
    const reference = reports.get(baseline);
    const cap = node("input");
    cap.id = "inspection-slots";
    cap.type = "range";
    cap.min = String(Math.min(...reports.keys()));
    cap.max = String(Math.max(...reports.keys()));
    cap.value = String(baseline);
    const count = node("output");
    count.htmlFor.add(cap.id);
    const label = node("label", "每批巡检名额");
    label.htmlFor = cap.id;
    const control = node("div", "", "capacity-control");
    control.append(label, cap, count);

    const series = [...reports].map(([slots, report]) => ({
      slots, hits: report.tools[0].metrics.failures_in_queue,
      alerts: report.tools[0].metrics.false_alerts
    }));
    const scale = Math.max(1, ...series.flatMap(({hits, alerts}) => [hits, alerts]));
    const chart = node("div", "", "capacity-chart");
    chart.setAttribute("role", "group");
    chart.setAttribute("aria-label", "按巡检名额比较故障命中和误报");
    const legend = node("div", "", "capacity-legend");
    legend.append(node("span", "故障命中", "capacity-hit"), node("span", "误报", "capacity-alert"));
    const columns = node("div", "", "capacity-columns");
    for (const {slots, hits, alerts} of series) {
      const bar = node("button", "", "capacity-column");
      bar.type = "button";
      bar.dataset.slots = String(slots);
      bar.setAttribute("aria-label", `每批 ${slots} 名额，命中 ${hits}，误报 ${alerts}`);
      const height = node("span", "", "capacity-bars");
      height.setAttribute("aria-hidden", "true");
      const hit = node("i", "", "capacity-hit");
      hit.style.blockSize = hits / scale * 100 + "%";
      const alert = node("i", "", "capacity-alert");
      alert.style.blockSize = alerts / scale * 100 + "%";
      height.append(hit, alert);
      bar.append(height, node("span", String(slots), "capacity-slot"));
      bar.addEventListener("click", () => {
        cap.value = String(slots);
        render();
      });
      columns.append(bar);
    }
    chart.append(legend, columns);

    const comparison = node("div", "", "capacity-summary");
    comparison.setAttribute("aria-live", "polite");
    const table = node("table");
    const headings = table.createTHead().insertRow();
    for (const caption of ["指标", "当前名额", `默认 ${baseline} 名额`]) {
      const cell = node("th", caption);
      cell.scope = "col";
      headings.append(cell);
    }
    const metricsBody = table.createTBody();
    const open = node("button", "打开本档报告", "secondary");
    open.type = "button";
    open.addEventListener("click", () => onOpen(reports.get(Number(cap.value))));
    const reset = node("button", "恢复默认", "secondary");
    reset.type = "button";
    reset.addEventListener("click", () => {
      cap.value = String(baseline);
      render();
      cap.focus();
    });
    const actions = node("div", "", "capacity-actions");
    actions.append(open);
    if (onPrepare) {
      prepareButton = node("button", "转到实时任务", "secondary");
      prepareButton.type = "button";
      prepareButton.disabled = busy;
      prepareButton.addEventListener("click", () => onPrepare(Number(cap.value)));
      actions.append(prepareButton);
    }
    actions.append(reset);

    function render() {
      const slots = Number(cap.value);
      const selected = reports.get(slots);
      count.value = String(slots);
      cap.setAttribute("aria-valuetext", `每批 ${slots} 个名额`);
      reset.disabled = slots === baseline;
      for (const bar of columns.children) bar.setAttribute("aria-pressed", String(Number(bar.dataset.slots) === slots));
      const current = selected.tools[0].metrics;
      const fixed = reference.tools[0].metrics;
      const total = selected.data.test_failures;
      comparison.textContent = `风险排序在 ${total} 个已知故障中命中 ${current.failures_in_queue} 个，按刀具磨损排序命中 ${current.wear_only_failures_at_same_capacity} 个。`;
      metricsBody.replaceChildren();
      for (const [key, caption] of [
        ["records_reviewed", "巡检记录"],
        ["failures_in_queue", "故障命中"],
        ["wear_only_failures_at_same_capacity", "仅按磨损排序的命中"],
        ["failures_outside_queue", "未查到的故障"],
        ["false_alerts", "误报"]
      ]) {
        const row = metricsBody.insertRow();
        const heading = node("th", caption);
        heading.scope = "row";
        row.append(heading, node("td", String(current[key])), node("td", String(fixed[key])));
      }
    }

    cap.addEventListener("input", render);
    const context = node("p", `固定合成设备数据，每批 ${reference.tools[0].output.records_per_batch} 条观测。两种排序使用相同巡检名额。`, "capacity-context");
    root.replaceChildren(context, control, chart, comparison, table, actions);
    render();
  }

  return {load, setBusy};
};
