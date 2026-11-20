"use strict";

(() => {
  const tables = new Map([
    ["recruiting_locations", [{
      key: "manual_review", label: "招募站点待核记录",
      columns: [["study", "试验"], ["city", "城市"], ["country", "国家"], ["reason", "待核原因"]]
    }]],
    ["registry_follow_up", [{
      key: "manual_review", label: "试验登记待核记录",
      columns: [["study", "试验"], ["reason", "待核原因"]]
    }]],
    ["manufacturing-capacity-plan", [{
      key: "order_netting", label: "订单净需求明细",
      columns: [["order_id", "订单"], ["product", "产品"], ["units", "订单数量"],
        ["stock_used", "成品抵扣量"], ["units_to_make", "待生产数量"], ["required_minutes", "所需工时（分钟）"]]
    }]],
    ["manufacturing-finite-schedule", [{
      key: "job_constraints", label: "工单排产约束",
      columns: [["job", "工单"], ["order", "订单"], ["machines", "可用机台"],
        ["ready", "最早开工（自午夜起，分钟）"], ["due", "交期（自午夜起，分钟）"], ["duration", "加工时长（分钟）"]]
    }]],
    ["manufacturing-oee-losses", [{
      key: "downtime_pareto", label: "停机损失分布",
      columns: [["cause", "停机原因"], ["lost_minutes", "损失时间（分钟）"], ["cumulative_pct", "累计占比（%）"]]
    }, {
      key: "reject_pareto", label: "不良品分布",
      columns: [["cause", "不良原因"], ["rejected_units", "不良数量"], ["cumulative_pct", "累计占比（%）"]]
    }]],
    ["manufacturing-shipment-trace", [{
      key: "shipment_records", label: "受影响及谱系待核的出货明细",
      columns: [["shipment", "出货单"], ["lot", "成品批次"], ["order", "订单"], ["customer", "客户"],
        ["units", "出货数量"], ["trace_status", "追踪状态"]]
    }]]
  ]);

  const traceStatuses = new Map([["affected", "已识别受影响"], ["genealogy missing", "谱系缺失，待核"]]);
  const isRecord = row => row !== null && typeof row === "object" && !Array.isArray(row);
  const hasId = value => typeof value === "string" && Boolean(value.trim());

  function rowsFor(spec, output) {
    const values = output[spec.key];
    if (!Array.isArray(values)) return [];
    const [identity] = spec.columns[0];
    const records = values.filter(row => isRecord(row) && hasId(row[identity]));
    if (spec.key !== "shipment_records") return records;

    const lots = new Map();
    for (const entry of Array.isArray(output.records) ? output.records : []) {
      if (isRecord(entry) && hasId(entry.lot) && traceStatuses.has(entry.status)) {
        lots.set(entry.lot, traceStatuses.get(entry.status));
      }
    }
    return records.filter(row => lots.has(row.lot)).map(row => ({...row, trace_status: lots.get(row.lot)}));
  }

  function renderCell(value, row, column) {
    if (column.key !== "study" || !/^NCT[0-9]{8}$/.test(value)) return null;
    const url = `https://clinicaltrials.gov/study/${value}`;
    if (row.url !== url) return null;
    const link = document.createElement("a");
    link.href = url;
    link.textContent = value;
    return link;
  }

  window.createToolEvidence = (tool, format) => {
    const specs = tables.get(tool?.id);
    if (!specs || !isRecord(tool.output)) return null;
    const sections = specs.map(spec => ({...spec, rows: rowsFor(spec, tool.output)})).filter(section => section.rows.length);
    if (!sections.length) return null;

    const details = document.createElement("details");
    details.className = "raw tool-evidence";
    const summary = document.createElement("summary");
    const count = sections.reduce((total, section) => total + section.rows.length, 0);
    const title = sections.length === 1 ? sections[0].label : "损失原因明细";
    summary.textContent = `${title}（${count} 条）`;
    details.append(summary);
    details.addEventListener("toggle", () => {
      if (!details.open || details.childElementCount > 1) return;
      for (const {rows, columns, label} of sections) {
        if (sections.length > 1) {
          const heading = document.createElement("h4");
          heading.textContent = label;
          details.append(heading);
        }
        details.append(window.createResultTable({rows, columns, label, format, renderCell}));
      }
    });
    return details;
  };
})();
