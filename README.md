# EV Fleet Charging Optimizer ⚡

**Interactive decision-support prototype for fleet managers (v3).** This Streamlit app uses **Google OR-Tools CP-SAT** to assign planned trips to electric vehicles and schedule pre-departure charging. It can minimize charging cost, minimize estimated electricity-related CO₂e, or optimize under a **maximum-emissions constraint**.

> **Status:** Five new independent analysis tests passed and Python syntax/UI-helper smoke checks passed in the packaging environment. Full OR-Tools and Streamlit integration tests could not run here because the dependencies were unavailable. Run `python -m unittest discover -v` and open Streamlit locally before sharing. All example data are synthetic.

## What it can do

- Model a fleet of 10 initially identical EVs with editable **SoC (%)** and a third, read-only **available battery energy (kWh)** column calculated automatically from battery capacity.
- Edit trip distances, hourly electricity tariffs and grid carbon intensity, battery capacity/reserve, charger count/power, depot power and charging efficiency.
- Jointly allocate trips to vehicles and assign grid energy within hourly charging slots.
- Minimize cost (`cost`) or emissions (`emissions`).
- Specify an **absolute fleet charging-emissions ceiling** in kg CO₂e while minimizing cost or emissions.
- Indicate input validation errors, infeasible schedules, and solver timeouts distinctly.
- View a trip × vehicle matrix of additional battery energy needed for every possible pairing (including the required arrival reserve).
- Compare the chosen plan against an **18:00, first-EV-first, uninterrupted charging** reference with separate cost, emissions, grid electricity and labelled charging chart.
- View EV IDs **inside colored hourly charging blocks**, in white.
- Compare the two optimized endpoints with automatically generated extra **cost-minimizing CO₂-ceiling scenarios**, in 4 kg increments.
- View KPI summaries, charging-by-hour plots, the full cost–carbon comparison and trip assignments.
- Export the scenario as JSON, charging/assignments as CSV and full results as JSON.
- Load four scenarios: standard operations, a fleet with a CO₂ ceiling, insufficient charging infrastructure, and a trip exceeding battery autonomy.

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
python -m unittest discover -v
```

The new `test_demo_analysis.py` tests the energy matrix, the +4 kg ceiling sequence, the 18:00 first-EV-first schedule, charger/site limits and clearly reported incomplete/unavailable reference scenarios. Its tests can also run independently of OR-Tools.

The cap is modeled directly inside CP-SAT, rather than simply filtering after optimization. It is evaluated from energy drawn from the grid, accounting for charging efficiency. CP-SAT uses integer coefficients at micro-kg resolution; conservative rounding is applied to avoid treating a slightly non-compliant schedule as compliant. Reported emissions are calculated from unrounded battery-added values and rounded only in the final display.

## A transparent example (synthetic)

The bundled `example.json` features 10 vehicles, 10 trips, 3 chargers (11 kW each), a 33 kW site charging limit, 80 kWh batteries, 10 kWh reserves, 90% efficiency and a 14-hour charging horizon. The hourly electricity prices and carbon intensity are **illustrative**, not live forecasts or market quotes. To study trade-offs, run the lowest-cost and lowest-emissions objectives and then apply a cap such as `20 kg CO₂e`. Your locally computed output is the authoritative result; no performance/savings figures are claimed without a confirmed execution.

## How the new comparisons are defined

**SoC conversion.** Each vehicle's editable input is **initial SoC (%)**. The displayed battery energy is `battery_kwh × SoC / 100`. The underlying optimizer continues to accept `soc_kwh` in the exported JSON schema. The interface converts automatically, so previously saved JSON scenarios still work.

**Trip–vehicle matrix.** Rows are trips, columns are EV IDs. A cell is the extra **stored battery energy** (kWh) needed to complete that trip with the configured reserve. A zero means no additional charging is necessary. An empty cell means that the trip plus reserve would exceed even a full battery. Values follow the solver's 0.1 kWh discretization.

**18:00 baseline.** For a fair timing comparison, it uses the **same assignment** as the selected feasible optimized plan (or a feasible uncapped benchmark if selection is infeasible). The available chargers begin at 18:00 with EVs in fleet-list order, charge continuously while vehicles need energy, and move to subsequent EVs as capacity becomes available. Each EV receives only the minimum energy to cover its assigned trip plus reserve, rather than necessarily reaching 100% SoC. The charger count, rated charger power, depot capacity, time horizon and efficiency are respected. The baseline does **not** enforce the CO₂ ceiling. If it cannot finish, the dashboard marks its totals as **partial**, not as a valid completed comparison. The 18:00 baseline requires a chronological hourly series that contains an 18:00 slot.

**CO₂-ceiling scenarios.** Compute the minimum-emissions and minimum-cost benchmarks without an emissions ceiling; then round **up** the minimum-emissions result to the nearest whole kg and add **4 kg** repeatedly, keeping only values **strictly below** the minimum-cost benchmark's emissions. Run cost-minimization with each cap. For example: if the endpoints are 13.705 and 27.629 kg CO₂e, the caps are **18, 22, 26 kg** (14 + 4, +4, +4). Each plotted point reports its achieved emissions, which need not equal the cap. A previously provided example listing 16 or 24 as subsequent values is inconsistent with the specified +4 increment; this implementation follows the +4 rule.

**Scope.** The chart comparisons are estimates from illustrative energy/carbon time series, not measured real-world savings.

## Architecture

```
app.py                 Streamlit UI, scenario editor, reporting
demo_analysis.py       Trip/EV matrix, immediate-18:00 reference, ceiling sequence
ev_optimizer.py        CP-SAT optimizer, validation and CLI
example.json           Synthetic reference scenario
example_capped.json    Alternate capped scenario
test_demo_analysis.py  Independent tests for v3 analytics
test_ev_optimizer.py   Original solver tests
test_emissions_cap.py  Carbon ceiling regression tests
requirements.txt       Runtime dependencies
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
4. Verify the hosted app by running all four prepared example scenarios, the 18:00 reference and the emissions-cap trade-off.
5. Add the public Streamlit URL and a screenshot to the repository README. Never put API keys into the repository.

**Roadmap:** individual departure/return windows, multiple trips per EV, measured baseline comparisons, live tariff/carbon feeds, charger-level interoperability and expanded independent validation.

## Portfolio demonstration script (3 minutes)

1. Open **Standard fleet**, edit one SoC %, and show the instantly derived available kWh. Run **Minimize cost** and demonstrate the trip–vehicle matrix and 18:00 reference chart.
2. Load **Carbon-constrained fleet**, keep **Minimize cost** and run again. Explain the 20 kg CO₂e ceiling and the +4 kg intermediate ceilings on the cost–carbon scatterplot.
3. Load **Impossible trip**, run optimization and explain that an impossible journey is rejected rather than assigned.
4. Point out the white vehicle labels inside charging blocks. Download the 18:00 reference schedule, optimized charging CSV and full JSON report. Mention that prices and carbon factors are synthetic.

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
