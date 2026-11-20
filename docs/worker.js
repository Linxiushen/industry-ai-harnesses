/* Execute the repository's Python graph on this origin, off the UI thread. */
let boot;
let active = false;
function progress(message) {
  self.postMessage({type: "progress", message});
}

async function initialize() {
  const root = new URL("./engine/", self.location.href).href;
  progress("正在加载 Python 运行环境，首次运行可能需要一些时间。");
  importScripts(root + "pyodide.js");
  const py = await loadPyodide({indexURL: root});
  const response = await fetch("./bundle.json");
  if (!response.ok) throw new Error("无法读取项目文件，请刷新后重试。");
  const bundle = await response.json();
  for (const [name, contents] of Object.entries(bundle.files)) {
    const path = "/studio/" + name;
    py.FS.mkdirTree(path.slice(0, path.lastIndexOf("/")));
    py.FS.writeFile(path, contents, {encoding: "utf8"});
  }
  py.runPython("import sys, json\nsys.path.insert(0, '/studio')\nfrom industry_agent.runtime import run_agent");
  return py;
}

self.onmessage = async ({data}) => {
  if (active) return;
  active = true;
  try {
    if (!boot) boot = initialize().catch(error => { boot = undefined; throw error; });
    const py = await boot;
    progress("正在选择工具并核对运行结果。");
    py.globals.set("studio_task", JSON.stringify({
      request: data.request, domain: data.domain || null, max_tools: data.max_tools ?? 3
    }));
    try {
      const output = await py.runPythonAsync("json.dumps(run_agent(**json.loads(studio_task)), allow_nan=False)");
      self.postMessage({type: "result", report: JSON.parse(output)});
    } finally {
      py.globals.delete("studio_task");
    }
  } catch (error) {
    self.postMessage({type: "error", message: String(error.message || error)});
  } finally {
    active = false;
  }
};
