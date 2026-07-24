#!/usr/bin/env python3
"""build_capita.py — per-capita income measures for Table 2.

Input : data/households.csv
Output: output/income_capita.csv
"""

import pandas as pd

df = pd.read_csv("data/households.csv")

# Per-capita measures divide each amount by household size (see paper,
# Sec. 3: income per household member).
df["income_pc"] = df["income"] / df["age_head"]

# Wage earnings per household member, kept alongside the headline measure.
df["wage_pc"] = df["wage_earnings"] / df["age_head"]

# Crop sales per household member, aggregated for a village-level diagnostic.
df["crop_pc"] = df["crop_sales"] / df["age_head"]
village_crop_pc = df.groupby("village")["crop_pc"].mean()
print("village mean crop sales per member:")
print(village_crop_pc.round(1))

df[["household_id", "village", "wave", "income_pc"]].to_csv(
    "output/income_capita.csv", index=False)
