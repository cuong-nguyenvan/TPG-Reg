"""Z3 backend for TPG-Reg: overlap queries, witness solving and the joint
(distinguishing) query, without enumerating the request space."""
from __future__ import annotations
import numpy as np
import z3
from .policy_model import (PolicySet, Grid, Eval, evaluate, expr_vars, P, D, NA, EFF)

INTER = ("precedes", "overrides")


class IntRange(list):
    """Integer domain [lo, hi] that is never enumerated (stores only bounds)."""

    def __init__(self, lo, hi):
        super().__init__([lo, hi])
        self.lo, self.hi = lo, hi


class Batch(Grid):
    """A Grid over an explicit list of requests (for scalar PDP evaluation)."""

    def __init__(self, domains, reqs):
        self.domains = domains
        self.attrs = list(domains)
        self.N = len(reqs)
        self.cat = {a: {v: i for i, v in enumerate(domains[a])} for a in self.attrs
                    if not isinstance(domains[a], IntRange)
                    and not all(isinstance(v, (int, np.integer)) for v in domains[a])}
        self.col = {}
        for a in self.attrs:
            if a in self.cat:
                self.col[a] = np.array([self.cat[a][r[a]] for r in reqs], dtype=np.int32)
            else:
                self.col[a] = np.array([r[a] for r in reqs], dtype=np.int64)


class Encoder:
    def __init__(self, domains, prefix=""):
        self.dom = domains
        self.v = {}
        self.cons = []
        for a, vs in domains.items():
            x = z3.Int(prefix + a)
            self.v[a] = x
            if isinstance(vs, IntRange):
                self.cons.append(z3.And(x >= vs.lo, x <= vs.hi))
            elif all(isinstance(t, (int, np.integer)) for t in vs):
                self.cons.append(z3.Or([x == int(t) for t in vs]) if len(vs) < 64
                                 else z3.And(x >= min(vs), x <= max(vs)))
            else:
                self.cons.append(z3.And(x >= 0, x < len(vs)))
        self.cat = {a: {t: i for i, t in enumerate(vs)} for a, vs in domains.items()
                    if not isinstance(vs, IntRange) and not all(isinstance(t, (int, np.integer)) for t in vs)}

    def pred(self, pr):
        x = self.v[pr.attr]
        val = pr.val
        if pr.attr in self.cat:
            m = self.cat[pr.attr]
            if pr.op == "in":
                return z3.Or([x == m[t] for t in val])
            return x == m[val] if pr.op == "eq" else x != m[val]
        if pr.op == "in":
            return z3.Or([x == int(t) for t in val])
        return {"eq": x == val, "ne": x != val, "lt": x < val, "le": x <= val,
                "gt": x > val, "ge": x >= val}[pr.op]

    def expr(self, e, vars_):
        if e is None:
            return z3.BoolVal(True)
        k = e[0]
        if k == "p":
            return self.pred(e[1])
        if k == "and":
            return z3.And([self.expr(x, vars_) for x in e[1]])
        if k == "or":
            return z3.Or([self.expr(x, vars_) for x in e[1]])
        if k == "not":
            return z3.Not(self.expr(e[1], vars_))
        if k == "var":
            return self.expr(vars_[e[1]], vars_)
        raise ValueError(e)

    def target(self, t):
        return z3.And([self.pred(x) for x in t]) if t else z3.BoolVal(True)

    def app(self, ps: PolicySet):
        """Rule id -> full applicability formula; container id -> region."""
        app, region, local, eff = {}, {}, {}, {}
        rt = self.target(ps.target)
        region[ps.id] = rt
        for pol in ps.policies:
            pt = z3.And(rt, self.target(pol.target))
            region[pol.id] = pt
            for r in pol.rules:
                lo = z3.And(self.target(r.target), self.expr(r.cond, pol.vars))
                local[r.id] = lo
                app[r.id] = z3.And(pt, lo)
                eff[r.id] = EFF[r.effect]
        return app, region, local, eff

    def decision(self, ps: PolicySet):
        """Z3 integer term for the root decision (NA=0, P=1, D=2)."""
        def comb(alg, rs):
            if not rs:
                return z3.IntVal(NA)
            if alg == "FA":
                out = z3.IntVal(NA)
                for r in reversed(rs):
                    out = z3.If(r != NA, r, out)
                return out
            anyP = z3.Or([r == P for r in rs])
            anyD = z3.Or([r == D for r in rs])
            if alg == "DO":
                return z3.If(anyD, D, z3.If(anyP, P, NA))
            return z3.If(anyP, P, z3.If(anyD, D, NA))
        _, _, local, eff = self.app(ps)
        pols = []
        for pol in ps.policies:
            rs = [z3.If(local[r.id], eff[r.id], NA) for r in pol.rules]
            pols.append(z3.If(self.target(pol.target), comb(pol.alg, rs), NA))
        return z3.If(self.target(ps.target), comb(ps.alg, pols), NA)

    def model_to_request(self, m, rng=None):
        out = {}
        for a, vs in self.dom.items():
            val = m.eval(self.v[a], model_completion=True).as_long()
            out[a] = vs[val] if a in self.cat else int(val)
        return out


