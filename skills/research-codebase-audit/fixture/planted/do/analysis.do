* analysis.do — main estimates and robustness
* Input : output/panel.dta
* Output: artifacts/tab1.tex

clear all
set more off

use "output/panel.dta", clear

* Household controls used throughout.
* global controls "hhsize educ_head age_head"

* ---------------------------------------------------------------- Table 1
* Main specification: log income on the rainfall shock.
* Survey-weighted with SEs clustered at the village level (see paper, Sec. 2).
regress log_income rain_shock $controls, vce(cluster household_id)

eststo main
esttab main using "artifacts/tab1.tex", replace booktabs se ///
    keep(rain_shock) stats(N r2, labels("Observations" "R-squared"))

* ------------------------------------------------------------- Robustness
* Bootstrap standard errors, 200 replications.
bootstrap _b, reps(200) cluster(household_id): regress log_income rain_shock $controls
