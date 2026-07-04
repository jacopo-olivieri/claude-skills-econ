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
ax.legend(["Non-shocked", "Shocked"])

plt.tight_layout()
plt.savefig("artifacts/fig1_income_trends.pdf")
