# Sources and licenses

The task graph uses the upstream PocketFlow Node and Flow implementation. The bundled copy is pinned to commit `f74d023f93607b8c3268133339a5e532a949898c`. Its source blob is `0b71858bfb9c0d8d02c5eb0b692d8b788af342e3`. The MIT copyright notice credits Zachary Huang. [Upstream source](https://github.com/The-Pocket/PocketFlow/blob/f74d023f93607b8c3268133339a5e532a949898c/pocketflow/__init__.py) · [Bundled license](industry_agent/vendor/pocketflow/LICENSE)

The website distributes the Pyodide 0.27.7 core runtime under the Mozilla Public License 2.0, with the accompanying component notices where supplied in the distribution. The build verifies the upstream core archive SHA-256 before extracting it. Source for the bundled runtime is available at its release tag. [Upstream source and release](https://github.com/pyodide/pyodide/releases/tag/0.27.7) · [License](licenses/Pyodide-MPL-2.0.txt) · [CPython license](https://docs.python.org/3/license.html)

Each industry guide describes the datasets, source revisions and reuse terms. The bundled clinical projection credits NCBI's TrialGPT. [Clinical data](verticals/pharma/README.md) · [Manufacturing data](verticals/manufacturing/README.md) · [Energy data](verticals/energy/README.md)
