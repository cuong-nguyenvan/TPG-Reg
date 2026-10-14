"""Policy model and vectorised PDP for the TPG-Reg prototype.

Simplified XACML 3.0: one root PolicySet of Policies of Rules; targets are
conjunctions of predicates; conditions are Boolean expressions over predicates
and policy-level VariableDefinitions; combining algorithms deny-overrides (DO),
permit-overrides (PO) and first-applicable (FA). Decisions: NA=0, P=1, D=2.
Indeterminate (missing attributes, function errors) is not modelled.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np

NA, P, D = 0, 1, 2
EFF = {"Permit": P, "Deny": D}
DEC_NAME = {NA: "NotApplicable", P: "Permit", D: "Deny"}


@dataclass
class Pred:
    attr: str
    op: str          # eq ne lt le gt ge in
    val: object      # tuple for 'in'

    def canon(self):
        v = tuple(sorted(self.val, key=str)) if self.op == "in" else self.val
        return f"{self.attr} {self.op} {v}"


@dataclass
class Rule:
    id: str
    effect: str
    target: list = field(default_factory=list)   # list[Pred], conjunction
    cond: tuple | None = None                     # expression tree


@dataclass
class Policy:
    id: str
    alg: str
    target: list = field(default_factory=list)
    rules: list = field(default_factory=list)
    vars: dict = field(default_factory=dict)      # var id -> expr


@dataclass
class PolicySet:
    id: str
    alg: str
    target: list = field(default_factory=list)
    policies: list = field(default_factory=list)


# ---------------------------------------------------------------- expressions
def p(attr, op, val):
    return ("p", Pred(attr, op, val))


def AND(*xs):
    return ("and", tuple(xs))


def OR(*xs):
    return ("or", tuple(xs))


def NOT(x):
    return ("not", x)


def VAR(v):
    return ("var", v)


def canon_expr(e):
    if e is None:
        return "true"
    k = e[0]
    if k == "p":
        return e[1].canon()
    if k in ("and", "or"):
        return k + "(" + ",".join(canon_expr(x) for x in e[1]) + ")"
    if k == "not":
        return "not(" + canon_expr(e[1]) + ")"
    if k == "var":
        return "var:" + e[1]
    raise ValueError(e)


def canon_target(t):
    return " & ".join(sorted(x.canon() for x in t)) or "any"


def expr_attrs(e, out=None):
    out = set() if out is None else out
    if e is None:
        return out
    k = e[0]
    if k == "p":
        out.add(e[1].attr)
    elif k in ("and", "or"):
        for x in e[1]:
            expr_attrs(x, out)
    elif k == "not":
        expr_attrs(e[1], out)
    return out


def expr_vars(e, out=None):
    out = set() if out is None else out
    if e is None:
        return out
    k = e[0]
    if k == "var":
        out.add(e[1])
    elif k in ("and", "or"):
        for x in e[1]:
            expr_vars(x, out)
    elif k == "not":
        expr_vars(e[1], out)
    return out


# ---------------------------------------------------------------- domain grid
class Grid:
    """All requests of a finite attribute domain, enumerated once."""

    def __init__(self, domains: dict):
        self.domains = domains
        self.attrs = list(domains)
        sizes = [len(domains[a]) for a in self.attrs]
        self.N = int(np.prod(sizes))
        idx = np.unravel_index(np.arange(self.N), sizes)
        self.col = {}
        for a, ix in zip(self.attrs, idx):
            vals = domains[a]
            if all(isinstance(v, (int, np.integer)) for v in vals):
                self.col[a] = np.asarray(vals)[ix]
            else:
                self.col[a] = ix.astype(np.int16)
        self.cat = {a: {v: i for i, v in enumerate(domains[a])}
                    for a in self.attrs
                    if not all(isinstance(v, (int, np.integer)) for v in domains[a])}

    def request(self, i):
        out = {}
        for a in self.attrs:
            c = self.col[a][i]
            out[a] = self.domains[a][int(c)] if a in self.cat else int(c)
        return out

    def pred(self, pr: Pred):
        c = self.col[pr.attr]
        v = pr.val
        if pr.attr in self.cat:
            m = self.cat[pr.attr]
            if pr.op == "eq":
                return c == m[v]
            if pr.op == "ne":
                return c != m[v]
            if pr.op == "in":
                return np.isin(c, [m[x] for x in v])
            raise ValueError(pr)
        if pr.op == "eq":
            return c == v
        if pr.op == "ne":
            return c != v
        if pr.op == "lt":
            return c < v
        if pr.op == "le":
            return c <= v
        if pr.op == "gt":
            return c > v
        if pr.op == "ge":
            return c >= v
        if pr.op == "in":
            return np.isin(c, list(v))
        raise ValueError(pr)

    def ones(self):
        return np.ones(self.N, dtype=bool)


def eval_expr(e, G: Grid, varmasks):
    if e is None:
        return G.ones()
    k = e[0]
    if k == "p":
        return G.pred(e[1])
    if k == "and":
        m = G.ones()
        for x in e[1]:
            m = m & eval_expr(x, G, varmasks)
        return m
    if k == "or":
        m = np.zeros(G.N, dtype=bool)
        for x in e[1]:
            m = m | eval_expr(x, G, varmasks)
        return m
    if k == "not":
        return ~eval_expr(e[1], G, varmasks)
    if k == "var":
        return varmasks[e[1]]
    raise ValueError(e)


def eval_target(t, G):
    m = G.ones()
    for pr in t:
        m = m & G.pred(pr)
    return m


def combine(alg, results):
    out = np.zeros_like(results[0]) if results else None
    if not results:
        return None
    if alg == "DO":
        anyP = np.zeros(out.shape, bool)
        anyD = np.zeros(out.shape, bool)
        for r in results:
            anyP |= r == P
            anyD |= r == D
        out[anyP] = P
        out[anyD] = D
    elif alg == "PO":
        anyP = np.zeros(out.shape, bool)
        anyD = np.zeros(out.shape, bool)
        for r in results:
            anyP |= r == P
            anyD |= r == D
        out[anyD] = D
        out[anyP] = P
    elif alg == "FA":
        for r in reversed(results):
            out = np.where(r != NA, r, out)
    else:
        raise ValueError(alg)
    return out


def child_decisive(alg, parent_dec, parent_res, results):
    out = []
    seen = np.zeros(parent_res.shape, bool)
    for r in results:
        if alg == "FA":
            d = parent_dec & (r != NA) & ~seen
            seen = seen | (r != NA)
        else:
            d = parent_dec & (r != NA) & (r == parent_res)
        out.append(d)
    return out


@dataclass
class Eval:
    dec: np.ndarray                 # root decision per request
    app: dict                       # rule id -> full applicability (incl. ancestor targets)
    decisive: dict                  # rule id -> bool mask
    region: dict                    # container id -> mask where container target (and ancestors) match
    effect: dict                    # rule id -> P/D
    parent: dict                    # rule id -> policy id


def evaluate(ps: PolicySet, G: Grid) -> Eval:
    ps_t = eval_target(ps.target, G)
    pol_res, app, region, effect, parent, rule_res_all = [], {}, {ps.id: ps_t}, {}, {}, {}
    for pol in ps.policies:
        pt = eval_target(pol.target, G)
        region[pol.id] = ps_t & pt
        vm = {}
        for vid, ve in pol.vars.items():
            vm[vid] = eval_expr(ve, G, vm)
        rres = []
        for r in pol.rules:
            local = eval_target(r.target, G) & eval_expr(r.cond, G, vm)
            app[r.id] = local & region[pol.id]
            effect[r.id] = EFF[r.effect]
            parent[r.id] = pol.id
            rr = np.where(local, EFF[r.effect], NA).astype(np.int8)
            rres.append(rr)
        rule_res_all[pol.id] = rres
        if rres:
            c = combine(pol.alg, rres)
            c = np.where(pt, c, NA).astype(np.int8)
        else:
            c = np.zeros(G.N, np.int8)
        pol_res.append(c)
    root = combine(ps.alg, pol_res) if pol_res else np.zeros(G.N, np.int8)
    root = np.where(ps_t, root, NA).astype(np.int8)
    decisive = {}
    pdec = child_decisive(ps.alg, root != NA, root, pol_res)
    for pol, pd, pr in zip(ps.policies, pdec, pol_res):
        rdec = child_decisive(pol.alg, pd, pr, rule_res_all[pol.id])
        for r, d in zip(pol.rules, rdec):
            decisive[r.id] = d
    return Eval(root, app, decisive, region, effect, parent)


def rule_index(ps: PolicySet):
    """rule id -> (policy index, rule index)"""
    out = {}
    for i, pol in enumerate(ps.policies):
        for j, r in enumerate(pol.rules):
            out[r.id] = (i, j)
    return out
