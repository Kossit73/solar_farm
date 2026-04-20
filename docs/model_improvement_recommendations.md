# Senior Financial Review – Solar Farm Model (Current State)

## Executive assessment
The model has improved materially and now includes stronger lender-style outputs (`CFADS`, `DSCR`, `capex_per_mw`, `opex_per_mwh`, and an LCOE proxy). It is now useful for first-pass project-finance screening. However, it still needs several structural upgrades to be fully investment-committee grade for utility-scale solar.

## What is now working well

1. **Debt service analytics are embedded**
   - Monthly `debt_service`, `cfads`, and `dscr` are calculated in-core, and annual DSCR is surfaced in annual summary outputs.

2. **Core efficiency and cost diagnostics exist**
   - `capex_per_mw`, `opex_per_mwh`, and `lcoe_proxy_per_mwh` are now reported, which improves benchmarkability and technical-economic review.

3. **Revenue-share validation added**
   - The model now blocks invalid over-allocation of PPA + merchant shares above 100%.

## Key gaps to prioritize (high impact)

### 1) Add explicit equity funding schedule and waterfall
Current equity cash flow still behaves as a residual debt-free cash-flow proxy. Add:
- construction-period equity draws,
- operating-period distributions,
- preferred return/hurdle logic (if applicable),
- investor/owner waterfall (including catch-up tiers if needed).

**Why this matters:** IRR and equity multiple become economically valid and auditable.

### 2) Upgrade debt module to full project-finance covenant quality
Add:
- LLCR/PLCR,
- DSRA mechanics,
- sculpted amortization against CFADS,
- covenant default triggers and cure assumptions.

**Why this matters:** lenders and ICs evaluate downside resilience through these metrics, not DSCR alone.

### 3) Replace simplified tax treatment with jurisdiction-grade tax stack
Add:
- ITC/PTC pathways,
- MACRS/bonus depreciation,
- tax-equity transferability/partnership allocations (if relevant),
- NOL handling and carryforward logic.

**Why this matters:** post-tax equity returns can change materially and often determine deal viability.

### 4) Improve merchant and contract realism
Add:
- PPA tenor roll-off,
- merchant curve by year (not only constant escalation),
- optional curtailment and availability assumptions,
- degradation-performance warranty interactions.

**Why this matters:** valuation and debt sizing are highly sensitive to post-PPA cash-flow quality.

### 5) Strengthen terminal valuation architecture
Add selectable methods:
- exit multiple,
- Gordon-growth using terminal growth,
- salvage/decommissioning netting,
- explicit working-capital release at exit.

**Why this matters:** terminal value often drives long-horizon project NPV and must be method-transparent.

### 6) Improve CAPEX realism and lifecycle modeling
Add:
- construction schedule by package and contingency draw rules,
- owner’s costs, IDC and financing fees,
- lifecycle replacement CAPEX (especially inverters),
- degradation-linked augmentation where relevant.

**Why this matters:** under-modeled lifecycle CAPEX overstates long-term equity value.

### 7) Introduce probabilistic downside diagnostics for IC discussion
Keep deterministic base case, but add:
- P50/P90 generation cases,
- downside merchant-price cases,
- debt covenant breach probability snapshots.

**Why this matters:** decision-makers need distributional risk insight, not only base/upside/downside points.

### 8) Add full traceability outputs for auditability
Produce dedicated schedule tabs/dataframes for:
- Sources & Uses,
- Debt covenant table,
- Tax bridge,
- Return bridge (NPV/IRR drivers),
- Reconciliation checks.

**Why this matters:** traceability is critical for credit committee and investor diligence confidence.

## Recommended implementation sequence (practical)
1. **Equity funding + waterfall + sources/uses reconciliation**
2. **Debt covenant stack (LLCR/PLCR/DSRA/sculpting)**
3. **Tax and incentives module**
4. **Contract/merchant curve realism + curtailment**
5. **Terminal valuation methods + decommissioning and WC release**
6. **Probabilistic risk pack (P50/P90 + covenant risk)**

If executed in this order, the model can move from “good screening tool” to “investment-committee and lender-ready underwriting model.”

## Additional bankability recommendations (senior lender perspective)

To move from technically improved to truly financeable in debt markets, add the following lender controls and deliverables:

1. **Base/Downside covenant case pack**
   - Mandatory base case + lender downside case with explicit DSCR lock-up, default, and cure paths.
   - Include minimum DSCR by year, average DSCR, and debt tail profile in each case.

2. **Debt term-sheet switchboard**
   - Parameterize common debt terms: margin grids, commitment/arrangement fees, amortization type, DSRA rules, prepayment assumptions, and cash sweep triggers.
   - Allow side-by-side debt structure comparison for bank club vs. institutional debt.

3. **Construction-to-operation transition controls**
   - Add COD tests, liquidated damages assumptions, delay scenarios, and EPC warranty logic.
   - Include contingency draw waterfall and residual contingency release rules.

4. **Operating reserve framework**
   - Distinguish DSRA, major maintenance reserve, and inverter reserve.
   - Track reserve funding and release logic with auditable cash-account rollforwards.

5. **Independent engineer alignment outputs**
   - Add P50/P75/P90 generation and availability assumptions with clear mapping to energy model inputs.
   - Provide a reconciliation table from technical assumptions to financial energy outcomes.

6. **Merchant risk and hedge module**
   - Add hedge/floor structures, basis risk assumptions, and shaping losses.
   - Include post-PPA merchant tail valuation under conservative and stressed curves.

7. **Counterparty and legal risk overlay**
   - PPA off-taker quality scoring, curtailment compensation rules, termination provisions, and change-in-law sensitivity.
   - Flag where legal protections are assumed but not modeled economically.

8. **IC-ready outputs and audit package**
   - One-click package with: assumptions memo, covenant dashboard, downside bridge, return attribution bridge, and reconciliation checks.
   - Ensure all key outputs are traceable back to assumptions and intermediate schedules.

These additions are typically what convert a strong internal model into a lender- and credit-committee-acceptable underwriting model.

## 8-point implementation verification checklist (current build)

1. **Equity funding + waterfall** – Implemented in core cash-flow plumbing (`equity_contribution`, reserve-adjusted distributions, and resulting `equity_cash_flow`).  
2. **Covenant-grade debt stack** – Implemented at proxy level (`CFADS`, `DSCR`, DSRA requirement/change, LLCR/PLCR proxies, covenant breach count).  
3. **Tax/incentive treatment** – Implemented baseline modules (optional bonus depreciation and ITC realization timing).  
4. **Contract/merchant realism** – Implemented baseline controls (curtailment, PPA-term roll-off, merchant floor price, counterparty haircut).  
5. **Terminal valuation architecture** – Implemented selectable terminal method (`multiple` / `gordon`).  
6. **Lifecycle CAPEX realism** – Implemented optional replacement-year/fraction lifecycle CAPEX schedule.  
7. **Probabilistic downside diagnostics** – Implemented downside NPV distribution with P10/P50/P90 plus P50/P75/P90 energy diagnostics.  
8. **Traceability/reconciliation schedules** – Implemented monthly/annual sources-uses and reserve/fee schedules with reconciliation gap output.

> Note: Items above are implemented to materially improve bankability, but some components are intentionally proxy-level (especially covenant architecture and tax depth) and should be hardened further for full lender model compliance.
