"""Two-rule financial policy (deny-overrides) and two commits:
A raises the deny threshold (intent: refine R2), B switches the algorithm to
first-applicable (intent: refactoring). Shows the path-based oracle error, the
impact sets and the change-aware classification of the generated tests.

Usage: python3 demo_finance_example.py
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".."))

import numpy as np
from tpgreg.policy_model import Grid, evaluate, DEC_NAME
from tpgreg.typed_policy_graph import TPG, INTER
from tpgreg.impact_analysis import diff_bis
from tpgreg.test_generation import tpg_obligations, minimise, w1_mask
from tpgreg.benchmarks import fin, FIN_DOM

G = Grid(FIN_DOM)
v1 = fin("DO", 5)
g1 = TPG(v1, G)
q = next(i for i in range(G.N) if G.request(i) == {"role": "FinancialOfficer", "action": "Transfer", "amount": 7})
print("path-based oracle for R1 at amount=7: expected Permit, PDP:", DEC_NAME[int(g1.ev.dec[q])])
print("v1 edges:", sorted(e[:3] for e in g1.edges if e[0] in INTER))
m = w1_mask(g1, "M.R1", INTER)
print("W1(R1) amounts:", sorted({G.request(i)["amount"] for i in np.flatnonzero(m)}))
for name, v2, intent in [("A (refine R2: 5->8)", fin("DO", 8), {"M.R2"}),
                         ("B (refactor: DO->FA)", fin("FA", 5), set())]:
    g2 = TPG(v2, G)
    CH, bis, cs, fol = diff_bis(g1, g2)
    diff = g1.ev.dec != g2.ev.dec
    obl = tpg_obligations(g1, g2, CH, bis, cs, fol, INTER + ("scopes", "refers"))
    suite = minimise(obl, np.random.default_rng(1))
    print(f"\nCommit {name}: CH={sorted(CH)} BIS={sorted(bis)} |diff|={int(diff.sum())} suite={len(suite)}")
    for t in suite:
        r = G.request(t)
        d1, d2 = int(g1.ev.dec[t]), int(g2.ev.dec[t])
        if d1 != d2:
            dec = sorted({x for x, mm in g1.ev.decisive.items() if mm[t]} | {x for x, mm in g2.ev.decisive.items() if mm[t]})
            label = "intended" if set(dec) & intent else "REGRESSION"
            print(f"  amount={r['amount']:2d}: {DEC_NAME[d1]} -> {DEC_NAME[d2]}  decisive={dec}  => {label}")
    amounts = sorted({G.request(i)["amount"] for i in np.flatnonzero(diff)})
    print("  ground-truth changed amounts:", amounts)
