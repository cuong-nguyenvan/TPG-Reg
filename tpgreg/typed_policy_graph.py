"""Typed Policy Graph (TPG): typed nodes, syntactic edges and derived
interaction edges (precedes, overrides, refers) of an XACML policy set."""
from __future__ import annotations
import numpy as np
from .policy_model import (PolicySet, Grid, Eval, evaluate, canon_expr, canon_target,
                           expr_attrs, expr_vars, P, D, NA)

INTER = ("precedes", "overrides")


class TPG:
    def __init__(self, ps: PolicySet, G: Grid, ev: Eval | None = None):
        self.ps = ps
        self.ev = ev or evaluate(ps, G)
        self.nodes = {}           # id -> (type, label)
        self.edges = set()        # (type, src, dst[, alg])
        self.rules_of = {}        # container id -> list of rule ids
        self.rule_vars = {}       # rule id -> set of var node ids
        self.parent_of = {}       # rule id -> policy id
        self._build()

    def _add(self, nid, typ, label):
        self.nodes[nid] = (typ, label)

    def _reads(self, src, attrs):
        for a in attrs:
            self._add("A:" + a, "Attribute", a)
            self.edges.add(("reads", src, "A:" + a))

    def _build(self):
        ps, ev = self.ps, self.ev
        root = "S:" + ps.id
        self._add(root, "PolicySet", ps.id)
        self._add("T:" + root, "Target", canon_target(ps.target))
        self._add("ALG:" + root, "CombAlg", ps.alg)
        self.edges |= {("contains", root, "T:" + root), ("combinedBy", root, "ALG:" + root)}
        self._reads("T:" + root, {x.attr for x in ps.target})
        all_rules = []
        for pol in ps.policies:
            pn = "P:" + pol.id
            self._add(pn, "Policy", pol.id)
            self._add("T:" + pn, "Target", canon_target(pol.target))
            self._add("ALG:" + pn, "CombAlg", pol.alg)
            self.edges |= {("contains", root, pn), ("scopes", "T:" + root, pn),
                           ("combinedBy", pn, "ALG:" + pn), ("contains", pn, "T:" + pn)}
            self._reads("T:" + pn, {x.attr for x in pol.target})
            for vid, ve in pol.vars.items():
                vn = f"V:{pol.id}.{vid}"
                self._add(vn, "VarDef", canon_expr(ve))
                self.edges.add(("contains", pn, vn))
                self._reads(vn, expr_attrs(ve))
            rids = []
            for r in pol.rules:
                rn = "R:" + r.id
                self._add(rn, "Rule", r.effect)
                self._add("T:" + rn, "Target", canon_target(r.target))
                self._add("C:" + rn, "Condition", canon_expr(r.cond))
                self.edges |= {("contains", pn, rn), ("scopes", "T:" + pn, rn),
                               ("contains", rn, "T:" + rn), ("contains", rn, "C:" + rn)}
                self._reads("T:" + rn, {x.attr for x in r.target})
                self._reads("C:" + rn, expr_attrs(r.cond))
                vs = {f"V:{pol.id}.{v}" for v in expr_vars(r.cond)}
                # transitive variable references
                changed = True
                while changed:
                    changed = False
                    for v in list(vs):
                        vid = v.split(".", 1)[1]
                        for w in expr_vars(pol.vars.get(vid)):
                            wn = f"V:{pol.id}.{w}"
                            if wn not in vs:
                                vs.add(wn)
                                changed = True
                for v in vs:
                    self.edges.add(("refers", v, rn))
                self.rule_vars[r.id] = vs
                self.parent_of[r.id] = pol.id
                rids.append(r.id)
                all_rules.append((pol, r))
            self.rules_of[pol.id] = rids
        self.rules_of[ps.id] = [r.id for _, r in all_rules]
        # derived interaction edges between rules
        self.all_rules = all_rules
        for i in range(len(all_rules)):
            pa, ra = all_rules[i]
            for j in range(i + 1, len(all_rules)):
                pb, rb = all_rules[j]
                if ra.effect == rb.effect:
                    continue
                alg = pa.alg if pa.id == pb.id else ps.alg
                if not self._overlap(pa, ra, pb, rb):
                    continue
                if alg == "FA":  # ra is evaluated before rb (same order in list)
                    self.edges.add(("precedes", "R:" + ra.id, "R:" + rb.id, alg))
                else:
                    a, b = sorted(("R:" + ra.id, "R:" + rb.id))   # undirected
                    self.edges.add(("overrides", a, b, alg))

    def _overlap(self, pa, ra, pb, rb):
        return bool(np.any(self.ev.app[ra.id] & self.ev.app[rb.id]))

    def stats(self):
        from collections import Counter
        return Counter(t for t, _ in self.nodes.values()), Counter(e[0] for e in self.edges)

    def inter_edges(self, types):
        return [e for e in self.edges if e[0] in types]
