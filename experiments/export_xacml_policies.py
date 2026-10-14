"""Export the benchmark policy sets and the versions of the financial
example to XACML 2.0 XML.

Usage: python3 export_xacml_policies.py <out dir>
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".."))

import os, sys
from xml.dom import minidom
from tpgreg.benchmarks import DATASETS, fin
from tpgreg.xacml_export import Exporter
from tpgreg.benchmarks import FIN_DOM

def pretty(x):
    return minidom.parseString(x.encode()).toprettyxml(indent="  ")


OUT = sys.argv[1] if len(sys.argv) > 1 else "../results/xacml_policies"
os.makedirs(OUT, exist_ok=True)
for name, (mk, dom) in DATASETS.items():
    open(f"{OUT}/{name}.xml", "w").write(pretty(Exporter(dom).policyset(mk())))
for tag, (alg, t) in {"FIN_v1": ("DO", 5), "FIN_commitA": ("DO", 8), "FIN_commitB": ("FA", 5)}.items():
    open(f"{OUT}/{tag}.xml", "w").write(pretty(Exporter(FIN_DOM).policyset(fin(alg, t))))
print("written:", sorted(os.listdir(OUT)))
