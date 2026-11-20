"use strict";

window.createStudioRuntime = () => {
  let worker = null;
  let busy = false;

  function forget(active) {
    if (worker === active) {
      worker = null;
      active.terminate();
    }
  }

  function run(task, {signal, onProgress = () => {}} = {}) {
    if (signal?.aborted) return Promise.reject(signal.reason);
    if (busy) return Promise.reject(new Error("另一个任务正在运行，请等待或停止该任务。"));

    return new Promise((resolve, reject) => {
      worker ??= new Worker("./worker.js");
      const active = worker;
      busy = true;
      let settled = false;

      function finish(error, report, discard = false) {
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        signal?.removeEventListener("abort", abort);
        active.onmessage = null;
        active.onerror = null;
        active.onmessageerror = null;
        busy = false;
        if (discard) forget(active);
        if (error) reject(error);
        else resolve(report);
      }

      function abort() {
        finish(signal.reason, undefined, true);
      }

      const timeout = setTimeout(() => {
        finish(new Error("加载或执行超时，请重试。"), undefined, true);
      }, 180000);
      signal?.addEventListener("abort", abort, {once: true});
      active.onerror = event => {
        event.preventDefault();
        finish(new Error(event.message || "无法加载浏览器运行环境。"), undefined, true);
      };
      active.onmessageerror = () => {
        finish(new Error("浏览器无法读取运行结果。"), undefined, true);
      };
      active.onmessage = ({data}) => {
        if (data?.type === "progress") onProgress(data.message);
        else if (data?.type === "error") finish(new Error(data.message), undefined, true);
        else if (data?.type === "result" && Array.isArray(data.report?.tools)) finish(null, data.report);
        else finish(new Error("浏览器返回了无法识别的运行结果。"), undefined, true);
      };
      try {
        active.postMessage(task);
      } catch (error) {
        finish(error, undefined, true);
      }
    });
  }

  return {run};
};
