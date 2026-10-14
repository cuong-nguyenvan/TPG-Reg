"""Mutation-based simulation of policy evolution (one edit per evolution)."""
import copy
import numpy as np
from .policy_model import Rule, Pred, p

ALGS = ["DO", "PO", "FA"]


def _preds(e, path=()):
    if e is None:
        return
    k = e[0]
    if k == "p":
        yield path, e[1]
    elif k in ("and", "or"):
        for i, x in enumerate(e[1]):
            yield from _preds(x, path + (i,))
    elif k == "not":
        yield from _preds(e[1], path + (0,))


def _replace(e, path, new):
    if not path:
        return ("p", new)
    k = e[0]
    if k in ("and", "or"):
        xs = list(e[1])
        xs[path[0]] = _replace(xs[path[0]], path[1:], new)
        return (k, tuple(xs))
    if k == "not":
        return ("not", _replace(e[1], path[1:], new))
    raise ValueError


def mutate_pred(pr: Pred, dom):
    vals = dom[pr.attr]
    numeric = all(isinstance(v, int) for v in vals)
    if pr.op == "in":
        v = tuple(pr.val)
        if len(v) > 1:
            return Pred(pr.attr, "in", v[1:])
        extra = next(x for x in vals if x not in v)
        return Pred(pr.attr, "in", v + (extra,))
    if numeric:
        return Pred(pr.attr, pr.op, pr.val + 2 if pr.val + 2 <= max(vals) else pr.val - 2)
    i = vals.index(pr.val)
    return Pred(pr.attr, pr.op, vals[(i + 1) % len(vals)])


def evolutions(ps, dom, seed=7):
    rng = np.random.default_rng(seed)
    out = []

    def emit(op, desc, ps2, edited):
        out.append({"op": op, "desc": desc, "ps": ps2, "edited": edited})

    numeric_attrs = [a for a, v in dom.items() if all(isinstance(x, int) for x in v) and len(v) > 4]
    for pi, pol in enumerate(ps.policies):
        for ri, r in enumerate(pol.rules):
            # CCF: change one predicate of target or condition
            for ti, pr in enumerate(r.target):
                ps2 = copy.deepcopy(ps)
                ps2.policies[pi].rules[ri].target[ti] = mutate_pred(pr, dom)
                emit("CCF", f"{r.id}.target[{ti}]", ps2, {r.id})
            for path, pr in _preds(r.cond):
                ps2 = copy.deepcopy(ps)
                rr = ps2.policies[pi].rules[ri]
                rr.cond = _replace(rr.cond, path, mutate_pred(pr, dom))
                emit("CCF", f"{r.id}.cond{list(path)}", ps2, {r.id})
            # CRE: flip effect
            ps2 = copy.deepcopy(ps)
            rr = ps2.policies[pi].rules[ri]
            rr.effect = "Deny" if r.effect == "Permit" else "Permit"
            emit("CRE", r.id, ps2, {r.id})
            # RDL: delete rule
            ps2 = copy.deepcopy(ps)
            del ps2.policies[pi].rules[ri]
            emit("RDL", r.id, ps2, {r.id})
            # RRO: swap with next rule
            if ri + 1 < len(pol.rules):
                ps2 = copy.deepcopy(ps)
                rs = ps2.policies[pi].rules
                rs[ri], rs[ri + 1] = rs[ri + 1], rs[ri]
                emit("RRO", f"{r.id}<->{pol.rules[ri + 1].id}", ps2, {r.id, pol.rules[ri + 1].id})
        # RAI: insert a new rule at the front and in the middle
        for k, pos in enumerate((0, len(pol.rules) // 2)):
            base = pol.rules[int(rng.integers(len(pol.rules)))]
            a = numeric_attrs[int(rng.integers(len(numeric_attrs)))]
            vals = dom[a]
            thr = vals[len(vals) // 2 + int(rng.integers(-2, 3))]
            nid = f"{pol.id}.N{k}"
            new = Rule(nid, "Deny" if base.effect == "Permit" else "Permit",
                       copy.deepcopy(base.target), p(a, "ge", thr))
            ps2 = copy.deepcopy(ps)
            ps2.policies[pi].rules.insert(pos, new)
            emit("RAI", f"{nid}@{pos}", ps2, {nid})
        # PTC: policy target change
        if pol.target:
            ps2 = copy.deepcopy(ps)
            ps2.policies[pi].target = []
            emit("PTC", f"{pol.id}.target:=any", ps2, {pol.id})
            ps2 = copy.deepcopy(ps)
            ps2.policies[pi].target[0] = mutate_pred(pol.target[0], dom)
            emit("PTC", f"{pol.id}.target[0]", ps2, {pol.id})
        # CAC: combining algorithm change
        for alg in ALGS:
            if alg != pol.alg:
                ps2 = copy.deepcopy(ps)
                ps2.policies[pi].alg = alg
                emit("CAC", f"{pol.id}:{pol.alg}->{alg}", ps2, {pol.id})
        # VDC: variable definition change
        for vid, ve in pol.vars.items():
            for path, pr in _preds(ve):
                ps2 = copy.deepcopy(ps)
                ps2.policies[pi].vars[vid] = _replace(ve, path, mutate_pred(pr, dom))
                emit("VDC", f"{pol.id}.{vid}{list(path)}", ps2, {pol.id})
        # PRO: swap with next policy
        if pi + 1 < len(ps.policies):
            ps2 = copy.deepcopy(ps)
            ps2.policies[pi], ps2.policies[pi + 1] = ps2.policies[pi + 1], ps2.policies[pi]
            emit("PRO", f"{pol.id}<->{ps.policies[pi + 1].id}", ps2, {pol.id, ps.policies[pi + 1].id})
    for alg in ALGS:
        if alg != ps.alg:
            ps2 = copy.deepcopy(ps)
            ps2.alg = alg
            emit("CAC", f"{ps.id}:{ps.alg}->{alg}", ps2, {ps.id})
    return out