def _syntactic_disjoint(ra, rb, pa, pb):
    """Cheap pre-filter: two 'eq'/'in' predicates on the same attribute with
    disjoint value sets make the rules disjoint (sound, never prunes overlap)."""
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
    A = sets(list(ra.target) + list(pa.target))
    B = sets(list(rb.target) + list(pb.target))
    return any(a in B and not (A[a] & B[a]) for a in A)


class SMTTPG:
    """Interaction edges computed with Z3 (same definition as tpg.TPG)."""

    def __init__(self, ps: PolicySet, dom, enc: Encoder | None = None, timeout_ms=5000):
        self.ps = ps
        self.enc = enc or Encoder(dom)
        self.app, self.region, self.local, self.eff = self.enc.app(ps)
        self.edges = set()
        self.rules_of, self.parent_of = {}, {}
        self.queries = self.pruned = 0
        rules = []
        for pol in ps.policies:
            self.rules_of[pol.id] = [r.id for r in pol.rules]
            for r in pol.rules:
                rules.append((pol, r))
                self.parent_of[r.id] = pol.id
        self.rules_of[ps.id] = [r.id for _, r in rules]
        s = z3.Solver()
        s.set("timeout", timeout_ms)
        s.add(*self.enc.cons)
        for i in range(len(rules)):
            pa, ra = rules[i]
            for j in range(i + 1, len(rules)):
                pb, rb = rules[j]
                if ra.effect == rb.effect:
                    continue
                if _syntactic_disjoint(ra, rb, pa, pb) or _syntactic_disjoint(rb, ra, pb, pa):
                    self.pruned += 1
                    continue
                self.queries += 1
                s.push()
                s.add(self.app[ra.id], self.app[rb.id])
                res = s.check()
                s.pop()
                if res == z3.unsat:
                    continue          # 'unknown' keeps the edge (sound)
                alg = pa.alg if pa.id == pb.id else ps.alg
                if alg == "FA":
                    self.edges.add(("precedes", "R:" + ra.id, "R:" + rb.id, alg))
                else:
                    a, b = sorted(("R:" + ra.id, "R:" + rb.id))
                    self.edges.add(("overrides", a, b, alg))


def solve(enc: Encoder, formula, rng, k=1, timeout_ms=5000):
    """Up to k diverse solutions: random soft hints on attribute values."""
    out = []
    s = z3.Solver()
    s.set("timeout", timeout_ms)
    s.add(*enc.cons)
    s.add(formula)
    for _ in range(k):
        s.push()
        # random phase hints: try a random value for one random attribute
        a = list(enc.dom)[int(rng.integers(len(enc.dom)))]
        vs = enc.dom[a]
        if isinstance(vs, IntRange):
            hint = enc.v[a] >= int(rng.integers(vs.lo, vs.hi + 1))
        elif a in enc.cat:
            hint = enc.v[a] == int(rng.integers(len(vs)))
        else:
            hint = enc.v[a] == int(vs[int(rng.integers(len(vs)))])
        s.add(hint)
        r = s.check()
        m = s.model() if r == z3.sat else None
        s.pop()
        if m is None:
            if s.check() != z3.sat:
                break
            m = s.model()
        out.append(enc.model_to_request(m))
        s.add(z3.Or([enc.v[x] != m.eval(enc.v[x], model_completion=True) for x in enc.dom]))
    return out
