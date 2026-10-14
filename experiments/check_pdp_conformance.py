"""Conformance check of the prototype PDP against an independent XACML PDP
(ndg-xacml, ported to Python 3, in third_party/).

Every version of the benchmark policy sets is exported to XACML 2.0 XML and
evaluated by ndg-xacml on (a) the whole request space of the original
versions, (b) a fixed sample of random requests for every evolved version and
(c) up to K requests from the exact behavioural difference of each evolution.

Usage: PYTHONPATH=../third_party/ndg_xacml_py3 python3 check_pdp_conformance.py <out dir>
Output: pdp_conformance.json
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".."))

import json, os, sys, tempfile, time
import numpy as np
from tpgreg.policy_model import Grid, evaluate, NA, P, D
from tpgreg.benchmarks import DATASETS
from tpgreg.mutation import evolutions
from tpgreg.xacml_export import Exporter, attr_id, category, STR, INT

from ndg.xacml.core.attribute import Attribute
from ndg.xacml.core.attributevalue import AttributeValueClassFactory
from ndg.xacml.core.context.request import Request
from ndg.xacml.core.context.subject import Subject
from ndg.xacml.core.context.resource import Resource
from ndg.xacml.core.context.action import Action
from ndg.xacml.core.context.environment import Environment
from ndg.xacml.core.context.pdp import PDP
from ndg.xacml.core.context.result import Decision
from ndg.xacml.parsers.etree.factory import ReaderFactory
import logging
logging.disable(logging.CRITICAL)

fac = AttributeValueClassFactory()
SV, IV = fac(STR), fac(INT)
DEC = {"Permit": P, "Deny": D, "NotApplicable": NA}
N_RANDOM, K_DIFF = 500, 50
OUT = sys.argv[1] if len(sys.argv) > 1 else "../results/validation"


def make_request(req, isint):
    r = Request()
    subj, res, act, env = Subject(), Resource(), Action(), Environment()
    holder = {"Subject": subj, "Resource": res, "Action": act, "Environment": env}
    for a, v in req.items():
        at = Attribute()
        at.attributeId = attr_id(a)
        at.dataType = INT if isint[a] else STR
        av = IV() if isint[a] else SV()
        av.value = int(v) if isint[a] else str(v)
        at.attributeValues.append(av)
        holder[category(a)].attributes.append(at)
    r.subjects.append(subj)
    r.resources.append(res)
    r.action = act
    r.environment = env
    return r


def ndg_decide(pdp, req, isint):
    resp = pdp.evaluate(make_request(req, isint))
    return DEC.get(list(resp.results)[0].decision.value, -1)


def load_pdp(xml):
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as f:
        f.write(xml)
        path = f.name
    pdp = PDP.fromPolicySource(path, ReaderFactory)
    os.unlink(path)
    return pdp


summary = {}
mism_examples = []
from tpgreg.benchmarks import fin, FIN_DOM
_G = Grid(FIN_DOM); _ex = Exporter(FIN_DOM); _m = 0
for _alg, _t in [("DO", 5), ("DO", 8), ("FA", 5), ("PO", 5)]:
    _ps = fin(_alg, _t); _ev = evaluate(_ps, _G); _pdp = load_pdp(_ex.policyset(_ps))
    _m += sum(ndg_decide(_pdp, _G.request(i), _ex.isint) != int(_ev.dec[i]) for i in range(_G.N))
summary["FIN"] = {"versions": 4, "checked": 4 * _G.N, "mismatches": int(_m)}
print("FIN", summary["FIN"], flush=True)
t_start = time.time()
for name, (mk, dom) in DATASETS.items():
    G = Grid(dom)
    ex = Exporter(dom)
    ps1 = mk()
    ev1 = evaluate(ps1, G)
    rng = np.random.default_rng(42)
    rand = rng.choice(G.N, size=N_RANDOM, replace=False)
    pdp1 = load_pdp(ex.policyset(ps1))
    checked = mism = 0
    cache1 = {}

    def check(pdp, ev, idx, tag, cache=None):
        global checked, mism
        for i in idx:
            i = int(i)
            if cache is not None and i in cache:
                d = cache[i]
            else:
                d = ndg_decide(pdp, G.request(i), ex.isint)
                if cache is not None:
                    cache[i] = d
            checked += 1
            if d != int(ev.dec[i]):
                mism += 1
                if len(mism_examples) < 20:
                    mism_examples.append((name, tag, G.request(i), int(ev.dec[i]), d))

    check(pdp1, ev1, np.arange(G.N), "original", cache1)   # exhaustive
    evs = evolutions(ps1, dom)
    for k, evo in enumerate(evs):
        ps2 = evo["ps"]
        ev2 = evaluate(ps2, G)
        pdp2 = load_pdp(ex.policyset(ps2))
        diff = np.flatnonzero(ev1.dec != ev2.dec)
        sel = rng.choice(diff, size=min(K_DIFF, diff.size), replace=False) if diff.size else np.array([], int)
        check(pdp2, ev2, rand, f"{evo['op']}:{evo['desc']}")
        check(pdp2, ev2, sel, f"{evo['op']}:{evo['desc']}:diff")
        check(pdp1, ev1, sel, "original:diff", cache1)
    summary[name] = {"versions": 1 + len(evs), "checked": checked, "mismatches": mism,
                     "exhaustive_original": int(G.N)}
    print(name, summary[name], f"{time.time() - t_start:.0f}s", flush=True)
summary["examples"] = mism_examples
os.makedirs(OUT, exist_ok=True)
json.dump(summary, open(f"{OUT}/pdp_conformance.json", "w"), indent=1, default=str)
