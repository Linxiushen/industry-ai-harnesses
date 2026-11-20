# Electricity demand and flexible-load operations

At midnight a demand planner needs an hourly forecast, an operator needs to know which hours deserve a peak watch, and a charging operator needs three consecutive hours before a deadline. This harness feeds all three decisions from the same information available at midnight, then scores them against the next 24 observations. Python 3.11+ and the standard library are sufficient.

Day-ahead forecasts have a public operational counterpart. U.S. balancing authorities supply demand and demand forecasts through the EIA-930 program. Energy optimization also has a public engineering toolchain. The national laboratory's REopt model includes the 8,760-hour office load profile used in the reference run below. In its April 2025 *Energy and AI* report, the IEA discusses AI applications to electricity forecasting and grid operations. These sources motivate the use cases. [EIA hourly grid monitor](https://www.eia.gov/electricity/gridmonitor/) · [REopt reference input](https://github.com/NatLabRockies/REopt.jl/blob/35abb019e29532ef45d4a61c8dcecd2b8cdb74da/test/data/loads_kw_largeoffice_sanfran.csv) · [IEA report](https://www.iea.org/reports/energy-and-ai)

Run these commands from this directory. The first command emits each day's 24 predictions, flagged hours and proposed start/end times together with metrics and hashes.

```shell
python harness.py
python -m unittest -v test_energy
python fetch_reopt.py office-data
python harness.py --data-dir office-data
```

The default is an original, seeded 84-day synthetic system with day-level demand shocks, independent hourly noise, and weekday/weekend usage patterns. For a public reference, the third command fetches the pinned REopt data and checks its Git blob hash. Add `--input /path/to/loads_kw_largeoffice_sanfran.csv` to prepare an existing download offline. REopt supplies modeled kW demand with no timestamps. The converter divides kW by 1,000 and assigns the first row to Sunday, January 1, 2017 on an illustrative fixed-hour calendar. Fields labelled UTC in that replay are indices on this assumed calendar. Dates and daily peaks from the replay do not describe measurements at a particular building.

| Operational output | Method and decision rule | Evaluation |
| --- | --- | --- |
| Next 24 hourly loads, in MW | Learn mean hourly profiles for weekdays and weekends. Fit a least-squares coefficient on prior-day hourly deviations from these profiles. | Mean absolute error (MAE) against prior-day and prior-week persistence. |
| Hours for peak watch | Define an event as load at or above the training 90th percentile. Select the alert margin on 14 calibration days by F1. | Count hits, false alarms and missed hours. Undefined precision, recall and F1 serialize as JSON null. |
| Start/end time for one flexible load | Add a block drawing 12% of median training demand. Enumerate starts from 15:00 to 20:00. Use three consecutive slots and finish by 23:00. Minimize forecast daily peak, then mean underlying block demand, then start time. | Compare realized daily peak with a fixed 17:00 start at identical power and energy. Count days made worse. |

The final 14 days form the test window. The preceding 14 days calibrate the alert margin. All earlier days train the forecasting model and establish the peak threshold. The model stays frozen throughout calibration and testing. At each decision it can use the entire preceding day's load. Deployments with meter reporting delays would need to move that cutoff.

| Held-out result, 336 hours per series | REopt large office | Synthetic system, seed 4163 |
| --- | ---: | ---: |
| Forecast MAE | 88.6 kW | 4.0316 MW |
| Prior-day / prior-week MAE | 117.3 / **32.5 kW** | 4.1429 / 5.6028 MW |
| Peak watch, hits / false alarms / missed hours | 0 / 0 / 0 | 15 / 12 / 1 |
| Peak watch precision / recall | Undefined / undefined | 55.56% / 93.75% |
| Mean daily peak, planned / fixed start | 838.5 / 841.8 kW | 99.4776 / 107.3236 MW |
| Mean peak reduction at identical energy | 3.3 kW | 7.8461 MW |

The REopt profile favoured the simple weekly forecast. Its last two weeks had zero threshold crossings, so they provide no estimate of alert sensitivity. The scheduling comparison replays a hypothetical incremental block. It establishes feasibility for one load and one daily deadline. Coordinating fleets would require distinguishing feeders, enforcing capacity and departure constraints, and measuring actual response.

The verified REopt source SHA-256 is `96382ee6e2cbed628ee8ccc20d0cb6af2a10aa8722ed91113ec6dce60371d050`. Its normalized CSV SHA-256 is `c1955d24fa5cea359605cf4f2a72b2dfff34477ba3a8637bbdfc7ce0fbc486fe`. The importer saves the upstream attribution, revision and hashes next to the CSV. This repository includes the importer and reported aggregate results. The upstream source and applicable notices are available from the [REopt.jl repository](https://github.com/NatLabRockies/REopt.jl/tree/35abb019e29532ef45d4a61c8dcecd2b8cdb74da).

**Optional measured regional load.** With a free `EIA_API_KEY` in your environment, run `python fetch_eia.py pjm-data --region PJM --start 2024-04-01 --days 84`, then `python harness.py --data-dir pjm-data`. The importer checks the respondent, units, continuous coverage and duplicates. It converts hourly MWh to average MW and hour-ending timestamps to interval starts. The EIA parser was tested offline on constructed API records. The live EIA endpoint was inaccessible during this release, so the table contains no EIA measurements. [EIA Open Data and key registration](https://www.eia.gov/opendata/) · [EIA terms of reuse](https://www.eia.gov/about/copyrights_reuse.php)

To bring your own series, supply a directory containing `load.csv` with columns `interval_start_utc,load_mw`. Use UTC hours such as `2024-04-01T00:00Z`, nonnegative finite MW, and at least 42 consecutive full days starting at midnight. If the directory includes `provenance.json` with `csv_sha256`, the harness checks it before replay.
