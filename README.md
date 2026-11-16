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



## Command-line usage

```bash
python ev_optimizer.py example.json --objective cost
python ev_optimizer.py example.json --objective emissions
python ev_optimizer.py example.json --objective cost --max-emissions-kg 20 --output result.json
```



## Run checks

```bash
python -m unittest -v test_ev_optimizer.py test_emissions_cap.py
```

The cap is modeled directly inside CP-SAT, rather than simply filtering after optimization. It is evaluated from energy drawn from the grid, accounting for charging efficiency. CP-SAT uses integer coefficients at micro-kg resolution; conservative rounding is applied to avoid treating a slightly non-compliant schedule as compliant. Reported emissions are calculated from unrounded battery-added values and rounded only in the final display.

## A transparent example (synthetic)

The bundled `example.json` features 10 vehicles, 10 trips, 3 chargers (11 kW each), a 33 kW site charging limit, 80 kWh batteries, 10 kWh reserves, 90% efficiency and a 14-hour charging horizon. The hourly electricity prices and carbon intensity are **illustrative**, not live forecasts or market quotes. To study trade-offs, run the lowest-cost and lowest-emissions objectives and then apply a cap such as `20 kg CO₂e`. 

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



