"""Scalability study with the Z3 backend on synthetic policies whose request
space cannot be enumerated (four integer attributes in [0, 10^6]).

For each size n, one policy set and E single-edit evolutions are generated.
Per evolution we measure: incremental TPG update, difference + BIS,
witness solving + greedy minimisation (W1-W3), distinguishing queries (D),
and a single global semantic-difference query. Ground truth: the global query
decides whether behaviour changed; up to S distinguishing requests sampled
from it give affected rules, used to check BIS soundness and exposure.

Usage: python3 exp_scalability.py <out dir> <sizes, e.g. 50,100,200,400> <evolutions per size> [analysis]
Output: runs_full_pipeline_n<sizes>.json or runs_analysis_only_n<sizes>.json
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".."))

import copy, json, sys, time
import numpy as np
import z3
from tpgreg.policy_model import PolicySet, Policy, Rule, Pred, p, AND, OR, VAR, evaluate, EFF, NA
from tpgreg.typed_policy_graph import TPG, INTER
from tpgreg.impact_analysis import diff_bis
from tpgreg.smt_backend import Encoder, Batch, IntRange, solve
from tpgreg.mutation import evolutions

SIZES = [int(x) for x in (sys.argv[2].split(",") if len(sys.argv) > 2 else "50,100,200,400,800".split(","))]
E_PER_SIZE = int(sys.argv[3]) if len(sys.argv) > 3 else 30
ANALYSIS_ONLY = len(sys.argv) > 4 and sys.argv[4] == "analysis"
OUT = sys.argv[1] if len(sys.argv) > 1 else "../results/scalability"
TO = 10000   # ms per query


def make_domains():
    dom = {f"c{i}": [f"v{j}" for j in range(20)] for i in range(1, 7)}
    for i in range(1, 5):
        dom[f"n{i}"] = IntRange(0, 10 ** 6)
    return dom


def gen_policy(n, seed):
    rng = np.random.default_rng(seed)
    pick = lambda xs: xs[int(rng.integers(len(xs)))]
    algs = ["DO", "PO", "FA"]
    pols = []
    for pi in range((n + 9) // 10):
        vars_ = {}
        if rng.random() < 0.5:
            vars_["w"] = AND(p("n1", "ge", int(rng.integers(0, 5 * 10 ** 5))),
                             p("n1", "lt", int(rng.integers(5 * 10 ** 5, 10 ** 6))))
        rules = []
        for ri in range(min(10, n - 10 * pi)):
            tgt = []
            if rng.random() < 0.9:
                tgt.append(Pred("c1", "eq", f"v{int(rng.integers(20))}"))
            if rng.random() < 0.6:
                tgt.append(Pred("c4", "in", tuple(sorted({f"v{int(x)}" for x in rng.integers(0, 20, 2)}))))
            atoms = [p(f"n{int(rng.integers(1, 5))}", pick(["ge", "lt", "gt", "le"]), int(rng.integers(0, 10 ** 6)))
                     for _ in range(int(rng.integers(1, 3)))]
            if "w" in vars_ and rng.random() < 0.3:
                atoms.append(VAR("w"))
            cond = atoms[0] if len(atoms) == 1 else (AND(*atoms) if rng.random() < 0.7 else OR(*atoms))
            rules.append(Rule(f"X.P{pi}.R{ri}", "Permit" if rng.random() < 0.6 else "Deny", tgt, cond))
        ptgt = [Pred("c3", "eq", f"v{pi % 20}")] if rng.random() < 0.9 else []
        pols.append(Policy(f"X.P{pi}", pick(algs), ptgt, rules, vars_))
    return PolicySet("X", pick(algs), [], pols)


def pol_sig(pol):
    return repr((pol.alg, pol.target, pol.vars, [(r.id, r.effect, r.target, r.cond) for r in pol.rules]))


class SMTGraph(TPG):
    """TPG whose overlap test is a Z3 query; reuses results of a previous
    version for rule pairs whose policies are unchanged (incremental)."""

    def __init__(self, ps, enc, prev=None):
        self.enc = enc
        self.appf, self.regionf, self.localf, self.effv = enc.app(ps)
        self.solver = z3.Solver()
        self.solver.set("timeout", TO)
        self.solver.add(*enc.cons)
        self.cache = {}
        self.queries = self.pruned = self.reused = self.unknown = 0
        clean = set()
        if prev is not None and prev.ps.alg == ps.alg and repr(prev.ps.target) == repr(ps.target):
            psig = {pol.id: (i, pol_sig(pol)) for i, pol in enumerate(prev.ps.policies)}
            for i, pol in enumerate(ps.policies):
                if psig.get(pol.id) == (i, pol_sig(pol)):
                    clean.add(pol.id)
        self.prev, self.clean = prev, clean
        super().__init__(ps, None, ev=type("E", (), {"app": None})())

    def _overlap(self, pa, ra, pb, rb):
        key = (ra.id, rb.id)
        if self.prev is not None and pa.id in self.clean and pb.id in self.clean and key in self.prev.cache:
            self.reused += 1
            self.cache[key] = self.prev.cache[key]
            return self.cache[key]
        if _disjoint(ra, rb, pa, pb):
            self.pruned += 1
            self.cache[key] = False
            return False
        self.queries += 1
        s = self.solver
        s.push()
        s.add(self.appf[ra.id], self.appf[rb.id])
        r = s.check()
        s.pop()
        if r == z3.unknown:
            self.unknown += 1
        self.cache[key] = r != z3.unsat
        return self.cache[key]


def _disjoint(ra, rb, pa, pb):
    def sets(ts):
        out = {}
        for t in ts:
            if t.op == "eq":
                s = {t.val}
            elif t.op == "in":
                s = set(t.val)
            else:
                continue
            out[t.attr] = out[t.attr] & s if t.attr in out else s
        return out
    A, B = sets(list(ra.target) + list(pa.target)), sets(list(rb.target) + list(pb.target))
    return any(a in B and not (A[a] & B[a]) for a in A)


def competitors(g, rid):
    out = set()
    rn = "R:" + rid
    for e in g.edges:
        if e[0] == "precedes" and e[2] == rn:
            out.add(e[1][2:])
        elif e[0] == "overrides" and rn in (e[1], e[2]):
            d = e[2][2:] if e[1] == rn else e[1][2:]
            if (e[3] == "DO" and g.effv[d] == 2) or (e[3] == "PO" and g.effv[d] == 1):
                out.add(d)
    return out


def obligations(g1, g2, CH, bis, followed, with_d, dec1, dec2):
    """List of (formula, checker) where checker(ev1, ev2, i) -> bool."""
    obl = []
    for v, g in ((1, g1), (2, g2)):
        for rid in sorted(bis):
            if rid not in g.appf:
                continue
            comp = sorted(competitors(g, rid))
            f = z3.And([g.appf[rid]] + [z3.Not(g.appf[c]) for c in comp])
            obl.append((f, lambda e1, e2, i, v=v, rid=rid, comp=comp:
                        (e1 if v == 1 else e2).app[rid][i] and not any((e1 if v == 1 else e2).app[c][i] for c in comp)))
            if rid in CH:
                others = sorted(set(g.appf) - {rid})
                f = z3.And([g.appf[rid]] + [z3.Not(g.appf[c]) for c in others])
                obl.append((f, lambda e1, e2, i, v=v, rid=rid, others=others:
                            (e1 if v == 1 else e2).app[rid][i] and not any((e1 if v == 1 else e2).app[c][i] for c in others)))
        for e in sorted(followed):
            if e in g.edges:
                a, b = e[1][2:], e[2][2:]
                obl.append((z3.And(g.appf[a], g.appf[b]),
                            lambda e1, e2, i, v=v, a=a, b=b: (e1 if v == 1 else e2).app[a][i] and (e1 if v == 1 else e2).app[b][i]))
    for rid in sorted(CH):
        if rid in g1.appf and rid in g2.appf:
            obl.append((z3.And(g1.appf[rid], z3.Not(g2.appf[rid])), lambda e1, e2, i, rid=rid: e1.app[rid][i] and not e2.app[rid][i]))
            obl.append((z3.And(g2.appf[rid], z3.Not(g1.appf[rid])), lambda e1, e2, i, rid=rid: e2.app[rid][i] and not e1.app[rid][i]))
    if with_d:
        for rid in sorted(bis):
            parts = [g.appf[rid] for g in (g1, g2) if rid in g.appf]
            obl.append((z3.And(z3.Or(parts), dec1 != dec2),
                        lambda e1, e2, i, rid=rid: (e1.app.get(rid, [False] * (i + 1))[i] or e2.app.get(rid, [False] * (i + 1))[i]) and e1.dec[i] != e2.dec[i]))
    return obl


def generate(g1, g2, ps1, ps2, dom, obl, rng, k=3):
    """Solve each obligation (k candidates), then greedy set cover using PDP
    evaluation of both versions on the candidates."""
    cands = []
    nsolved = 0
    for f, _ in obl:
        sols = solve(g1.enc, f, rng, k=k, timeout_ms=TO)
        nsolved += bool(sols)
        cands.extend(sols)
    if not cands:
        return [], None, None, nsolved
    B = Batch(dom, cands)
    e1, e2 = evaluate(ps1, B), evaluate(ps2, B)
    cov = np.array([[bool(chk(e1, e2, i)) for i in range(len(cands))] for _, chk in obl])
    left = cov.any(axis=1)
    chosen = []
    while left.any():
        gain = cov[left].sum(axis=0)
        best = int(np.argmax(gain))
        if gain[best] == 0:
            break
        chosen.append(best)
        left &= ~cov[:, best]
    return [cands[i] for i in chosen], e1, e2, nsolved


def main():
    import os; os.makedirs(OUT, exist_ok=True)
    dom = make_domains()
    enc = Encoder(dom)
    rows = []
    for n in SIZES:
        ps1 = gen_policy(n, seed=n)
        t0 = time.perf_counter()
        g1 = SMTGraph(ps1, enc)
        t_build = time.perf_counter() - t0
        dec1 = enc.decision(ps1)
        evs = evolutions(ps1, {a: (list(range(0, 10 ** 6 + 1, 10 ** 5)) if isinstance(v, IntRange) else v) for a, v in dom.items()})
        rng = np.random.default_rng(n)
        sel = rng.choice(len(evs), size=min(E_PER_SIZE, len(evs)), replace=False)
        print(f"n={n}: |E*|={len([e for e in g1.edges if e[0] in INTER])} build={t_build:.1f}s queries={g1.queries} pruned={g1.pruned} unknown={g1.unknown} evolutions={len(evs)}", flush=True)
        for k in sel:
            evo = evs[int(k)]
            ps2 = evo["ps"]
            row = {"n": n, "op": evo["op"], "desc": evo["desc"], "t_build1": t_build, "q_build1": g1.queries,
                   "E_star": len([e for e in g1.edges if e[0] in INTER]), "pruned1": g1.pruned}
            t0 = time.perf_counter(); g2 = SMTGraph(ps2, enc, prev=g1); row["t_tpg2"] = time.perf_counter() - t0
            row.update(q_tpg2=g2.queries, reused=g2.reused, unknown=g2.unknown)
            t0 = time.perf_counter(); CH, bis, cs, fol = diff_bis(g1, g2); row["t_bis"] = time.perf_counter() - t0
            row.update(CH=len(CH), BIS=len(bis))
            dec2 = enc.decision(ps2)
            # global semantic difference (one query) and affected-rule sample
            s = z3.Solver(); s.set("timeout", 60000); s.add(*enc.cons); s.add(dec1 != dec2)
            t0 = time.perf_counter(); r = s.check(); row["t_global"] = time.perf_counter() - t0
            row["changed"] = (r == z3.sat)
            row["global_unknown"] = (r == z3.unknown)
            if ANALYSIS_ONLY:
                rows.append(row)
                print({k2: (round(v, 3) if isinstance(v, float) else v) for k2, v in row.items() if k2 != "desc"}, flush=True)
                continue
            # soundness check: for every rule outside the BIS, ask for a
            # distinguishing request on which it applies; check decisiveness
            # of such a request with the PDP
            viol = sat_cnt = 0
            aff = set()
            if r == z3.sat:
                sv = z3.Solver(); sv.set("timeout", TO); sv.add(*enc.cons); sv.add(dec1 != dec2)
                for rid in sorted(set(g1.appf) | set(g2.appf)):
                    if rid in bis:
                        continue
                    parts = [g.appf[rid] for g in (g1, g2) if rid in g.appf]
                    sv.push(); sv.add(z3.Or(parts)); rr = sv.check()
                    sols = [enc.model_to_request(sv.model())] if rr == z3.sat else []
                    sv.pop()
                    if not sols:
                        continue
                    sat_cnt += 1
                    B = Batch(dom, sols)
                    e1, e2 = evaluate(ps1, B), evaluate(ps2, B)
                    if (rid in e1.decisive and e1.decisive[rid].any()) or (rid in e2.decisive and e2.decisive[rid].any()):
                        viol += 1
                samples = solve(enc, dec1 != dec2, rng, k=20, timeout_ms=60000)
                B = Batch(dom, samples)
                e1, e2 = evaluate(ps1, B), evaluate(ps2, B)
                for rid, m in list(e1.decisive.items()) + list(e2.decisive.items()):
                    if m.any():
                        aff.add(rid)
            row["outside_sat"] = sat_cnt
            row["violations"] = viol
            row["aff_sample"] = len(aff)
            row["aff_outside_bis"] = len(aff - bis)
            for mode in ("W", "D"):
                obl = obligations(g1, g2, CH, bis, fol, mode == "D", dec1, dec2)
                t0 = time.perf_counter()
                suite, e1, e2, nsol = generate(g1, g2, ps1, ps2, dom, obl, rng)
                row[f"t_gen_{mode}"] = time.perf_counter() - t0
                row[f"obl_{mode}"] = len(obl)
                row[f"T_{mode}"] = len(suite)
                det = False
                exposed = set()
                if suite:
                    B = Batch(dom, suite)
                    a1, a2 = evaluate(ps1, B), evaluate(ps2, B)
                    dmask = a1.dec != a2.dec
                    det = bool(dmask.any())
                    for rid in aff:
                        if (rid in a1.decisive and (a1.decisive[rid] & dmask).any()) or \
                           (rid in a2.decisive and (a2.decisive[rid] & dmask).any()):
                            exposed.add(rid)
                row[f"det_{mode}"] = det
                row[f"exp_{mode}"] = len(exposed)
            rows.append(row)
            print({k2: (round(v, 3) if isinstance(v, float) else v) for k2, v in row.items() if k2 not in ("desc",)}, flush=True)
        json.dump(rows, open(f"{OUT}/runs_{'analysis_only' if ANALYSIS_ONLY else 'full_pipeline'}_n{'-'.join(map(str, SIZES))}.json", "w"), indent=0)


if __name__ == "__main__":
    main()
