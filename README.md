# TPG-Reg
 
**Change-impact-driven regression testing for evolving XACML policies, based on Typed Policy Graphs.**
 
An edit to one rule of an XACML policy can change decisions that are governed by *other* rules: a raised limit can
unblock requests another rule was meant to deny, and a combining algorithm switched "for readability" can grant
access that was refused before. Such regressions are invisible in a textual diff.
 
Given two versions of a policy set and the declared intent of the change, TPG-Reg answers three questions for every
commit: **which** decisions can change, **whether** they did, and **whether** the change was intended.
 
---
 
## How it works
 
```
 Policy v1 ─┐                                                              ┌─> Report: request, decision v1 → v2,
            ├─> TPG builder ─> ID-anchored diff ─> BIS closure ─> Witness ─┤   deciding rules,
 Policy v2 ─┘   (typed +        (changed nodes      (level-       obligations   verdict: intended / regression
                derived edges)  and edges)          monotone)     + greedy set cover
 Intent ────────────────────────────────────────────────────────────────────> run on PDP(v1), PDP(v2)
```
 
1. **Typed Policy Graph (TPG).** Each version becomes a graph with typed nodes (PolicySet, Policy, Rule, Target,
   Condition, CombAlg, VarDef, Attribute), four syntactic edge types (`contains`, `scopes`, `combinedBy`, `reads`)
   and three **derived** edge types between rules that can actually interact:
   `overrides` (opposite effects, overlapping, combined by deny- or permit-overrides),
   `precedes` (opposite effects, overlapping, first-applicable order) and
   `refers` (a condition uses a variable). Overlap is decided by a syntactic filter, then by enumeration or Z3.
2. **Difference.** Nodes are matched by their XACML identifiers (`PolicyId`, `RuleId`, `VariableId`); added,
   deleted and relabelled nodes and changed interaction edges give the set of changed rules. Positions are not
   labels, so reordering children of deny- or permit-overrides containers produces no change.
3. **Behavioral Impact Set (BIS).** The changed rules are closed over interaction edges with a *level-monotone*
   closure (an edge inside a policy may be followed by an edge between policies, not vice versa). Every rule that
   decides a changed request lies in the BIS (checked empirically on all benchmark evolutions).
4. **Test generation.** For the rules of the BIS, TPG-Reg derives obligations — *decisive* witnesses (the rule
   applies and no competitor does), *isolation* witnesses, *interaction* witnesses for the followed edges,
   *difference* witnesses for edited targets and conditions and, optionally, *distinguishing* requests on which
   the two versions disagree (`TPG-Reg+D`). Greedy set cover selects a small suite.
5. **Change-aware oracle.** Every test is executed on both versions. Each changed decision is reported with its
   deciding rules and classified as **intended** (a deciding rule lies in the scope of the declared edit) or
   **regression** (otherwise, or always for a declared refactoring).
---
 
## Main results
 
Three benchmark policy sets (HACS, FMS, SIS; 20–30 rules each, request spaces small enough for exhaustive ground
truth), 462 single-edit evolutions of which 363 change behaviour, seeds 1–5:
 
| Method | Evolutions detected | Affected rules exposed | Tests per evolution |
|---|---:|---:|---:|
| Re-run flow-graph suite, GA-minimised (Retest-all) | 51.7 % | 36.9 % | 15.7 |
| Regenerate flow-graph suite, GA-minimised (XFG-Regen) | 38.8 % | 27.9 % | 15.4 |
| Syntactic difference with upward propagation (AST-Up) | 58.9 % | 31.5 % | 1.8 |
| **TPG-Reg** | **91.8 %** | **65.8 %** | **12.8** |
| **TPG-Reg+D** (with distinguishing requests) | **100 %** | **98.1 %** | **13.3** |
 
- **Impact analysis:** the BIS contained all 1,012 affected-rule instances (recall 100 %, precision 27.6 %);
  removing any derived edge type loses affected rules.
- **Oracle:** the path-based oracle was wrong for 8–18 % of its tests; decisive witnesses were never wrong.
- **Intent oracle:** on 240 two-edit commits, TPG-Reg+D flagged 97.0 % of commits with an undeclared side edit
  and raised no false alarm on clean commits.
- **Scalability (Z3 backend):** building the TPG of an 800-rule policy set takes about 3 s; the impact set
  becomes imprecise when policies overlap widely.
- **Validation:** the built-in PDP agreed with the independent PDP ndg-xacml on all 552,556 requests checked.
All numbers are in [`results/REPORT.md`](results/REPORT.md) and [`results/tables/`](results/tables/).
 
---
 
## Installation
 
```bash
git clone https://github.com/cuong-nguyenvan/TPG-Reg.git
cd TPG-Reg
python3 -m pip install -r requirements.txt   # numpy, scipy, matplotlib, z3-solver
```
 
Tested with Python 3.13 on Linux.
 
## Quick start
 
