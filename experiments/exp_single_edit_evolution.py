"""Single-edit evolution experiment.

For every benchmark policy set, all single-edit evolutions (mutation.py) are
generated; for each evolution and seed, the regression suites of all methods
(TPG-Reg, TPG-Reg+D, TPG-Reg without minimisation, edge-type ablations,
AST-Up, flow-graph suites with greedy or GA minimisation) are generated and
evaluated against the exact behavioural difference computed by enumeration.
Also measures the correctness of the path-based and decisive-witness oracles
on the original policies.

Usage: python3 exp_single_edit_evolution.py <out dir>
Output: per_evolution_<SET>.json, policy_statistics.json
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".."))

import json, time, os, sys
from collections import defaultdict
import numpy as np
from tpgreg.policy_model import Grid, evaluate, NA, P, D
from tpgreg.typed_policy_graph import TPG, INTER
from tpgreg.impact_analysis import diff_bis
from tpgreg.test_generation import tpg_generate, w1_mask, tpg_obligations, minimise, pick
from tpgreg.baselines import ast_diff, ast_generate, xfg_suite, xfg_min_suite, xfg_ga_suite
from tpgreg.benchmarks import DATASETS
from tpgreg.mutation import evolutions

SEEDS = [1, 2, 3, 4, 5]
FULL = ("precedes", "overrides", "scopes", "refers")
ABL = {"TPG-Reg": FULL,
       "-precedes": tuple(x for x in FULL if x != "precedes"),
       "-overrides": tuple(x for x in FULL if x != "overrides"),
       "-scopes": tuple(x for x in FULL if x != "scopes"),
       "-refers": tuple(x for x in FULL if x != "refers")}
OUT = sys.argv[1] if len(sys.argv) > 1 else "../results/single_edit_evolution"
os.makedirs(OUT, exist_ok=True)


def exposed(suite, diff, ev1, ev2, affected):
    s = np.asarray(suite, dtype=np.int64)
    if s.size == 0:
        return 0, False
    sd = s[diff[s]]
    if sd.size == 0:
        return 0, False
    n = 0
    for r in affected:
        hit = False
        if r in ev1.decisive and ev1.decisive[r][sd].any():
            hit = True
        if r in ev2.decisive and ev2.decisive[r][sd].any():
            hit = True
        n += hit
    return n, True


summary = {}
for name, (mk, dom) in DATASETS.items():
    G = Grid(dom)
    ps1 = mk()
    t0 = time.perf_counter()
    g1 = TPG(ps1, G)
    t_build1 = time.perf_counter() - t0
    nstat, estat = g1.stats()
    nrules = sum(len(p_.rules) for p_ in ps1.policies)
    # ----------------------------------------------- oracle correctness on the original policies
    oracle = {"xfg_err": [], "w1_err": [], "w1_n": []}
    for s in SEEDS:
        rng = np.random.default_rng(s)
        suite = xfg_suite(g1, rng)
        oracle["xfg_err"].append(sum(int(g1.ev.dec[q]) != e for q, e, _ in suite))
        err = n = 0
        for pol in ps1.policies:
            for r in pol.rules:
                m = w1_mask(g1, r.id, INTER)
                if m.any():
                    idx = np.flatnonzero(m)
                    q = int(idx[rng.integers(idx.size)])
                    n += 1
                    err += int(g1.ev.dec[q]) != g1.ev.effect[r.id]
        oracle["w1_err"].append(err)
        oracle["w1_n"].append(n)
    never_decisive = [r.id for pol in ps1.policies for r in pol.rules if not g1.ev.decisive[r.id].any()]
    w1_empty = [r.id for pol in ps1.policies for r in pol.rules if not w1_mask(g1, r.id, INTER).any()]
    xfg_wrong_rules = sorted({rid for s in SEEDS for q, e, rid in xfg_suite(g1, np.random.default_rng(s))
                              if int(g1.ev.dec[q]) != e})
    # analytic: probability that a path-based request for rule r yields a wrong oracle
    wrong_frac = {}
    for pol in ps1.policies:
        for r in pol.rules:
            a = g1.ev.app[r.id]
            wrong_frac[r.id] = float((g1.ev.dec[a] != g1.ev.effect[r.id]).mean()) if a.any() else None
    # ----------------------------------------------- evolutions
    evs = evolutions(ps1, dom)
    rows = []
    for k, evo in enumerate(evs):
        ps2 = evo["ps"]
        t0 = time.perf_counter()
        ev2 = evaluate(ps2, G)
        diff = g1.ev.dec != ev2.dec
        t_sem = time.perf_counter() - t0
        affected = sorted({r for r, m in g1.ev.decisive.items() if (m & diff).any()} |
                          {r for r, m in ev2.decisive.items() if (m & diff).any()})
        t0 = time.perf_counter()
        g2 = TPG(ps2, G, ev2)
        t_tpg2 = time.perf_counter() - t0
        row = {"op": evo["op"], "desc": evo["desc"], "ndiff": int(diff.sum()),
               "changed": bool(diff.any()), "affected": affected, "t_sem": t_sem,
               "t_tpg2": t_tpg2, "m": {}, "N": G.N}
        bis_sets = {}
        for mname, use in ABL.items():
            t0 = time.perf_counter()
            CH, bis, cs, fol = diff_bis(g1, g2, use)
            t_bis = time.perf_counter() - t0
            bis_sets[mname] = (CH, bis, cs, fol)
            row["m"][mname] = {"bis": sorted(bis), "ch": sorted(CH), "cs": sorted(cs),
                               "t_bis": t_bis, "seeds": []}
        ar, ac = ast_diff(ps1, ps2, g1, g2)
        row["m"]["AST-Up"] = {"bis": sorted(ar), "cs": sorted(ac), "seeds": []}
        row["m"]["Retest-all"] = {"seeds": []}
        row["m"]["XFG-Regen"] = {"seeds": []}
        row["m"]["Retest-all(GA)"] = {"seeds": []}
        row["m"]["XFG-Regen(GA)"] = {"seeds": []}
        row["m"]["TPG-Reg(raw)"] = {"seeds": []}
        row["m"]["TPG-Reg+D"] = {"seeds": []}
        for s in SEEDS:
            rng = np.random.default_rng(1000 * s + k)
            suites = {
                "Retest-all": xfg_min_suite(g1, rng),
                "XFG-Regen": xfg_min_suite(g2, rng),
                "Retest-all(GA)": xfg_ga_suite(g1, rng),
                "XFG-Regen(GA)": xfg_ga_suite(g2, rng),
                "AST-Up": ast_generate(g1, g2, ar, ac, rng),
            }
            for mname, use in ABL.items():
                CH, bis, cs, fol = bis_sets[mname]
                t0 = time.perf_counter()
                suites[mname] = tpg_generate(g1, g2, CH, bis, cs, fol, rng, use)
                if mname == "TPG-Reg":
                    row["t_gen"] = time.perf_counter() - t0
                    obl = tpg_obligations(g1, g2, CH, bis, cs, fol, use)
                    suites["TPG-Reg(raw)"] = sorted({pick(m, rng) for m in obl})
                    sl = np.zeros(G.N, bool)
                    for rid in bis:
                        if rid in g1.ev.app:
                            sl |= g1.ev.app[rid]
                        if rid in ev2.app:
                            sl |= ev2.app[rid]
                    row["slice"] = int(sl.sum())
                    dobl = [diff & ((g1.ev.app[rid] if rid in g1.ev.app else False) |
                                    (ev2.app[rid] if rid in ev2.app else False)) for rid in sorted(bis)]
                    dobl = [m for m in dobl if np.any(m)]
                    suites["TPG-Reg+D"] = minimise(obl + dobl, rng)
            for mname, suite in suites.items():
                nexp, det = exposed(suite, diff, g1.ev, ev2, affected)
                row["m"][mname]["seeds"].append({"size": len(set(suite)), "det": det, "exp": nexp})
        rows.append(row)
    summary[name] = {"N": G.N, "rules": nrules, "policies": len(ps1.policies),
                     "nodes": dict(nstat), "edges": dict(estat), "t_build": t_build1,
                     "oracle": oracle, "never_decisive": never_decisive, "w1_empty": w1_empty,
                     "xfg_wrong_rules": xfg_wrong_rules, "wrong_frac": wrong_frac}
    with open(f"{OUT}/per_evolution_{name}.json", "w") as f:
        json.dump(rows, f)
    print(name, "evolutions", len(rows), "changed", sum(r["changed"] for r in rows), flush=True)
with open(f"{OUT}/policy_statistics.json", "w") as f:
    json.dump(summary, f, indent=1)
