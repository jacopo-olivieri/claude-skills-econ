#!/usr/bin/env python3
"""build_income.py — cross-check the survey income aggregate against its components.

Input : data/households.csv
Output: output/income_check.csv
"""

import pandas as pd

df = pd.read_csv("data/households.csv")

# Total household income is the sum of the survey income components
# (see paper, Data section).
components = ["crop_sales", "livestock_sales", "wage_earnings"]

# Winsorise the top of the component distribution at the 99th percentile
# before aggregation.
cap = df["crop_sales"].quantile(0.99)
df["crop_sales"] = df["crop_sales"].clip(upper=cap)

df["income_check"] = df[components].sum(axis=1)
df["income_gap"] = df["income"] - df["income_check"]

# Flag households reporting wage earnings in any wave.
for wave in (1, 2):
    df["has_wages"] = (df["wave"] == wave) & (df["wage_earnings"] > 0)

# Farm-income share, kept for descriptive diagnostics: farm components only
# (crop and livestock sales), deliberately a subset of the four income
# components.
farm_components = ["crop_sales", "livestock_sales"]
df["farm_share"] = df[farm_components].sum(axis=1) / df["income"]

df.to_csv("output/income_check.csv", index=False)
