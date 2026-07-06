# Replication package — Rainfall Shocks and Household Income (synthetic fixture)

Everything in this package is fabricated. It exists to exercise an audit pipeline.

## Data

| File | Description |
| --- | --- |
| `data/households.csv` | Household survey panel (public 1-in-20 subsample), three villages, two waves. |
| `data/rainfall_stations.csv` | Station-level rainfall used to construct the shock variable. |

## Run order

1. `do/build_panel.do` — builds `output/panel.dta` and `output/panel.csv`.
2. `do/analysis.do` — estimates the main specification, writes `artifacts/tab1.tex`.
3. `py/make_figures.py` — writes `artifacts/fig1_income_trends.pdf`.

## Output mapping

| Paper object | Producing script |
| --- | --- |
| Table 1 | `do/analysis.do` |
| Figure 1 | `py/make_figures.py` |

## Requirements

Stata 17+ (`esttab` from ssc), Python 3 with pandas and matplotlib.
