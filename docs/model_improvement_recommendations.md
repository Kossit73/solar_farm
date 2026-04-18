# Investor Attractiveness Review – Solar Farm Financial Model

## Executive view
Using the repository default assumptions (10 MW plant, 20-year horizon, 10% discount rate), the current model produces a **negative project NPV (~-$11.0M)** and **non-meaningful equity/investor IRRs (`NaN`)**. This is a red flag for institutional investors and also indicates that the equity cash flow construction needs to be improved before using IRR as a decision KPI.

## What is limiting investor appeal today

1. **Equity cash flow is missing an explicit equity contribution draw profile**
   - The model sets `equity_cash_flow = debt_free_cash_flow` directly, but does not model an initial equity injection line.
   - Result: investor/equity IRR can become mathematically undefined (`NaN`) because the series may not include a proper negative equity outflow period.

2. **No lender-grade credit metrics are reported (DSCR, LLCR, PLCR)**
   - Investors typically screen utility-scale projects first on debt service coverage and debt tail quality, then on IRR.
   - The model has debt interest/principal schedules, so those ratios can be computed, but they are not yet surfaced.

3. **Tax-equity and incentive layer is absent**
   - There is tax logic for income/capital gains, but no explicit modeling of U.S. solar incentives (e.g., ITC/PTC pathways), transferability, or bonus depreciation impacts on after-tax equity returns.

4. **Terminal growth input is present but not used in valuation logic**
   - `terminal_growth_rate` exists in assumptions and UI, but terminal value uses only exit multiple logic.
   - This can confuse investment committees and makes valuation methodology look incomplete.

5. **Contracting and merchant risk are simplified**
   - Revenue is modeled from static shares/rates with annual escalation, but without PPA tenor roll-off, shape risk, curtailment risk, merchant price distributions, or basis risk.

## Recommendations to improve investability

## Priority 1 (must-have for IC readiness)

### A) Build a true equity funding schedule
- Add explicit equity draw line during construction (`equity_contribution`) so total sources = uses each month.
- Redefine:
  - `equity_cash_flow_to_investor = -equity_contribution + distributions`
- Outcome: investor IRR and MOIC become economically meaningful.

### B) Add covenant-grade debt metrics
- Calculate and report monthly + annual:
  - DSCR = CFADS / Debt Service
  - LLCR = NPV(CFADS over loan life) / debt balance
  - Debt yield = EBITDA / debt balance
- Add downside case covenant headroom (P50/P90 production and merchant downside).

### C) Add explicit incentives module
- Add scenario toggles for ITC/PTC treatment and depreciation/tax shield impacts.
- Show before/after impact on NPV, equity IRR, and payback.

## Priority 2 (value uplift levers)

### D) Expand bankability of revenue stack
- Model PPA tenor and step-down to merchant pricing after contract expiry.
- Add curtailment + availability assumptions and optional floor/hedge structure.

### E) Separate O&M into fixed, indexed, and lifecycle replacements
- Keep current fixed/variable buckets, but add major maintenance reserve and inverter replacement cycle.

### F) Add exit-method choice
- Keep EBITDA multiple method, and add Gordon-growth option using `terminal_growth_rate`.
- Let users compare valuation methods side-by-side.

## Quick sensitivity insights from current defaults

Directional tests against defaults show that the largest value lever is **capital structure + capex + contracted price quality together**. A combined scenario (10% capex reduction, 70% debt at 6%, stronger PPA mix/price, and 15% opex reduction) improves project NPV materially versus base case, but still remains negative, indicating that additional structural changes are needed (especially incentives and realistic equity structuring).

## Practical next implementation sprint
1. **Financial plumbing**: equity contribution schedule + DSCR/LLCR outputs.
2. **Tax/incentives**: ITC/PTC and depreciation options.
3. **Revenue risk**: PPA tenor roll-off + merchant downside cases.
4. **Decision dashboard**: investment committee page with NPV/IRR/MOIC/DSCR covenant summary in base/upside/downside.

These four deliverables will materially improve investor confidence because they address the exact diligence questions asked by infrastructure equity, tax equity, and project finance lenders.
