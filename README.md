# Solar Farm Financial Model

An opinionated project finance model for utility-scale solar farms. The model was seeded from the
provided Excel workbook and translated into Python for repeatable analysis.

## Features

- Deterministic 20-year projection covering energy generation, revenues, operating costs, capex,
  debt, taxes, and cash flows.
- CLI utility for exporting monthly and annual financial statements as CSV files.
- Streamlit dashboard for adjusting key assumptions interactively and visualising the outputs.
- Optional Excel workbook ingestion to hydrate the Python model with project-specific data.

## Getting started

Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Command line workflow

Run the CLI to export CSV outputs. If you have the Excel assumptions workbook, supply its path with
`--excel`.

```bash
python -m solar_farm_financial_model.cli --export-dir outputs
```

### Streamlit dashboard

Launch the interactive dashboard locally:

```bash
streamlit run streamlit_app.py
```

Use the sidebar to upload the Excel workbook (optional) and adjust the global, energy, and revenue
assumptions. The main area surfaces key metrics, charts, and downloadable CSV tables.

### Deploying to Streamlit Cloud

Deploy this repository directly to Streamlit Cloud using the hosted deployer. Replace
`YOUR_GITHUB_USERNAME` with your GitHub handle if you fork the repository.

[![Deploy to Streamlit](https://static.streamlit.io/badges/streamlit_badge.svg)](https://share.streamlit.io/deploy?repository=https://github.com/YOUR_GITHUB_USERNAME/solar_farm&mainScript=streamlit_app.py)

## Project structure

- `solar_farm_financial_model/` – core package containing dataclasses, loaders, model logic, and
  reporting helpers.
- `streamlit_app.py` – Streamlit entry point wired into the Python model.
- `README.md` – documentation for local usage and deployment.
- `requirements.txt` – dependencies for running the CLI or Streamlit app.
