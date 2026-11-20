# Machine maintenance review

A reliability team has 25 new machine observations and time to inspect three. This harness ranks the batch, assigns the three review slots and gives the analyst a work-order draft with the sensor readings behind its suggested category. One command runs the whole workflow on a CPU with Python 3.11+ and the standard library.

```sh
python verticals/manufacturing/harness.py > maintenance-review.json
python -m unittest discover -s verticals/manufacturing -p 'test_*.py'
```

## Workflows and measured results

The default workload contains 4,000 original synthetic observations (seed 20261120). The first 3,000 fit the models. The last 1,000 supply 40 consecutive batches for evaluation, with 161 labeled failures. Each observation carries a contemporaneous outcome. A batch represents 25 records available together, and its reviewer gets the whole batch before making a selection.

| Stage and caller | What the caller gets | Offline result |
| --- | --- | --- |
| Condition monitoring · reliability engineer | Machine observations ranked by sensor-based failure score. The incumbent orders records by tool wear alone. | Average precision 0.677 vs 0.333 for tool wear. Failure prevalence was 0.161. |
| Inspection planning · maintenance planner | Three ranked observation IDs per batch, breaking ties by source order. | 79 failures in 120 reviews vs 28 at identical capacity for wear alone. There were 41 false alerts and 82 missed failures. |
| Work-order drafting · maintenance analyst | One proposed failure category with up to two supporting readings per selected record. | Of 79 selected records with failure labels, 75 had at least one matching category. All 120 drafts require human review, including the 41 false alerts. |

For example, the first batch puts observation 3022 first. Its draft suggests a power-related issue and cites a calculated mechanical power of 8.116 kW. The JSON includes the other 119 drafts. Match the record ID, batch, rank, suggested category and evidence fields to a maintenance review inbox. The harness makes no equipment changes.

## How evaluation works

The model is a histogram naïve Bayes ranker. It fits quantile boundaries, failure prevalence and smoothed likelihoods on the training prefix. Its five inputs are temperature gap, rotation speed, mechanical power, wear × torque and tool wear. Correlated features can amplify a score, so the output exposes a ranking score. Each diagnostic model learns one labeled failure mode versus all other training observations. The strongest positive feature contributions provide traceable readings for a reviewer. The training labels, including the five mode flags, are excluded from inference.

Average precision groups ties at each distinct score. The queue comparison uses exactly the same local review budget for both policies. The evidence-stage denominator includes every captured failure, including unexplained/random failures, and accepts any tagged cause on a multilabel record. It does not measure root-cause accuracy across all machines. The simulator deliberately includes random failures and overlapping conditions. These data measure the review workflow, with no measured fault lead time, prevented downtime, repair cost or plant safety outcome.

The engineering motivation extends beyond this simulator. Anomalib is an active open-source industrial anomaly-detection project. On 2026-11-20 its repository reported 6,412 stars and a last push on 2026-11-19. This is a signal of public engineering interest in industrial inspection. Adoption and comparative market size require separate evidence. [Anomalib repository](https://github.com/open-edge-platform/anomalib)

## Optional UCI workload

The alternative input is Stephan Matzka's *AI4I 2020 Predictive Maintenance Dataset*, UCI Machine Learning Repository (2020), DOI 10.24432/C5HS5C, licensed CC BY 4.0. UCI describes it as synthetic. The default simulator is original and includes no UCI rows. The following commands fetch the canonical ZIP, validate its CSV format and 10,000-row count, and print hashes of the exact download. Run them from the repository root. [UCI dataset](https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset) · [License](https://creativecommons.org/licenses/by/4.0/)

```sh
python verticals/manufacturing/fetch_ai4i.py ./ai4i-data
python verticals/manufacturing/harness.py --data-dir ./ai4i-data > ai4i-review.json
```

On 2026-11-20 we ran all three workflows against two public copies of AI4I. Both contain 10,000 observations, 14 fields and 339 failures, in continuous UDI order. The first 7,500 observations fit the models, and the final 2,500 contain 55 failures. UDI supplies source order without an asset timestamp.

| Public benchmark result | Model | Wear-only baseline |
| --- | ---: | ---: |
| Average precision | 0.4033 | 0.1800 |
| Failures captured in 300 reviews | 37 of 55 | 26 of 55 |
| Other records sent for review | 263 | 274 |
| Failures outside the queue | 18 | 29 |

Among the 37 captured failures, 32 draft work orders suggested a category present in the recorded labels. The model found 11 additional failures using the same 300 review slots. Its queue contained about seven false alerts per captured failure on this public synthetic benchmark.

The original UCI archive was unreachable during verification. We compared all 140,000 fields across two mirror files. Exactly 935 process-temperature strings differed in decimal notation, e.g. `309.0` and `309`. All field values agreed after numeric parsing, and both runs produced identical scores, queues, draft evidence and metrics. A third public repository references the second file's Git blob. For the measured input, the helper verifies the pinned mirror SHA-256 before writing the CSV.

```sh
python verticals/manufacturing/fetch_ai4i.py ./ai4i-mirror --mirror
python verticals/manufacturing/harness.py --data-dir ./ai4i-mirror > ai4i-review.json
```

| Verified mirror and revision | CSV SHA-256 |
| --- | --- |
| [Pendeteksi-Mesin-Halu, e0bfb97](https://github.com/Pendeteksi-Mesin-Halu/predictive-maintenance-ai4i2020/blob/e0bfb9786b07e250fc743c14f1db818e2f72e3dd/data/ai4i2020.csv) | `1dcd9c32543beb77921a24c18d79525e698c8b055e85b3320486b427e79f5b1f` |
| [Edoar-do, 279c6d3](https://github.com/Edoar-do/AI4I-Predictive-Maintenance/blob/279c6d303c98f713e14df001561cc3e80d2b4d22/ai4i2020.csv) and [rockyfjord, 789f44a](https://github.com/rockyfjord/predictive-maintenance/blob/789f44a7336f173cea4d4879fb61993db0d42fdf/maintenance.csv) | `dc6630cd9b1f0f853922fad78a1b6436570d3f1ec863f1dd5c4340ac56bc8a8e` |
