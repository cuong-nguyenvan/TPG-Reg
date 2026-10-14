# TPG-Reg

**Change-impact-driven regression testing for evolving XACML policies, based on Typed Policy Graphs.**

Given two versions of an XACML policy set and the declared intent of the change, TPG-Reg

1. builds a **Typed Policy Graph** (TPG) for each version, with derived edges (`overrides`, `precedes`, `refers`)
   between rules that can interact;
2. matches the two graphs by XACML identifiers and computes the **Behavioral Impact Set** (BIS), the rules whose
   decisions the edit can change;
3. generates a small regression suite inside the BIS (decisive, interaction and difference witnesses, optionally
   distinguishing requests: `TPG-Reg+D`);
4. runs it on both versions and classifies each changed decision as **intended** or **regression**.

## Main results

363 behaviour-changing single-edit evolutions of three benchmark policy sets (HACS, FMS, SIS), seeds 1–5:

| Method | Evolutions detected | Tests per evolution |
|---|---:|---:|
| Flow-graph suite, GA-minimised (Retest-all) | 51.7 % | 15.7 |
| Syntactic difference (AST-Up) | 58.9 % | 1.8 |
| **TPG-Reg** | **91.8 %** | **12.8** |
| **TPG-Reg+D** | **100 %** | **13.3** |

The BIS contained all 1,012 affected-rule instances, and the intent oracle flagged 97.0 % of commits with an
undeclared edit without false alarms. Full results: [`results/REPORT.md`](results/REPORT.md).

## Installation and quick start

```bash
git clone https://github.com/cuong-nguyenvan/TPG-Reg.git && cd TPG-Reg
python3 -m pip install -r requirements.txt   # numpy, scipy, matplotlib, z3-solver (tested with Python 3.13)
```

```python
import numpy as np
from tpgreg.policy_model import Grid
from tpgreg.benchmarks import fin, FIN_DOM
from tpgreg.typed_policy_graph import TPG
from tpgreg.impact_analysis import diff_bis
from tpgreg.test_generation import tpg_obligations, minimise

G = Grid(FIN_DOM)
g1, g2 = TPG(fin("DO", 5), G), TPG(fin("FA", 5), G)     # deny-overrides -> first-applicable
changed, bis, container_seeds, followed = diff_bis(g1, g2)
use = ("precedes", "overrides", "scopes", "refers")
suite = minimise(tpg_obligations(g1, g2, changed, bis, container_seeds, followed, use),
                 np.random.default_rng(1))
print(sorted(bis), [G.request(q) for q in suite])        # ['M.R1', 'M.R2'] and 3 tests
```

## Reproducing the experiments

```bash
./run_all.sh          # all experiments (about 1 hour on 2 cores)
./run_all.sh --fast   # without scalability study and PDP cross-check (about 5 minutes)
```

Results are deterministic (fixed seeds, `PYTHONHASHSEED=0`) except for timings; pre-computed results are in `results/`.

## Repository layout

```
tpgreg/        library: policy model and PDP, TPG, impact analysis, test generation,
               baselines, Z3 backend, mutation operators, benchmarks, XACML export
experiments/   one script per experiment (impact analysis, detection, intent oracle,
               scalability, PDP cross-check, report)
results/       pre-computed results, logs, tables and REPORT.md
third_party/   ndg-xacml 0.5.1 ported to Python 3 (BSD licence), used as independent PDP
```

## Limitations

- Supports deny-overrides, permit-overrides and first-applicable; Indeterminate, obligations and advice are not modelled.
- Benchmark policies were written for this study; large scalability policies are synthetic.
