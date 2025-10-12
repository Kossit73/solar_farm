# Solar Farm Financial Model – Improvement Recommendations

This note summarizes the main areas where the deterministic engine and the Streamlit tooling can be strengthened to increase analytical robustness, traceability, and IFRS alignment.

## 1. Strengthen automated regression coverage
- **Why:** The core simulator orchestrates multiple dependent schedules – generation, revenue, operating costs, capex, working capital, taxes, debt, and terminal value – before aggregating them into IFRS-style statements.【F:solar_farm_financial_model/model.py†L115-L183】【F:solar_farm_financial_model/model.py†L480-L499】 Without automated tests, small refactors in any sub-schedule can silently break cash flows or statement roll-ups.
- **Recommendation:** Introduce a `tests/` suite (e.g., with `pytest`) that feeds curated assumption fixtures through `SolarFarmFinancialModel.run()` and asserts:
  - Income statement subtotals (revenue, EBITDA, EBIT) reconcile to the monthly drivers.
  - Cash flow totals tie back to the balance sheet movements and working-capital deltas.
  - Key metrics (NPV, IRR, payback) remain stable for the canonical workbook.  This provides a regression net before changing depreciation logic or adding new assumptions.

## 2. Guard against duplicate operating-expense labels
- **Observation:** Operating expense columns are keyed by a lower-cased label (`opex_fixed_<slug>` / `opex_variable_<slug>`).【F:solar_farm_financial_model/model.py†L251-L277】 If two inputs share the same label (e.g., two “Maintenance” rows), later iterations overwrite earlier data, leading to understated costs.
- **Recommendation:** Normalise column names with a deterministic unique suffix (e.g., append an index) or store results in a MultiIndex keyed by both label and UUID. Also surface validation in the Streamlit input table to flag duplicate names before the model runs.

## 3. Expand terminal-value flexibility
- **Observation:** The exit cash flow is currently calculated with a single trailing EBITDA multiple minus capital-gains tax and outstanding debt.【F:solar_farm_financial_model/model.py†L451-L459】 Real projects often require:
  - Alternative valuation methods (DCF of a terminal growth perpetuity, book-value-based exits).
  - Explicit salvage / decommissioning costs and working-capital releases at exit.
- **Recommendation:** Extend the global assumptions schema to let users pick the terminal methodology, specify salvage costs, and opt-in to releasing working capital. This will make the exit treatment more transparent and adaptable to different mandates.

## 4. Enhance working-capital modelling fidelity
- **Observation:** Working-capital balances scale linearly with total opex, even for receivables where revenue is the more appropriate driver.【F:solar_farm_financial_model/model.py†L327-L389】 Inventory and payables also assume a single blended opex base.
- **Recommendation:** Allow the assumption tables to map each working-capital component to a driver (revenue, variable opex, fixed opex, or energy). This improves accuracy for hybrid business models (e.g., when inventory is tied to merchant sales) and keeps the IFRS balance sheet closer to operational reality.

## 5. Improve dependency handling ergonomics
- **Observation:** Optional imports are guarded in the loaders, but the CLI still surfaces environment-specific guidance when numpy/pandas are missing.【F:solar_farm_financial_model/data_loader.py†L9-L37】【F:solar_farm_financial_model/cli.py†L1-L120】 Users deploying on Streamlit Cloud or Airflow benefit from clearer documentation.
- **Recommendation:** Ship a `pyproject.toml` or extras section that defines core vs. optional dependencies, and document minimal packages required for headless execution. Pair this with a lightweight smoke test in CI that exercises both the CLI and the Streamlit app in dependency-constrained environments.

Implementing the above will make the model easier to extend, safer to refactor, and more resilient when different stakeholders contribute custom assumptions.
