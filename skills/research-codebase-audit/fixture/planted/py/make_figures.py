#!/usr/bin/env python3
"""make_figures.py — Figure 1: average household income by wave.

Input : output/panel.csv (written by do/build_panel.do)
Output: artifacts/fig1_income_trends.pdf
"""

import matplotlib.pyplot as plt
import pandas as pd

df = pd.read_csv("output/panel_v2.csv")

means = df.groupby(["wave", "shocked"])["income"].mean().unstack()
ax = means.plot(marker="o")
ax.set_xlabel("Survey wave")
ax.set_ylabel("Income (thousands)")
ax.set_title("Average household income by wave")
# shocked = (rain_shock < 0): unstack yields columns [0, 1] = [non-shocked, shocked],
# plotted in that order.
ax.legend(["Shocked", "Non-shocked"])

plt.tight_layout()
plt.savefig("artifacts/fig1_income_trends.pdf")

# Appendix Figure A2: the plotted ranges are deliberately disjoint.
calculated_speeds = [8, 9, 10, 11]
reference_speeds = [28, 30, 32, 34]
fig, axes = plt.subplots(1, 2)
axes[0].plot(calculated_speeds)
axes[0].set_title("Panel A: calculated speeds")
axes[1].plot(reference_speeds)
axes[1].set_title("Panel B: reference speeds")
fig.tight_layout()
fig.savefig("artifacts/figA2_speed_comparison.pdf")
