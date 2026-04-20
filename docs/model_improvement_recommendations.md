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
