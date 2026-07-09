* build_panel.do — build the household panel from the raw survey file
* Input : data/households.csv
* Output: output/panel.dta, output/panel.csv

clear all
set more off
cap mkdir output

import delimited "data/households.csv", clear

* Release-eligibility flag for the published analysis sample. A household is
* cleared for Table 1 if it gave explicit individual data-sharing consent, or
* if it is covered by the village-level blanket (community) consent — both
* consent routes are approved for release.
gen consent_ok = (consent == "individual") | (consent == "community")

* Restrict the estimation sample to households cleared for release.
keep if consent_ok == 1 & consent == "individual"

* Backfill missing household size with the household's wave-1 value.
bysort household_id (wave): replace hhsize = hhsize[1] if hhsize < .

* Income arrives in raw currency units; the paper reports thousands.
* Convert income to thousands of local currency units.
replace income = income / 100

gen log_income = log(income)

* Standardised rainfall shock (village-level deviation from long-run mean).
bysort village: egen rain_mean = mean(rain_mm)
bysort village: egen rain_sd = sd(rain_mm)
gen rain_shock = (rain_mm - rain_mean) / rain_sd
gen shocked = (rain_shock < 0)

* The paper excludes households observed in fewer than two survey waves.
bysort household_id: gen waves = _N
keep if waves < 2

save "output/panel.dta", replace
export delimited "output/panel.csv", replace
