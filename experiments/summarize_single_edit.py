"""Aggregate the single-edit evolution results: detection rate (EDR),
affected-rule exposure (ARE), suite sizes, BIS recall/precision, results per
edit operator and timings.

Usage: python3 summarize_single_edit.py <single_edit_evolution dir>
Output: summary.json (and a text summary on stdout)
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".."))

import json, sys
from collections import defaultdict
import numpy as np

R = sys.argv[1] if len(sys.argv) > 1 else "../results/single_edit_evolution"
S = json.load(open(f"{R}/policy_statistics.json"))
METHODS = ["Retest-all", "XFG-Regen", "Retest-all(GA)", "XFG-Regen(GA)", "AST-Up", "TPG-Reg", "TPG-Reg(raw)", "TPG-Reg+D", "-precedes", "-overrides", "-scopes", "-refers"]
out = {}
allrows = []
for ds in S:
    rows = json.load(open(f"{R}/per_evolution_{ds}.json"))
    for r in rows:
        r["ds"] = ds
    allrows += rows


def stats(rows, label):
    ch = [r for r in rows if r["changed"]]
    eq = [r for r in rows if not r["changed"]]
    res = {"n": len(rows), "changed": len(ch), "equiv": len(eq)}
    for m in METHODS:
        det = [np.mean([s["det"] for s in r["m"][m]["seeds"]]) for r in ch]
        aff_tot = sum(len(r["affected"]) for r in ch)
        exp = [sum(r["m"][m]["seeds"][i]["exp"] for r in ch) / aff_tot for i in range(5)]
        detseed = [np.mean([r["m"][m]["seeds"][i]["det"] for r in ch]) for i in range(5)]
        size_ch = np.mean([np.mean([s["size"] for s in r["m"][m]["seeds"]]) for r in ch]) if ch else 0
        size_eq = np.mean([np.mean([s["size"] for s in r["m"][m]["seeds"]]) for r in eq]) if eq else 0
        d = {"EDR": float(np.mean(detseed)), "EDR_sd": float(np.std(detseed)),
             "ARE": float(np.mean(exp)), "ARE_sd": float(np.std(exp)),
             "size_ch": float(size_ch), "size_eq": float(size_eq)}
        if "bis" in r["m"].get(m, {}) if rows else False:
            pass
        if m not in ("Retest-all", "XFG-Regen", "Retest-all(GA)", "XFG-Regen(GA)", "TPG-Reg(raw)", "TPG-Reg+D"):
            rec_num = sum(len(set(r["affected"]) & set(r["m"][m]["bis"])) for r in ch)
            rec_den = sum(len(r["affected"]) for r in ch)
            miss_evo = sum(1 for r in ch if not set(r["affected"]) <= set(r["m"][m]["bis"]))
            prec_num = sum(len(set(r["affected"]) & set(r["m"][m]["bis"])) for r in ch)
            prec_den = sum(len(r["m"][m]["bis"]) for r in ch)
            d.update({"BIS_recall": rec_num / rec_den, "BIS_prec": prec_num / max(prec_den, 1),
                      "miss_evo": miss_evo,
                      "bis_size_ch": float(np.mean([len(r["m"][m]["bis"]) for r in ch])),
                      "bis_size_eq": float(np.mean([len(r["m"][m]["bis"]) for r in eq])) if eq else 0,
                      "eq_nonempty": sum(1 for r in eq if r["m"][m]["bis"])})
        res[m] = d
    return res


for ds in S:
    out[ds] = stats([r for r in allrows if r["ds"] == ds], ds)
out["ALL"] = stats(allrows, "ALL")
# per-operator
ops = sorted({r["op"] for r in allrows})
out["per_op"] = {}
for op in ops:
    rs = [r for r in allrows if r["op"] == op]
    out["per_op"][op] = stats(rs, op)
# misses detail for TPG-Reg
out["tpg_misses"] = [(r["ds"], r["op"], r["desc"], sorted(set(r["affected"]) - set(r["m"]["TPG-Reg"]["bis"])))
                     for r in allrows if r["changed"] and not set(r["affected"]) <= set(r["m"]["TPG-Reg"]["bis"])]
out["tpg_undetected"] = [(r["ds"], r["op"], r["desc"], r["ndiff"], [s["det"] for s in r["m"]["TPG-Reg"]["seeds"]])
                         for r in allrows if r["changed"] and not all(s["det"] for s in r["m"]["TPG-Reg"]["seeds"])]
# timing
out["time"] = {ds: {"t_sem_ms": 1000 * np.mean([r["t_sem"] for r in allrows if r["ds"] == ds]),
                    "t_tpg2_ms": 1000 * np.mean([r["t_tpg2"] for r in allrows if r["ds"] == ds]),
                    "t_bis_ms": 1000 * np.mean([r["m"]["TPG-Reg"]["t_bis"] for r in allrows if r["ds"] == ds]),
                    "t_gen_ms": 1000 * np.mean([r["t_gen"] for r in allrows if r["ds"] == ds])} for ds in S}
out["slice"] = {ds: float(np.mean([r["slice"] / r["N"] for r in allrows if r["ds"] == ds and r["changed"]])) for ds in S}
out["slice"]["ALL"] = float(np.mean([r["slice"] / r["N"] for r in allrows if r["changed"]]))
print("slice", out["slice"])
json.dump(out, open(f"{R}/summary.json", "w"), indent=1, default=float)

for ds in list(S) + ["ALL"]:
    o = out[ds]
    print(f"== {ds}: n={o['n']} changed={o['changed']} equiv={o['equiv']}")
    for m in METHODS:
        d = o[m]
        extra = ""
        if "BIS_recall" in d:
            extra = f" BISrec={d['BIS_recall']:.3f} prec={d['BIS_prec']:.3f} miss_evo={d['miss_evo']} bis={d['bis_size_ch']:.1f} eqBIS={d['bis_size_eq']:.1f} eqNonEmpty={d['eq_nonempty']}"
        print(f"  {m:11s} EDR={d['EDR']:.3f}±{d['EDR_sd']:.3f} ARE={d['ARE']:.3f}±{d['ARE_sd']:.3f} size={d['size_ch']:.1f} sizeEq={d['size_eq']:.1f}{extra}")
print("per-op TPG/AST/-prec/-over/-scopes/-refers ARE:")
for op in ops:
    o = out["per_op"][op]
    print(f"  {op} n={o['n']} ch={o['changed']} " + " ".join(f"{m}:{o[m]['ARE']:.2f}/{o[m]['EDR']:.2f}" for m in METHODS))
print("misses", out["tpg_misses"][:20], len(out["tpg_misses"]))
print("undetected", out["tpg_undetected"][:20], len(out["tpg_undetected"]))
print(json.dumps(out["time"], indent=0, default=float))
for ds in S:
    s = S[ds]
    print(ds, s["N"], s["rules"], s["policies"], s["nodes"], s["edges"], "build", s["t_build"])
    print("  oracle", s["oracle"], "never_dec", s["never_decisive"], "w1_empty", s["w1_empty"], "xfgwrong", s["xfg_wrong_rules"])
