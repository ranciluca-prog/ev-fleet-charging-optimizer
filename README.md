# EV Fleet Charging Optimizer ⚡

**Interactive decision-support prototype for fleet managers.** This Streamlit app uses **Google OR-Tools CP-SAT** to assign planned trips to electric vehicles and schedule pre-departure charging. It can minimize charging cost, minimize estimated electricity-related CO₂e, or optimize under a **maximum-emissions constraint**.

> **Status:** Runnable application source. The project has been statically checked, but solver/UI runtime tests could not be executed in the packaging environment because OR-Tools and Streamlit were unavailable. Install dependencies and run tests before a production or public demonstration. Example data are synthetic.

## What it can do

- Model a fleet of 10 initially identical EVs with different state-of-charge levels (the vehicle list can be edited).
- Edit trip distances, hourly electricity tariffs and grid carbon intensity, battery capacity/reserve, charger count/power, depot power and charging efficiency.
- Jointly allocate trips to vehicles and assign grid energy within hourly charging slots.
- Minimize cost (`cost`) or emissions (`emissions`).
- Specify an **absolute fleet charging-emissions ceiling** in kg CO₂e while minimizing cost or emissions.
- Indicate input validation errors, infeasible schedules, and solver timeouts distinctly.
- View KPI summaries, a charging-by-hour plot, a cost–carbon comparison and trip assignments.
- Export the scenario as JSON, charging/assignments as CSV and full results as JSON.
- Load three scenarios: standard operations, insufficient charging infrastructure, and a trip exceeding battery autonomy.

## Start the app

Python 3.10+ is recommended. From this folder:

```bash
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On macOS / Linux:
# source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Streamlit will show a **local** URL (typically http://localhost:8501). Keep the terminal open while presenting the app.

## Command-line usage

```bash
python ev_optimizer.py example.json --objective cost
python ev_optimizer.py example.json --objective emissions
python ev_optimizer.py example.json --objective cost --max-emissions-kg 20 --output result.json
```

To specify a cap in JSON, add `"max_emissions_kg": 20.0`. Omit it (or set `null`) to disable it.

## Run checks

```bash
python -m unittest -v test_ev_optimizer.py test_emissions_cap.py
```

The cap is modeled directly inside CP-SAT, rather than simply filtering after optimization. It is evaluated from energy drawn from the grid, accounting for charging efficiency. CP-SAT uses integer coefficients at micro-kg resolution; conservative rounding is applied to avoid treating a slightly non-compliant schedule as compliant. Reported emissions are calculated from unrounded battery-added values and rounded only in the final display.

## A transparent example (synthetic)

The bundled `example.json` features 10 vehicles, 10 trips, 3 chargers (11 kW each), a 33 kW site charging limit, 80 kWh batteries, 10 kWh reserves, 90% efficiency and a 14-hour charging horizon. The hourly electricity prices and carbon intensity are **illustrative**, not live forecasts or market quotes. To study trade-offs, run the lowest-cost and lowest-emissions objectives and then apply a cap such as `20 kg CO₂e`. Your locally computed output is the authoritative result; no performance/savings figures are claimed without a confirmed execution.

## Architecture

```
app.py                 Streamlit user interface, scenario editor, reporting
 ev_optimizer.py       CP-SAT solver, validation and CLI
 example.json          Synthetic reference scenario
 test_ev_optimizer.py  Baseline model tests
 test_emissions_cap.py Carbon ceiling regression tests
 requirements.txt      Runtime dependencies
```

## Important limitations

1. All listed slots are assumed to be **one hour** long and occur **before all trips depart**. Each vehicle may perform at most **one trip**. No mid-route charging, midday returns or departure-time assignment.
2. Vehicle batteries and power capabilities are homogeneous; state of charge may differ. Charging occurs in discrete increments of **0.1 kWh stored** and assumes constant charging efficiency. Actual charging may taper close to full capacity.
3. Financial totals include the hourly energy component only, excluding taxes, demand charges, grid charges and battery wear; no PPA modelling.
4. Environmental totals reflect **user-supplied grid carbon-intensity factors** multiplied by grid energy. They are illustrative location-based operational estimates, **not** a verified Scope 2 market-based inventory or marginal-emissions calculation.
5. Charger counts are modeled as concurrent plug-in slots, not as named physical chargers. Sub-hourly plug-in changes, charger switching time and charging session interruptions are not modeled.
6. `OPTIMAL` means optimal within this mathematical formulation. `FEASIBLE` means a valid schedule without a proof of global optimality; `UNKNOWN` is **not** evidence of infeasibility.
7. This is a **decision-support prototype**, not a certified charge-point controller. Verify compatibility and real operational needs before deploying.

## Publishing on GitHub and Streamlit Community Cloud

1. Create a new GitHub repository and upload the files from this folder **to its root** (`app.py`, `requirements.txt`, etc.). Do not upload `.venv`.
2. Test locally using the commands above.
3. On https://share.streamlit.io, sign in with GitHub, select the repository, branch and `app.py` as the main entry point, then deploy.
4. Verify the hosted app by running all three example scenarios and the emissions-cap demo.
5. Add the public Streamlit URL and a screenshot to the repository README. Never put API keys into the repository.

**Roadmap:** individual departure/return windows, multiple trips per EV, measured baseline comparisons, live tariff/carbon feeds, charger-level interoperability and expanded independent validation.

## Portfolio demonstration script (3 minutes)

1. Open the **Standard fleet** example and run **Minimize cost**. Explain the depot, 10 EVs, hourly tariff/carbon factors, assignments and charging chart.
2. Load the **Carbon-constrained fleet** example, keep **Minimize cost** and run again. Explain the 20 kg CO₂e ceiling and compare the extra electricity cost with the unconstrained minimum-cost plan.
3. Load **Impossible trip**, run optimization and explain that an impossible journey is rejected rather than assigned.
4. Download the charging CSV and full JSON report. Mention all price and emissions input data are synthetic.

## Reproducibility and checks

```bash
python -m unittest discover -v
python -m compileall -q .
```

The tests include a tiny independently calculable scenario: 1 kWh charge at €0.20/kWh and 100 gCO₂e/kWh, efficiency 100%. Expected cost: €0.20; expected emissions: 0.1000 kg. A ceiling of 0.1000 kg is feasible and 0.0999 kg is not. **Do not claim the tests passed without executing them in an environment with OR-Tools.**

## Windows / VS Code quickstart

1. Install Python and VS Code. Open the extracted project folder in VS Code (**File → Open Folder**).
2. Open **Terminal → New Terminal** (do not type these commands into a Python notebook or the Python interactive console).
3. Run:

```powershell
py -m pip install -r requirements.txt
py -m unittest discover -v
py -m streamlit run app.py
```

If `py` is not recognized, use `python` instead. If dependencies fail to install, check your selected Python interpreter and use a supported Python version (3.11 or 3.12 is a practical choice).

## Publication checklist

- [ ] Install dependencies and pass all tests locally.
- [ ] Open the UI locally and verify the four prepared scenarios and data editing.
- [ ] Upload only the project files to a public GitHub repository; keep virtual environments and secrets out.
- [ ] Connect the GitHub repo to **Streamlit Community Cloud** and set the entry point to `app.py`.
- [ ] Retest the hosted application and ensure that the cost/carbon cap matches the downloaded JSON.
- [ ] Add the live demo URL, one screenshot and validated example outputs to the README.
- [ ] Record a short demo and include its link in the README.

The portfolio README deliberately does not claim independently measured savings or a running public deployment until verified.
