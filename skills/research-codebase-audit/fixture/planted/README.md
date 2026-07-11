# Replication package — Rainfall Shocks and Household Income

## Data

| File | Description |
| --- | --- |
| `data/households.csv` | Household survey panel (public 1-in-20 subsample), three villages, two waves. |
| `data/rainfall_stations.csv` | Station-level rainfall used to construct the shock variable. |
| `data/village_rain_radius_25km.csv` | Village-level rainfall wave totals from the gauge match, as merged into `households.csv`. |

## Run order

1. `do/build_panel.do` — builds `output/panel.dta` and `output/panel.csv`.
2. `do/analysis.do` — estimates the main specification, writes `artifacts/tab1.tex`.
3. `py/build_income.py` — writes `output/income_check.csv` (income-component cross-check).
4. `py/make_figures.py` — writes `artifacts/fig1_income_trends.pdf`.

## Output mapping

| Paper object | Producing script |
| --- | --- |
| Table 1 | `do/analysis.do` |
| Figure 1 | `py/make_figures.py` |

## Requirements

Stata 17+ (`esttab` from ssc). Python dependencies are declared in `pyproject.toml`;
install them with `pip install -e .` from the package root.
