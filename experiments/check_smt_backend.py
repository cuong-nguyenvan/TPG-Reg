"""Check the Z3 backend against the enumeration backend on every version
of the benchmark policy sets (original and all single-edit evolutions): the
interaction edges must be identical, and Z3 witnesses must satisfy their
obligations when evaluated by the PDP.

Usage: python3 check_smt_backend.py <out dir>
Output: smt_backend_equivalence.json
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".."))

import json, sys, time
import numpy as np
from tpgreg.policy_model import Grid, evaluate
from tpgreg.benchmarks import DATASETS
from tpgreg.mutation import evolutions
from tpgreg.typed_policy_graph import TPG
from tpgreg.smt_backend import SMTTPG, Encoder, Batch, solve

OUT = sys.argv[1] if len(sys.argv) > 1 else "../results/validation"
import os; os.makedirs(OUT, exist_ok=True)
res = {}
for name, (mk, dom) in DATASETS.items():
    G = Grid(dom)
    ps1 = mk()
    versions = [ps1] + [e["ps"] for e in evolutions(ps1, dom)]
    same = diff = q = pr = 0
    t_enum = t_smt = 0.0
    wit_ok = wit_n = 0
    rng = np.random.default_rng(0)
    for k, ps in enumerate(versions):
        t0 = time.perf_counter(); ev = evaluate(ps, G); g = TPG(ps, G, ev); t_enum += time.perf_counter() - t0
        t0 = time.perf_counter(); s = SMTTPG(ps, dom); t_smt += time.perf_counter() - t0
        q += s.queries; pr += s.pruned
        e1 = {e for e in g.edges if e[0] in ("precedes", "overrides")}
        if e1 == s.edges:
            same += 1
        else:
            diff += 1
        if k % 10 == 0:   # witness check on a subsample of versions
            for pol in ps.policies:
                for r in pol.rules:
                    sols = solve(s.enc, s.app[r.id], rng, k=1)
                    if sols:
                        B = Batch(dom, sols)
                        wit_n += 1
                        wit_ok += bool(evaluate(ps, B).app[r.id][0])
    res[name] = {"versions": len(versions), "edges_identical": same, "edges_differ": diff,
                 "smt_queries": q, "prefilter_pruned": pr, "t_enum_s": t_enum, "t_smt_s": t_smt,
                 "witness_checked": wit_n, "witness_valid": wit_ok}
    print(name, res[name], flush=True)
json.dump(res, open(f"{OUT}/smt_backend_equivalence.json", "w"), indent=1)
