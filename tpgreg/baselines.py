"""Baselines: syntactic AST difference with upward-only propagation (AST-Up)
and path-based flow-graph suites (one request per rule path) minimised by
greedy set cover or by a genetic algorithm."""
from __future__ import annotations
import numpy as np
from .test_generation import pick, minimise


def ast_positions(ps):
    pos = {}
    for i, pol in enumerate(ps.policies):
        pos["P:" + pol.id] = i
        for j, r in enumerate(pol.rules):
            pos["R:" + r.id] = j
    return pos


def ast_diff(ps1, ps2, g1, g2):
    """Syntactic tree diff with order-sensitive sibling matching and
    upward-only propagation. Returns (rule seeds/ancestors, container set)."""
    n1, n2 = g1.nodes, g2.nodes
    struct = lambda n: {k: v for k, v in n.items() if v[0] != "Attribute"}
    s1, s2 = struct(n1), struct(n2)
    changed = (set(s1) ^ set(s2)) | {k for k in set(s1) & set(s2) if s1[k] != s2[k]}
    pos1, pos2 = ast_positions(ps1), ast_positions(ps2)
    moved = {k for k in set(pos1) & set(pos2) if pos1[k] != pos2[k]}
    rules, conts = set(), set()
    parent = {}
    for g in (g1, g2):
        for pid, rids in g.rules_of.items():
            if pid != g.ps.id:
                for r in rids:
                    parent[r] = pid
    for nid in changed | moved:
        if nid.startswith("R:"):
            rules.add(nid[2:])
        elif nid.startswith(("T:R:", "C:R:")):
            rules.add(nid.split("R:", 1)[1])
        elif nid.startswith(("P:", "T:P:", "ALG:P:")):
            conts.add(nid.split("P:", 1)[1])
        elif nid.startswith("V:"):
            conts.add(nid[2:].split(".")[0])
        elif nid.startswith(("S:", "T:S:", "ALG:S:")):
            conts.add(ps1.id)
    # upward propagation: rule -> policy -> policy set
    for r in rules:
        if r in parent:
            conts.add(parent[r])
    if rules or conts:
        conts.add(ps1.id)
    return rules, conts


def ast_generate(g1, g2, rules, conts, rng):
    obl = []
    for g in (g1, g2):
        for rid in sorted(rules):
            if rid in g.ev.app and g.ev.app[rid].any():
                obl.append(g.ev.app[rid])
        for c in sorted(conts):
            if c in g.ev.region and g.ev.region[c].any():
                obl.append(g.ev.region[c])
    return minimise(obl, rng)


def xfg_suite(g, rng):
    """Path-based suite: one request per rule satisfying ancestor targets,
    rule target and condition; expected decision = rule effect."""
    out = []
    for pol in g.ps.policies:
        for r in pol.rules:
            q = pick(g.ev.app[r.id], rng)
            if q is not None:
                out.append((q, g.ev.effect[r.id], r.id))
    return out


def xfg_min_suite(g, rng):
    """Path-based suite minimised for full rule coverage (greedy set cover,
    the same objective as the GA of the flow-graph approach)."""
    obl = [g.ev.app[r.id] for pol in g.ps.policies for r in pol.rules if g.ev.app[r.id].any()]
    return minimise(obl, rng)


def ga_select(cov, rng, pop=50, gens=100, pc=0.8, pm=0.05, w=(0.7, 0.3)):
    """GA test-suite minimisation as specified for the flow-graph approach:
    binary encoding over TS_raw, F(C) = w1*Cov(C) + w2*(1 - |C|/M),
    tournament selection, single-point crossover (pc), bit-flip mutation (pm),
    best individual kept across generations. cov: obligations x candidates."""
    n_obl, M = cov.shape
    if M == 0:
        return []
    X = rng.random((pop, M)) < 0.5

    def fit(X):
        covered = (X.astype(np.int32) @ cov.T.astype(np.int32)) > 0      # pop x obl
        return w[0] * covered.mean(axis=1) + w[1] * (1 - X.sum(axis=1) / M)

    f = fit(X)
    best, bestf = X[np.argmax(f)].copy(), f.max()
    for _ in range(gens):
        a, b = rng.integers(pop, size=(2, pop)), rng.integers(pop, size=(2, pop))
        p1 = X[np.where(f[a[0]] >= f[a[1]], a[0], a[1])]
        p2 = X[np.where(f[b[0]] >= f[b[1]], b[0], b[1])]
        cut = rng.integers(1, max(M, 2), size=pop)
        mask = np.arange(M)[None, :] < cut[:, None]
        do = rng.random(pop) < pc
        child = np.where(do[:, None], np.where(mask, p1, p2), p1)
        child ^= rng.random((pop, M)) < pm
        X = child
        f = fit(X)
        if f.max() > bestf:
            best, bestf = X[np.argmax(f)].copy(), f.max()
    return list(np.flatnonzero(best))


def xfg_ga_suite(g, rng):
    """Path-based suite (one request per rule) minimised by the GA."""
    rids = [r.id for pol in g.ps.policies for r in pol.rules if g.ev.app[r.id].any()]
    raw = [pick(g.ev.app[r], rng) for r in rids]
    cov = np.stack([g.ev.app[r][np.array(raw)] for r in rids])
    return sorted({raw[i] for i in ga_select(cov, rng)})
