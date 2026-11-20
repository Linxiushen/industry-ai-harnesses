# Clinical trial operations

A clinical operations team can use the harness to find related studies, identify recruiting locations to contact, and prioritize registry records for follow-up. Run the demo offline with Python 3.11 or newer from this directory.

```sh
python harness.py
python -m unittest discover -s . -p test_pharma.py -v
```

Search uses the first 12 historical studies in the public NCBI TrialGPT SIGIR corpus. Each hit links to its ClinicalTrials.gov record. The two operational queues use a separate January 15, 2025 snapshot of 12 fictional studies with IDs beginning with `SIM-`. Each scenario in the JSON output identifies its dataset.

| Workflow | Typical caller and decision | Method | Bundled result |
| --- | --- | --- | --- |
| Trial landscape search | A clinical intelligence analyst enters a condition or abbreviation and opens related studies. | BM25 over condition names with four explicit abbreviation expansions. Each hit carries its matched terms, indication and phase when available. | Six positive queries gave MRR@3 of 1.00. Literal token overlap gave 0.6667. “COPD” returned NCT00440687. The seventh query, “migraine”, returned no hits. |
| Recruiting location shortlist | A feasibility coordinator checks which study/city pairs merit a call to confirm site capacity. | Require recruiting status at both levels, matching country, city, and a study update within 180 days. Deduplicate study/city pairs. | Boston (SIM-01) and Chicago (SIM-02) qualified. Two more records need manual verification because of missing site status or a stale registry update. |
| Registry reporting follow-up | A registry operations lead prioritizes completed studies for correspondence. | When the registry explicitly reports no posted results, order records by days since actual primary completion. Use a configurable internal threshold of 365 days. | SIM-10 and SIM-03 enter the queue in that order. A month-only date and an estimated completion date require manual review. |

The six positive search queries and their relevant IDs are project-authored and stored in `data/questions.json` independently of the ranker. MRR@3 averages the reciprocal position of the first relevant study in the first three hits, with zero for a miss. Two of the six queries are abbreviations included in the dictionary. The observed difference measures the combined ranker and dictionary on this small demonstration. A representative search log and independent judgments would be needed to measure generalization. Capacity, patient eligibility and legal reporting obligations each require information beyond this registry projection.

## Why these workflows

TrialGPT, a 2024 project by the NCBI NLP research team and collaborators, describes trial retrieval as the first stage of its matching workflow. Researchers can inspect the public code and evaluation assets. It establishes a concrete research use for trial search. The cohort and metrics here are specific to this repository. Site screening and registry follow-up are proposed operations workflows that use the registry's location, recruitment and reporting fields. This evidence does not measure market share or customer adoption. [TrialGPT project and paper](https://github.com/ncbi-nlp/TrialGPT)

## Using a public registry cohort

ClinicalTrials.gov is maintained by the U.S. National Library of Medicine. From this directory, the following commands request selected study IDs from its free API and then process the saved file offline. Use a new output directory for each snapshot. [API documentation](https://clinicaltrials.gov/data-api/about-api) · [Registry terms](https://clinicaltrials.gov/policy/terms-conditions)

```sh
python fetch_registry.py --output local-cohort/registry.json NCT01720446
python harness.py --data-dir local-cohort
```

The importer accepts up to 25 chosen IDs. It saves study and API URLs, UTC retrieval timestamps and SHA-256 hashes of the returned payloads with selected registry fields. For example, an operator reviewing a stale site can follow its study link and compare the last posted update with the saved snapshot. The importer omits names, contact details and free-text descriptions. Its field projection and handling of missing flags have offline regression tests. The live registry endpoint was unreachable during preparation on November 20, 2026. The bundled search records were retrieved from the NCBI research archive on that date.

The historical search projection preserves only the NCT identifier, archived condition names and phase from the first 12 rows of the corpus. A blank phase is stored as an empty list. To verify every bundled field, run `python verify_trialgpt.py` with public GitHub access or pass the path to an original downloaded `corpus.jsonl`. It checks the Git blob hash and rebuilds the projection. The source revision was committed on January 24, 2025. Current recruitment status requires a fresh registry read. [Frozen corpus](https://github.com/ncbi-nlp/TrialGPT/blob/1b3242cd50c153a9c324661d4a0bd94fc68a4226/dataset/sigir/corpus.jsonl)

The repository license covers the original synthetic fixtures, query labels and code. The TrialGPT distribution carries an NCBI public-domain notice and requests citation of Qiao Jin, Zifeng Wang, Charalampos S. Floudas, Fangyuan Chen, Changlin Gong, Dara Bracken-Clarke, Elisabetta Xue, Yifan Yang, Jimeng Sun and Zhiyong Lu, *Matching Patients to Clinical Trials with Large Language Models*. ClinicalTrials.gov's terms apply to downloaded registry records. Retain attribution, identifiers, links and dates when reusing a cohort. [NCBI public-domain notice](https://github.com/ncbi-nlp/TrialGPT/blob/1b3242cd50c153a9c324661d4a0bd94fc68a4226/LICENSE)

For a custom cohort, add `questions.json` next to `registry.json` with entries such as `{"query":"CKD","relevant":["your-cohort-study-id"]}`. Omit `relevant` to run unlabeled queries. An empty relevance list declares a no-match query. With no question file the harness runs three illustrative queries and omits rank-quality estimates. The snapshot is small enough to score exhaustively. A registry-wide integration would cache the condition index and refresh changed records incrementally.
