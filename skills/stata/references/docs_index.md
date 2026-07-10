# Stata 18 Documentation Index

All PDFs are in `/Applications/Stata/docs/`. Use this index to identify which manual to consult for a given topic.

## Quick Lookup by Topic

| PDF | Title | Pages | Size | Key Topics |
|-----|-------|------:|-----:|------------|
| `u.pdf` | User's Guide | 402 | 3.4M | Getting started, basic usage, data types, do-files, syntax, estimation, post-estimation |
| `r.pdf` | Base Reference | 3394 | 29M | All base commands: `regress`, `logit`, `probit`, `summarize`, `tabulate`, `correlate`, `test`, `predict`, etc. |
| `d.pdf` | Data Management | 984 | 5.6M | `import`, `export`, `merge`, `append`, `reshape`, `encode`, `decode`, `destring`, `tostring`, `rename`, `recode`, `sort`, `duplicates`, `frames` |
| `g.pdf` | Graphics | 768 | 17M | `graph twoway`, `scatter`, `line`, `bar`, `histogram`, `box`, `pie`, `scheme`, graph options |
| `p.pdf` | Programming | 665 | 3.8M | `program`, `macro`, `scalar`, `matrix`, `return`, `ereturn`, `class`, `ado-files`, Stata programming |
| `fn.pdf` | Functions | 193 | 2.5M | Built-in functions: string, math, date, statistical, random-number, matrix functions |
| `m.pdf` | Mata Reference | 1180 | 4.8M | Mata programming language: matrix operations, optimization, numerical methods |
| `ts.pdf` | Time Series | 1026 | 7.4M | `arima`, `arch`, `var`, `vec`, `irf`, `dfgls`, `dfuller`, `pperron`, time-series operators |
| `xt.pdf` | Longitudinal/Panel Data | 697 | 11M | `xtreg`, `xtlogit`, `xtprobit`, `xtpoisson`, `xtmixed`, `xtabond`, panel-data models |
| `st.pdf` | Survival Analysis | 642 | 7.1M | `stset`, `stcox`, `streg`, `sts`, `stcurve`, Kaplan-Meier, Cox regression |
| `me.pdf` | Multilevel Mixed-Effects | 572 | 8.8M | `mixed`, `melogit`, `mepoisson`, `menl`, multilevel/hierarchical models |
| `mv.pdf` | Multivariate Statistics | 750 | 6.9M | `manova`, `factor`, `pca`, `cluster`, `discriminant`, `canon`, multivariate methods |
| `causal.pdf` | Causal Inference & Treatment Effects | 560 | 4.9M | `teffects`, `eteffects`, `stteffects`, DID, IPW, regression adjustment, matching |
| `bayes.pdf` | Bayesian Analysis | 897 | 18M | `bayesmh`, `bayes:`, Bayesian estimation, MCMC, priors, model comparison |
| `sem.pdf` | Structural Equation Modeling | 670 | 5.0M | `sem`, `gsem`, path diagrams, CFA, mediation, latent variables |
| `mi.pdf` | Multiple Imputation | 399 | 3.3M | `mi impute`, `mi estimate`, handling missing data |
| `meta.pdf` | Meta-Analysis | 439 | 4.0M | `meta set`, `meta summarize`, `meta forestplot`, `meta funnelplot` |
| `lasso.pdf` | Lasso | 394 | 3.3M | `lasso`, `elasticnet`, `sqrtlasso`, `ds`, `po`, machine learning variable selection |
| `svy.pdf` | Survey Data | 227 | 2.4M | `svyset`, `svy:`, survey estimation, stratification, clustering, weights |
| `tables.pdf` | Customizable Tables & Collected Results | 329 | 4.0M | `table`, `collect`, `etable`, `dtable`, customizable output tables |
| `pss.pdf` | Power, Precision & Sample Size | 795 | 5.4M | `power`, `ciwidth`, sample-size calculations, power analysis |
| `cm.pdf` | Choice Models | 329 | 3.0M | `cmclogit`, `cmmixlogit`, `cmroprobit`, discrete choice models |
| `erm.pdf` | Extended Regression Models | 307 | 3.2M | `eregress`, `eprobit`, `eologit`, endogeneity, sample selection, treatment |
| `irt.pdf` | Item Response Theory | 251 | 4.1M | `irt 1pl`, `irt 2pl`, `irt grm`, psychometric models |
| `adapt.pdf` | Adaptive Designs: Group Sequential Trials | 252 | 3.7M | `gsd`, group sequential designs, clinical trial monitoring |
| `bma.pdf` | Bayesian Model Averaging | 241 | 2.9M | `bma`, model uncertainty, variable selection via BMA |
| `sp.pdf` | Spatial Autoregressive Models | 231 | 4.7M | `spregress`, `spxtregress`, spatial econometrics |
| `dsge.pdf` | Dynamic Stochastic General Equilibrium | 179 | 2.7M | `dsge`, `dsgenl`, macroeconomic modeling |
| `fmm.pdf` | Finite Mixture Models | 141 | 2.0M | `fmm:`, latent class models, mixture distributions |
| `h2oml.pdf` | Machine Learning (H2O Ensemble Trees) | 360 | 4.8M | `h2oml`, random forests, gradient boosting, decision trees |
| `rpt.pdf` | Reporting | 221 | 6.3M | `putdocx`, `putpdf`, `putexcel`, dynamic documents, automated reports |
| `gsm.pdf` | Getting Started for Mac | 157 | 13M | Mac-specific intro, GUI walkthrough |
| `gsu.pdf` | Getting Started for Unix | 162 | 8.5M | Unix-specific intro |
| `gsw.pdf` | Getting Started for Windows | 158 | 5.8M | Windows-specific intro |
| `ig.pdf` | Installation Guide | 21 | 1.8M | Installation, licensing, platforms |
| `i.pdf` | Combined Index | 321 | 5.5M | Master index across all manuals |
| `stoc.pdf` | Combined Subject Table of Contents | 59 | 1.7M | Combined TOC for all manuals — good for topic discovery |

## Recommended Search Order by Task

**Running regressions / estimation**: `r.pdf` → `u.pdf`
**Data wrangling**: `d.pdf` → `r.pdf` → `u.pdf`
**Graphics/plotting**: `g.pdf`
**Panel data**: `xt.pdf` → `r.pdf`
**Time series**: `ts.pdf`
**Survival analysis**: `st.pdf`
**Programming (ado/do)**: `p.pdf` → `u.pdf`
**Mata programming**: `m.pdf`
**Missing data**: `mi.pdf`
**Survey data**: `svy.pdf`
**Causal inference**: `causal.pdf`
**Bayesian methods**: `bayes.pdf` → `bma.pdf`
**Machine learning**: `lasso.pdf` → `h2oml.pdf`
**Tables/reporting**: `tables.pdf` → `rpt.pdf`
**Finding any command**: `i.pdf` (index) → `stoc.pdf` (subject TOC)
