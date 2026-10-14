# TPG-Reg

**Change-impact-driven regression testing for evolving XACML policies based on Typed Policy Graphs.**

Given two versions of an XACML policy set, TPG-Reg builds a *Typed Policy Graph* (TPG) for each version,
computes an identifier-anchored difference and a *Behavioral Impact Set* (BIS) — the rules whose decisions an
edit can influence — and generates a small regression test suite inside the BIS. Each changed decision is
reported with the rules that decide it and classified as *intended* or *regression* with respect to the
declared intent of the change.

> **Tiếng Việt.** TPG-Reg là bộ công cụ kiểm thử hồi quy cho chính sách XACML khi chính sách thay đổi:
> dựng đồ thị chính sách có kiểu (TPG) cho hai phiên bản, tính tập tác động hành vi (BIS) và sinh bộ test
> hồi quy trong BIS. Thư mục `tpgreg/` là thư viện, `experiments/` là các chương trình thực nghiệm,
> `results/` là kết quả đã chạy (xem `results/REPORT.md`). Chạy lại toàn bộ: `./run_all.sh`
> (≈1 giờ trên 2 nhân) hoặc `./run_all.sh --fast` (≈5 phút, bỏ qua thực nghiệm khả năng mở rộng và
> kiểm tra tương thích PDP).

## Installation

```bash
python3 -m pip install -r requirements.txt     # numpy, scipy, matplotlib, z3-solver (Python >= 3.11)
```

## Usage as a library

```python
import numpy as np
from tpgreg.policy_model import Grid
from tpgreg.benchmarks import fin, FIN_DOM
from tpgreg.typed_policy_graph import TPG
from tpgreg.impact_analysis import diff_bis
from tpgreg.test_generation import tpg_obligations, minimise

G = Grid(FIN_DOM)
g1, g2 = TPG(fin("DO", 5), G), TPG(fin("FA", 5), G)        # version 1 and version 2
changed, bis, container_seeds, followed = diff_bis(g1, g2)
use = ("precedes", "overrides", "scopes", "refers")
suite = minimise(tpg_obligations(g1, g2, changed, bis, container_seeds, followed, use),
                 np.random.default_rng(1))
print(sorted(bis), [G.request(q) for q in suite])
```

## Library (`tpgreg/`)

| Module | Content |
|---|---|
| `policy_model.py` | Policy model (PolicySet / Policy / Rule, targets, conditions, variables), vectorised PDP for deny-overrides, permit-overrides and first-applicable, decisive rules |
| `typed_policy_graph.py` | Typed Policy Graph: typed nodes, syntactic edges (contains, scopes, combinedBy, reads) and derived edges (refers, precedes, overrides) |
| `impact_analysis.py` | Identifier-anchored graph difference and Behavioral Impact Set (level-monotone closure) |
| `test_generation.py` | Test obligations (decisive, isolation, interaction and difference witnesses), greedy set-cover minimisation |
| `baselines.py` | AST difference with upward propagation; path-based flow-graph suites with greedy or genetic-algorithm minimisation |
| `smt_backend.py` | Z3 encoding of targets, conditions and decisions; overlap queries and witness solving for non-enumerable domains |
| `mutation.py` | Single-edit policy evolutions (CCF, CRE, RDL, RRO, CAC, RAI, PTC, VDC, PRO) |
| `benchmarks.py` | Benchmark policy sets HACS, FMS, SIS and a two-rule financial example |
| `xacml_export.py` | Export to XACML 2.0 XML |

## Experiments (`experiments/`)

| Program | What it does | Output (in `results/`) |
|---|---|---|
| `exp_single_edit_evolution.py` | All single-edit evolutions of the three benchmark sets, 5 seeds, all methods and edge-type ablations, exact ground truth by enumeration; oracle correctness | `single_edit_evolution/per_evolution_<SET>.json`, `policy_statistics.json` |
| `summarize_single_edit.py` | Detection rate, affected-rule exposure, suite sizes, BIS recall/precision, per edit operator, timings | `single_edit_evolution/summary.json`, `summary.txt` |
| `significance_tests.py` | Wilcoxon signed-rank, Vargha–Delaney A12, McNemar | `single_edit_evolution/significance_tests.json`, `.txt` |
| `plot_detection_rates.py` | Detection / exposure chart | `single_edit_evolution/detection_rates.png` |
| `exp_two_edit_commits.py` | Intent oracle on commits with and without an undeclared side edit | `two_edit_commits/per_commit.json`, `summary.json` |
| `exp_scalability.py` | Synthetic policies with 50–800 rules and integer domains [0, 10^6], Z3 backend, incremental TPG update | `scalability/runs_*.json` |
| `check_smt_backend.py` | Z3 backend vs. enumeration backend on every policy version | `validation/smt_backend_equivalence.json` |
| `check_pdp_conformance.py` | Prototype PDP vs. the independent PDP ndg-xacml (`third_party/`) | `validation/pdp_conformance.json` |
| `demo_finance_example.py` | Two commits on a two-rule financial policy | `finance_example/output.txt` |
| `export_regression_suites.py` | Concrete regression tests and impact sets of every evolution | `regression_suites/<SET>_regression_tests.csv`, `<SET>_impact_sets.csv` |
| `export_xacml_policies.py` | Policies as XACML 2.0 XML | `xacml_policies/*.xml` |
| `build_report.py` | All tables as CSV and one Markdown report | `REPORT.md`, `tables/*.csv` |

Run everything with `./run_all.sh` (or `./run_all.sh --fast`). `PYTHONHASHSEED=0` and fixed NumPy seeds make
all results reproducible exactly, except for timings.

## Notes

- The PDP covers XACML 3.0 deny-overrides, permit-overrides and first-applicable without Indeterminate,
  obligations or advice.
- `third_party/ndg_xacml_py3` is ndg-xacml 0.5.1 (BSD licence, P. J. Kershaw, STFC), converted to Python 3
  with `fissix` plus a manual replacement of `UserDict.DictMixin`; 115 of its 125 unit tests pass (the failures
  concern XPath attribute selectors and an MD5 extension function). For the conformance check, variables are
  inlined, `or` is written with De Morgan's law and integer comparisons are expanded into disjunctions of
  equalities over the finite domain, because ndg-xacml implements none of these.
- The scalability study runs only the analysis (no test generation) for 800 rules.
