# Agent runtime and deployment

A shared PocketFlow graph drives the command line and the browser. Each industry owns its input contract, algorithms, output records and evaluation metrics. The agent can select 27 registered tools across the three industries. The catalog groups tools by business phase. Each tool can run directly by ID or by its example request. The 18 operations tools simulate individual decisions with bundled input data and produce reviewable output records.

1. **Plan.** The built-in planner selects one industry and a list of tools from a Chinese or English request. It extracts supported parameters such as a condition or country. Ambiguous requests can end with a clarification. On the CLI an explicitly selected local language model can propose the plan.
2. **Execute and observe.** A tool produces structured decisions and measured outcomes. An observation can introduce another tool in a handoff. For example, machine risk results can lead to inspection slots, followed by draft work orders. A one-tool limit returns the pending work. For manufacturing and energy a request reuses one domain evaluation across its requested tools.
3. **Finish.** The report includes the request, data source, tool metrics, observations and review items. Site availability, posting follow-ups, maintenance orders and proposed energy schedules require an operator's judgment. Download the JSON to retain the evidence.

The web worker loads a pinned Python runtime from the same GitHub Pages origin. It mounts the same Python files and clinical data used by the CLI. The page can show a saved run for every scenario before the runtime loads. Clicking Run executes a new graph with the current input. The worker has no model credentials. Its default planner follows explicit rules, so unusual wording may need a more specific request. The published browser cases use a small historical clinical projection and labeled simulated operating data. Each operations tool includes its input assumptions and data source in the report.

## Run locally

```sh
python agent.py "Find historical COPD trials"
python agent.py "Prepare a manufacturing shift briefing" --max-tools 1
python agent.py "Forecast electricity demand" --local-model YOUR_MODEL --port 11434
python -m unittest discover -s tests -v
```

The optional model must already be served on the user's loopback interface and support structured chat completions. Only the task and tool catalog are sent to it. The runtime validates plans before calling tools. The automated tests cover this interface with simulated provider replies.

## Build the website

```sh
curl -fL -o pyodide-core.tar.bz2 https://github.com/pyodide/pyodide/releases/download/0.27.7/pyodide-core-0.27.7.tar.bz2
python scripts/build_studio.py --runtime-archive pyodide-core.tar.bz2
python -m http.server 8000 --directory output/site
```

Visit `http://localhost:8000/`. Building without the archive produces the page and saved examples for reviewing the UI. The live worker requires the runtime archive. The GitHub workflow builds the whole site, exercises each industry through the browser, deploys the artifact and reads back the public page and replay file. [Framework and data attribution](THIRD_PARTY.md)