```python
import numpy as np
from tpgreg.policy_model import Grid
from tpgreg.benchmarks import fin, FIN_DOM
from tpgreg.typed_policy_graph import TPG
from tpgreg.impact_analysis import diff_bis
from tpgreg.test_generation import tpg_obligations, minimise
 
G = Grid(FIN_DOM)                                   # finite request space of the example
g1 = TPG(fin("DO", 5), G)                           # version 1: deny-overrides
g2 = TPG(fin("FA", 5), G)                           # version 2: first-applicable ("refactoring")
changed, bis, container_seeds, followed = diff_bis(g1, g2)
 
use = ("precedes", "overrides", "scopes", "refers") # derived / scoping edges to follow
suite = minimise(tpg_obligations(g1, g2, changed, bis, container_seeds, followed, use),
                 np.random.default_rng(1))
 
print(sorted(bis))                                  # ['M.R1', 'M.R2']
print([G.request(q) for q in suite])                # 3 regression tests
```
 
A complete walk-through of two commits on this policy, including the intent oracle, is in
`experiments/demo_finance_example.py` (output: [`results/finance_example/output.txt`](results/finance_example/output.txt)).
 
---
 
## Reproducing the experiments
 
```bash
./run_all.sh          # everything (about 1 hour on 2 cores)
./run_all.sh --fast   # without the scalability study and the PDP cross-check (about 5 minutes)
```
 
`PYTHONHASHSEED=0` and fixed NumPy seeds make all results reproducible exactly, except for timings.
Pre-computed results are already in `results/`.
 
| Question | Script | Results |
|---|---|---|
| Does the BIS contain every affected rule? Edge-type ablation | `exp_single_edit_evolution.py`, `summarize_single_edit.py` | `results/single_edit_evolution/` |
| How many behavioural changes do the suites detect? | same | `summary.txt`, `detection_rates.png` |
| Are the differences significant? | `significance_tests.py` | `significance_tests.txt` |
| Are expected decisions correct? (path-based vs. decisive witness) | `exp_single_edit_evolution.py` | `policy_statistics.json` |
| Does the intent oracle separate clean and dirty commits? | `exp_two_edit_commits.py` | `results/two_edit_commits/` |
| Does it scale with Z3? (50–800 rules) | `exp_scalability.py` | `results/scalability/` |
| Is the Z3 backend equivalent to enumeration? | `check_smt_backend.py` | `results/validation/` |
| Is the built-in PDP correct? (vs. ndg-xacml) | `check_pdp_conformance.py` | `results/validation/` |
| Concrete regression tests and impact sets | `export_regression_suites.py` | `results/regression_suites/` |
| Policies as XACML XML | `export_xacml_policies.py` | `results/xacml_policies/` |
| All tables and one report | `build_report.py` | `results/REPORT.md`, `results/tables/` |
 
---
 
## Repository layout
 
```
TPG-Reg/
├── tpgreg/                      # the library
│   ├── policy_model.py          # PolicySet / Policy / Rule, vectorised PDP (DO, PO, FA), decisive rules
│   ├── typed_policy_graph.py    # Typed Policy Graph: typed nodes, syntactic and derived edges
│   ├── impact_analysis.py       # identifier-anchored difference, level-monotone BIS closure
│   ├── test_generation.py       # witness obligations, greedy set-cover minimisation
│   ├── baselines.py             # AST-Up; flow-graph suites with greedy or GA minimisation
│   ├── smt_backend.py           # Z3 encoding, overlap queries, witness solving
│   ├── mutation.py              # single-edit operators CCF, CRE, RDL, RRO, CAC, RAI, PTC, VDC, PRO
│   ├── benchmarks.py            # HACS, FMS, SIS and the two-rule financial example
│   └── xacml_export.py          # export to XACML 2.0 XML
├── experiments/                 # one script per experiment (see table above)
├── results/                     # pre-computed results, logs and REPORT.md
├── third_party/ndg_xacml_py3/   # ndg-xacml 0.5.1 ported to Python 3 (independent PDP)
├── run_all.sh
└── requirements.txt
```
 
### Edit operators
 
| Operator | Edit | Operator | Edit |
|---|---|---|---|
| CCF | rule target or condition changed | RAI | rule inserted |
| CRE | rule effect inverted | PTC | policy target changed |
| RDL | rule deleted | VDC | variable definition changed |
| RRO | rules reordered | PRO | policies reordered |
| CAC | combining algorithm changed | | |
 
---
 
## Scope and limitations
 
- The PDP covers XACML 3.0 **deny-overrides, permit-overrides and first-applicable** at policy-set and policy
  level, with targets, conditions and variables. **Indeterminate, obligations and advice are not modelled.**
- The benchmark policy sets were written for this study to mirror the domains and sizes of published XACML test
  subjects; the large policies of the scalability study are synthetic. Results on real policy histories may differ.
- On policies whose rules overlap widely, the BIS can approach the whole policy; distinguishing requests
  (`TPG-Reg+D`) keep detection complete at the cost of more solver calls.
- For 800-rule policies only the analysis (TPG, difference, BIS) was run, not test generation.
## Third-party code
 
`third_party/ndg_xacml_py3` is **ndg-xacml 0.5.1** (BSD licence, P. J. Kershaw, STFC), converted to Python 3 with
`fissix` plus a manual replacement of `UserDict.DictMixin`; 115 of its 125 unit tests pass (the failures concern
XPath attribute selectors and an MD5 extension function). For the cross-check, variables are inlined, `or` is
rewritten with De Morgan's law and integer comparisons are expanded into equalities over the finite domain,
because ndg-xacml implements none of these.
 
