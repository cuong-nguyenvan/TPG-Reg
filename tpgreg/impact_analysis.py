"""Identifier-anchored difference of two TPGs and the Behavioral Impact Set
(BIS), computed by a level-monotone closure over interaction edges."""
from __future__ import annotations
from .typed_policy_graph import TPG, INTER


def diff_bis(g1: TPG, g2: TPG, use=("precedes", "overrides", "scopes", "refers")):
    """Return (CH, BIS_R, container_seeds, delta) for the enabled propagation kinds."""
    n1, n2 = g1.nodes, g2.nodes
    added = set(n2) - set(n1)
    deleted = set(n1) - set(n2)
    updated = {k for k in set(n1) & set(n2) if n1[k] != n2[k]}
    delta_v = added | deleted | updated
    inter = tuple(t for t in INTER if t in use)
    e1 = {e for e in g1.edges if e[0] in inter}
    e2 = {e for e in g2.edges if e[0] in inter}
    delta_e = e1 ^ e2

    CH, cont_seeds = set(), set()
    for nid in delta_v:
        typ = (n1.get(nid) or n2.get(nid))[0]
        if typ == "Attribute":
            continue
        # rule-level elements
        if nid.startswith("R:"):
            CH.add(nid[2:])
        elif nid.startswith(("T:R:", "C:R:")):
            CH.add(nid.split("R:", 1)[1])
        elif nid.startswith(("P:", "T:P:", "ALG:P:")):
            pid = nid.split("P:", 1)[1]
            if "scopes" in use:
                CH |= set(g1.rules_of.get(pid, [])) | set(g2.rules_of.get(pid, []))
            else:
                cont_seeds.add(pid)
        elif nid.startswith(("T:S:", "ALG:S:", "S:")):
            if "scopes" in use:
                CH |= set(g1.rules_of[g1.ps.id]) | set(g2.rules_of[g2.ps.id])
            else:
                cont_seeds.add(g1.ps.id)
        elif nid.startswith("V:"):
            if "refers" in use:
                for g in (g1, g2):
                    CH |= {e[2][2:] for e in g.edges if e[0] == "refers" and e[1] == nid}
            else:
                cont_seeds.add(nid[2:].split(".")[0])
    for e in delta_e:
        CH.add(e[1][2:])
        CH.add(e[2][2:])
    # level-monotone lateral closure: a rule reached through an interaction
    # edge resolved at container level L may only propagate through edges
    # resolved at a strictly higher container (smaller level)
    level = {r: 2 for r in CH}
    followed = set()
    frontier = list(CH)
    E = e1 | e2
    while frontier:
        nxt = []
        for x in frontier:
            for e in E:
                a, b = e[1][2:], e[2][2:]
                if x not in (a, b):
                    continue
                lv = edge_level(g1, g2, a, b)
                if lv >= level[x]:
                    continue
                y = b if x == a else a
                followed.add(e)
                if level.get(y, -1) < lv:
                    level[y] = lv
                    nxt.append(y)
        frontier = nxt
    bis = set(level)
    return CH, bis, cont_seeds, followed


def edge_level(g1, g2, a, b):
    """1 if both rules are in the same policy (in either version), else 0."""
    for g in (g1, g2):
        pa, pb = g.parent_of.get(a), g.parent_of.get(b)
        if pa is not None and pa == pb:
            return 1
    return 0
