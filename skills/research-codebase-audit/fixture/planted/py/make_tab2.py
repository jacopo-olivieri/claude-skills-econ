#!/usr/bin/env python3
"""make_tab2.py — Table 2: mean income per household member, by wave.

Input : output/income_capita.csv
Output: artifacts/tab2.tex
"""

import pandas as pd

df = pd.read_csv("output/income_capita.csv")
by_wave = df.groupby("wave")["income_pc"].mean()

lines = [
    "\\begin{tabular}{lc}",
    "\\toprule",
    " & Income per member \\\\",
    "\\midrule",
]
for wave, value in by_wave.items():
    lines.append(f"Wave {wave} & {value:,.0f} \\\\")
lines += [
    "\\midrule",
    f"Observations & {len(df)} \\\\",
    "\\bottomrule",
    "\\end{tabular}",
]
with open("artifacts/tab2.tex", "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
