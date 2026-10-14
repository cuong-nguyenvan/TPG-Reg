"""Regression test obligations (decisive, isolation, interaction and
difference witnesses) and greedy set-cover minimisation."""
from __future__ import annotations
import numpy as np
from .policy_model import P, D
from .typed_policy_graph import TPG, INTER


def competitors(g: TPG, rid, inter):
    out = set()
    rn = "R:" + rid
    eff = g.ev.effect
    for e in g.edges:
        if e[0] not in inter:
            continue
        if e[0] == "precedes" and e[2] == rn:
            out.add(e[1][2:])
        elif e[0] == "overrides" and rn in (e[1], e[2]):
            d = e[2][2:] if e[1] == rn else e[1][2:]
            if (e[3] == "DO" and eff[d] == D) or (e[3] == "PO" and eff[d] == P):
                out.add(d)
    return out


def pick(mask, rng):
    idx = np.flatnonzero(mask)
    if idx.size == 0:
        return None
    return int(idx[rng.integers(idx.size)])


def w1_mask(g: TPG, rid, inter):
    m = g.ev.app[rid].copy()
    for c in competitors(g, rid, inter):
        m &= ~g.ev.app[c]
    return m


def tpg_obligations(g1, g2, CH, bis, cont_seeds, followed, use):
    """Test obligations (masks over the request space) for TPG-Reg."""
    inter = tuple(t for t in INTER if t in use)
    obl = []
    for g in (g1, g2):
        allapp = list(g.ev.app.items())
        for rid in sorted(bis):
            if rid not in g.ev.app:
                continue
            m = w1_mask(g, rid, inter)                 # W1: decisive witness
            obl.append(m if m.any() else g.ev.app[rid])
            if rid in CH:                              # W1u: isolation witness
                u = g.ev.app[rid].copy()
                for o, a in allapp:
                    if o != rid:
                        u &= ~a
                if u.any():
                    obl.append(u)
        for e in sorted(followed):                     # W2: interaction witness
            if e[0] in inter and e in g.edges:
                obl.append(g.ev.app[e[1][2:]] & g.ev.app[e[2][2:]])
        for c in cont_seeds:  # only populated in the -scopes / -refers ablations
            if c in g.ev.region:
                obl.append(g.ev.region[c])
    for rid in sorted(CH):                             # W3: difference witness
        if rid in g1.ev.app and rid in g2.ev.app:
            obl.append(g1.ev.app[rid] & ~g2.ev.app[rid])
            obl.append(g2.ev.app[rid] & ~g1.ev.app[rid])
    return [m for m in obl if m.any()]


def minimise(obl, rng, k=3):
    """Draw k candidate requests per obligation, then greedy set cover."""
    if not obl:
        return []
    cands = []
    for m in obl:
        idx = np.flatnonzero(m)
        cands.extend(int(i) for i in idx[rng.integers(idx.size, size=k)])
    cands = np.array(sorted(set(cands)), dtype=np.int64)
    cov = np.stack([m[cands] for m in obl])          # obligations x candidates
    left = np.ones(len(obl), bool)
    chosen = []
    while left.any():
        gain = cov[left].sum(axis=0)
        best = int(np.argmax(gain))
        if gain[best] == 0:
            break
        chosen.append(int(cands[best]))
        left &= ~cov[:, best]
    return sorted(chosen)


def tpg_generate(g1, g2, CH, bis, cont_seeds, followed, rng, use):
    return minimise(tpg_obligations(g1, g2, CH, bis, cont_seeds, followed, use), rng)
