"""Paired significance tests over the behaviour-changing single-edit
evolutions: per-evolution detection rate and exposure (mean over seeds) of
TPG-Reg / TPG-Reg+D versus each baseline. Wilcoxon signed-rank (Pratt),
Vargha-Delaney A12 and an exact McNemar test on seed-1 detection outcomes.

Usage: python3 significance_tests.py <single_edit_evolution dir>
Output: significance_tests.json
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".."))

import json, sys
import numpy as np
from scipy.stats import wilcoxon, binomtest

R = sys.argv[1] if len(sys.argv) > 1 else "../results/single_edit_evolution"
rows = []
for ds in ("HACS", "FMS", "SIS"):
    for r in json.load(open(f"{R}/per_evolution_{ds}.json")):
        if r["changed"]:
            rows.append(r)


def per_evo(m, key):
    out = []
    for r in rows:
        v = [s[key] for s in r["m"][m]["seeds"]]
        if key == "exp":
            v = [x / len(r["affected"]) for x in v]
        out.append(float(np.mean(v)))
    return np.array(out)


def a12(x, y):
    gt = (x[:, None] > y[None, :]).sum()
    eq = (x[:, None] == y[None, :]).sum()
    return (gt + 0.5 * eq) / (len(x) * len(y))


res = {}
for ref in ("TPG-Reg", "TPG-Reg+D"):
    for base in ("Retest-all", "XFG-Regen", "Retest-all(GA)", "XFG-Regen(GA)", "AST-Up"):
        d = {}
        for key, nm in (("det", "EDR"), ("exp", "ARE")):
            x, y = per_evo(ref, key), per_evo(base, key)
            w = wilcoxon(x, y, zero_method="pratt")
            d[nm] = {"p": float(w.pvalue), "A12": float(a12(x, y)), "mean_diff": float((x - y).mean())}
        b = sum(1 for r in rows if r["m"][ref]["seeds"][0]["det"] and not r["m"][base]["seeds"][0]["det"])
        c = sum(1 for r in rows if not r["m"][ref]["seeds"][0]["det"] and r["m"][base]["seeds"][0]["det"])
        d["McNemar_seed1"] = {"b": b, "c": c, "p": float(binomtest(b, b + c, 0.5).pvalue) if b + c else 1.0}
        res[f"{ref} vs {base}"] = d
json.dump(res, open(f"{R}/significance_tests.json", "w"), indent=1)
for k, v in res.items():
    print(f"{k:32s} EDR p={v['EDR']['p']:.2e} A12={v['EDR']['A12']:.2f} | ARE p={v['ARE']['p']:.2e} A12={v['ARE']['A12']:.2f} | McNemar b={v['McNemar_seed1']['b']} c={v['McNemar_seed1']['c']} p={v['McNemar_seed1']['p']:.1e}")
