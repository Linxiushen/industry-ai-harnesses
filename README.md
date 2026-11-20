# Industry AI Harnesses

[**Open the live Agent Studio**](https://linxiushen.github.io/industry-ai-harnesses/) · [中文说明](README.zh-CN.md)

Ask the agent to find historical COPD trials, allocate inspection slots or prepare an electricity shift briefing. Each run shows its tool choices, observations, remaining work and evidence for the reviewer. Try a one-tool budget on a manufacturing handoff, then raise it to three to see how the inspection queue leads to work-order drafts. The browser executes the Python graph locally after downloading the runtime. Saved examples are available immediately.

```sh
python agent.py "Prepare a manufacturing shift briefing" --max-tools 3 --out output/shift.json
```

The default planner uses domain vocabulary and explicit rules. Observations can add a follow-up tool, request clarification or route decisions for review. The budget counts distinct tool decisions surfaced to the user. Energy and manufacturing share one backtest per domain request. To try model-based planning with a model you already serve on localhost, add `--local-model YOUR_MODEL --port 11434` to the CLI command. [Architecture, deployment and limits](ARCHITECTURE.md)

Three runnable reference projects for teams evaluating where AI can help with operational decisions. A clinical operations analyst gets trial evidence and follow-up queues, a maintenance planner gets a fixed number of inspections, and an energy planner gets tomorrow's load forecast and shift schedule. Each harness produces JSON with decisions, supporting data, baseline comparisons and checks.

[中文项目导览](README.zh-CN.md) · [Clinical trial operations](verticals/pharma/README.md) · [Manufacturing maintenance](verticals/manufacturing/README.md) · [Electricity demand](verticals/energy/README.md)

## Run all nine workflows

With Python 3.11+ in the checkout, run:

```sh
python run.py all --out output/decisions.json
```

The default run works offline using the Python standard library. The console shows metrics. The JSON file includes the ranked trials, site and registry queues, hourly forecasts, alerts, scheduled load blocks, inspection IDs and work-order drafts. A failed built-in check exits with a nonzero status. To integrate one project, use `python run.py manufacturing` or import the domain module's `run(data_dir=None)` function. A custom cohort can be passed as `python run.py pharma --data-dir path/to/cohort`. Each domain guide documents its data format.

| Harness | Three decisions | What the replay showed |
| --- | --- | --- |
| [Clinical trial operations](verticals/pharma/README.md) | Retrieve related trials, shortlist recruiting locations, prioritize registry follow-up. | Six labeled searches over 12 historical NCBI trial records each returned a relevant trial first. Literal word matching averaged 0.67 reciprocal rank. On a separate fictional cohort, two study/city pairs and two registry follow-ups were queued. |
| [Manufacturing maintenance](verticals/manufacturing/README.md) | Score machine condition, allocate inspection slots, draft work orders with sensor evidence. | On the public UCI AI4I synthetic benchmark, 300 reviews found 37 of 55 labeled failures versus 26 by tool wear. The model also sent 263 false alerts. Of the 37 captured failures, 32 draft categories matched a recorded label. |
| [Electricity demand](verticals/energy/README.md) | Forecast 24 hourly loads, flag peak hours, schedule a flexible three-hour load. | On a national-lab office load profile, the final 336 hours gave a forecast MAE of 88.6 kW versus 32.5 kW for the same hour last week. Shifting an identical load cut the average daily peak by 3.3 kW versus a fixed 17:00 start. The profile is modeled and has an illustrative calendar. |

## Why these three

- **Clinical operations.** The NCBI TrialGPT team published code for retrieving, matching and ranking trials. Registry search gives an analyst a verifiable artifact early in a pilot. Relevance can be scored by rank and each factual hit can link back to its study. [NCBI TrialGPT](https://github.com/ncbi-nlp/TrialGPT)
- **Manufacturing maintenance.** Microsoft's public manufacturing project connects predictive maintenance to a review workflow. With a fixed number of inspections, a team can measure how many failures it captures and how many false alerts consume its slots. [Microsoft predictive maintenance project](https://github.com/microsoft/pdm-fabric-foundry) · [UCI AI4I benchmark](https://doi.org/10.24432/C5HS5C)
- **Energy operations.** The national lab maintains a short-term load forecasting benchmark and publishes building load profiles for optimization. Hourly inputs make it possible to compare a forecast against a seasonal baseline, then replay the scheduling decision at equal energy. [BuildingsBench](https://github.com/NatLabRockies/BuildingsBench) · [REopt.jl](https://github.com/NatLabRockies/REopt.jl)

The selection reflects public engineering activity and the availability of measurable workflows. Market-share rankings, customer deployments and plant or clinical outcomes would require different evidence. The implementations use retrieval, statistical learning and explicit operational rules. They run on a CPU without paid model calls.

## Data, checks and license

The guides distinguish bundled fixtures from downloaded benchmarks and give commands to replay public data. Local inputs and full generated reports can be kept in `local-data/` and `output/`. The MIT license covers the original code and fixtures. See the guides for third-party attribution and source terms.

```sh
python -m unittest discover -s verticals/pharma -v
python -m unittest discover -s verticals/manufacturing -v
python -m unittest discover -s verticals/energy -v
```
