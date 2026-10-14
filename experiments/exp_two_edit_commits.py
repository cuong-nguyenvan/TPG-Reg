"""Two-edit commit experiment for the change-aware (intent) oracle.

Clean commit: P1 -> P_int (one behaviour-changing edit, intent refine(E)).
Dirty commit: P1 -> P_both = P_int + one undeclared side edit outside the
scope of E that changes the behaviour of P_int. Ground truth is independent of
the oracle: a commit is dirty iff it contains the undeclared edit. A method
flags a commit if its suite contains a request whose decision changed and on
which no decisive rule lies in scope(E).

Usage: python3 exp_two_edit_commits.py <out dir> [commits per policy set]
Output: per_commit.json, summary.json
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".."))

import json, sys
import numpy as np
from tpgreg.policy_model import Grid, evaluate
from tpgreg.benchmarks import DATASETS
from tpgreg.mutation import evolutions
from tpgreg.typed_policy_graph import TPG
from tpgreg.impact_analysis import diff_bis
from tpgreg.test_generation import tpg_obligations, minimise
from tpgreg.baselines import ast_diff, ast_generate, xfg_min_suite

OUT = sys.argv[1] if len(sys.argv) > 1 else "../results/two_edit_commits"
import os; os.makedirs(OUT, exist_ok=True)
N_PER_DS = int(sys.argv[2]) if len(sys.argv) > 2 else 40
SEEDS = [1, 2, 3, 4, 5]
FULL = ("precedes", "overrides", "scopes", "refers")


def scope(E, ps_list):
    out = set()
    for ps in ps_list:
        for pol in ps.policies:
            for r in pol.rules:
                if r.id in E or pol.id in E or ps.id in E:
                    out.add(r.id)
    return out


def regression_mask(ev1, ev2, sc):
    diff = ev1.dec != ev2.dec
    inscope = np.zeros_like(diff)
    for rid in sc:
        if rid in ev1.decisive:
            inscope |= ev1.decisive[rid]
        if rid in ev2.decisive:
            inscope |= ev2.decisive[rid]
    return diff & ~inscope, diff


def suites(g1, g2, ps1, ps2, ev2, rng):
    CH, bis, cs, fol = diff_bis(g1, g2, FULL)
    obl = tpg_obligations(g1, g2, CH, bis, cs, fol, FULL)
    diff = g1.ev.dec != ev2.dec
    dobl = [diff & ((g1.ev.app[r] if r in g1.ev.app else False) | (ev2.app[r] if r in ev2.app else False))
            for r in sorted(bis)]
    dobl = [m for m in dobl if np.any(m)]
    ar, ac = ast_diff(ps1, ps2, g1, g2)
    return {"Retest-all": xfg_min_suite(g1, rng), "XFG-Regen": xfg_min_suite(g2, rng),
            "AST-Up": ast_generate(g1, g2, ar, ac, rng), "TPG-Reg": minimise(obl, rng),
            "TPG-Reg+D": minimise(obl + dobl, rng)}


rows = []
for name, (mk, dom) in DATASETS.items():
    G = Grid(dom)
    ps1 = mk()
    g1 = TPG(ps1, G)
    rng0 = np.random.default_rng(7)
    evs = [e for e in evolutions(ps1, dom) if e["op"] not in ("RRO", "PRO")]
    order = rng0.permutation(len(evs))
    made = 0
    for k in order:
        if made >= N_PER_DS:
            break
        intended = evs[int(k)]
        P_int = intended["ps"]
        ev_int = evaluate(P_int, G)
        if not (g1.ev.dec != ev_int.dec).any():
            continue
        E = set(intended["edited"])
        sc_int = scope(E, [ps1, P_int])
        pols_of_E = {pol.id for pol in P_int.policies for r in pol.rules if r.id in sc_int} | \
                    {x for x in E if x.startswith(name[0] + ".P")}
        side = [e for e in evolutions(P_int, dom)
                if e["op"] not in ("RRO", "PRO") and not (set(e["edited"]) & (sc_int | E | pols_of_E | {ps1.id}))
                and not any(x.endswith((".N0", ".N1")) for x in e["edited"])]
        rng0.shuffle(side)
        side_pick = None
        for s in side:
            ev_b = evaluate(s["ps"], G)
            if (ev_int.dec != ev_b.dec).any():
                side_pick, ev_both = s, ev_b
                break
        if side_pick is None:
            continue
        made += 1
        for label, P2, ev2 in (("clean", P_int, ev_int), ("dirty", side_pick["ps"], ev_both)):
            sc = scope(E, [ps1, P2])
            reg, diff = regression_mask(g1.ev, ev2, sc)
            g2 = TPG(P2, G, ev2)
            row = {"ds": name, "label": label, "intended": f"{intended['op']}:{intended['desc']}",
                   "side": f"{side_pick['op']}:{side_pick['desc']}" if label == "dirty" else "",
                   "n_diff": int(diff.sum()), "n_reg_gt": int(reg.sum()), "m": {}}
            for s in SEEDS:
                rng = np.random.default_rng(100 * s + made)
                for mname, suite in suites(g1, g2, ps1, P2, ev2, rng).items():
                    st = np.asarray(suite, dtype=np.int64)
                    flagged = bool(st.size and reg[st].any())
                    detected = bool(st.size and diff[st].any())
                    row["m"].setdefault(mname, []).append({"flag": flagged, "det": detected, "size": int(st.size)})
            rows.append(row)
    print(name, "commits", made, flush=True)

json.dump(rows, open(f"{OUT}/per_commit.json", "w"))
# summary
summ = {}
for label in ("clean", "dirty"):
    rs = [r for r in rows if r["label"] == label]
    summ[label] = {"n": len(rs), "oracle_flaggable_exhaustive": sum(r["n_reg_gt"] > 0 for r in rs)}
    for m in rs[0]["m"]:
        summ[label][m] = {"flag": float(np.mean([np.mean([x["flag"] for x in r["m"][m]]) for r in rs])),
                          "det": float(np.mean([np.mean([x["det"] for x in r["m"][m]]) for r in rs])),
                          "size": float(np.mean([np.mean([x["size"] for x in r["m"][m]]) for r in rs]))}
json.dump(summ, open(f"{OUT}/summary.json", "w"), indent=1)
print(json.dumps(summ, indent=1))
