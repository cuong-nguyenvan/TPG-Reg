"""Bar chart of evolution detection rate (EDR) and affected-rule exposure
(ARE) per method over all behaviour-changing single-edit evolutions.

Usage: python3 plot_detection_rates.py <single_edit_evolution dir>
Output: detection_rates.png
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".."))

import json, sys, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
R = sys.argv[1] if len(sys.argv) > 1 else "../results/single_edit_evolution"
A = json.load(open(f"{R}/summary.json"))
ms = ["Retest-all(GA)", "XFG-Regen(GA)", "AST-Up", "TPG-Reg", "TPG-Reg+D"]
labels = ["Retest-all\n(GA)", "XFG-Regen\n(GA)", "AST-Up", "TPG-Reg\n(witness)", "TPG-Reg\n(+distinguish.)"]
edr = [100 * A["ALL"][m]["EDR"] for m in ms]; edr_sd = [100 * A["ALL"][m]["EDR_sd"] for m in ms]
are = [100 * A["ALL"][m]["ARE"] for m in ms]; are_sd = [100 * A["ALL"][m]["ARE_sd"] for m in ms]
size = [A["ALL"][m]["size_ch"] for m in ms]
plt.rcParams.update({"font.size": 10, "font.family": "DejaVu Sans"})
fig, ax = plt.subplots(figsize=(6.6, 3.0), dpi=300)
x = np.arange(len(ms)); w = 0.36
b1 = ax.bar(x - w/2 - 0.01, edr, w, yerr=edr_sd, color="#2a78d6", label="EDR (evolution detected)", capsize=2, error_kw={"lw": 0.8})
b2 = ax.bar(x + w/2 + 0.01, are, w, yerr=are_sd, color="#eb6834", label="ARE (affected rules exposed)", capsize=2, error_kw={"lw": 0.8},
            hatch="////", edgecolor="white", linewidth=0)
for xi, v in zip(x - w/2, edr): ax.text(xi, v + 2.5, f"{v:.0f}", ha="center", fontsize=7.5, color="#333")
for xi, v in zip(x + w/2, are): ax.text(xi, v + 2.5, f"{v:.0f}", ha="center", fontsize=7.5, color="#333")
ax.set_xticks(x, [f"{l}\n|T|={s:.1f}" for l, s in zip(labels, size)], fontsize=8)
ax.set_ylabel("%"); ax.set_ylim(0, 112)
ax.spines[["top", "right"]].set_visible(False)
ax.yaxis.grid(True, color="#e5e5e5", lw=0.6); ax.set_axisbelow(True)
ax.legend(loc="upper left", fontsize=8, frameon=False, ncol=2)
fig.tight_layout()
fig.savefig(f"{R}/detection_rates.png")
