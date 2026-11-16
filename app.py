"""EV Fleet Charging Optimizer | interactive portfolio demo.

Run with: streamlit run app.py
All example prices and carbon data are illustrative, not live feeds.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from demo_analysis import (
    carbon_ceiling_candidates,
    immediate_18h_baseline,
    trip_vehicle_extra_energy,
)
from ev_optimizer import solve, validate

BASE = Path(__file__).parent
VALID = ('OPTIMAL', 'FEASIBLE')

st.set_page_config(page_title='EV Fleet | Charging Optimizer', page_icon='⚡', layout='wide')
st.markdown('''<style>
.block-container {max-width: 1320px; padding-top: 2rem;}
[data-testid="stMetric"] {background: rgba(125,125,125,.07); border-radius: 12px; padding: 14px;}
.small-note {font-size: .88rem; opacity: .74;}
</style>''', unsafe_allow_html=True)


def example(kind: str) -> dict:
    data = json.loads((BASE / 'example.json').read_text(encoding='utf-8'))
    if kind == 'Carbon-constrained fleet':
        data['max_emissions_kg'] = 20.0
    elif kind == 'Low charging capacity':
        data['chargers'] = 1
        data['site_power_kw'] = 3.0
        for v in data['vehicles']:
            v['soc_kwh'] = 3
    elif kind == 'Impossible trip':
        data['trips'][0]['distance_km'] = 500
    return data


def to_csv(table: list[dict]) -> bytes:
    return pd.DataFrame(table).to_csv(index=False).encode('utf-8')


def status_text(name: str) -> str:
    return {'OPTIMAL': 'Proven optimum', 'FEASIBLE': 'Feasible (optimality not proven)',
            'INFEASIBLE': 'No feasible schedule', 'INVALID': 'Invalid inputs',
            'UNKNOWN': 'Solver time limit / unknown', 'MODEL_INVALID': 'Solver model invalid'}.get(name, name)


def schedule_plot(charging: list[dict], slot_order: list[str], title: str):
    """Each colored segment displays its vehicle ID in white."""
    df = pd.DataFrame(charging)
    fig = px.bar(df, x='slot', y='grid_energy_kwh', color='vehicle', text='vehicle',
                 title=title,
                 labels={'slot': 'Charging hour', 'grid_energy_kwh': 'Grid electricity (kWh)', 'vehicle': 'EV'})
    fig.update_traces(textposition='inside', insidetextfont=dict(color='white', size=12),
                      textfont=dict(color='white', size=12))
    fig.update_layout(barmode='stack', xaxis_tickangle=-35, legend_title_text='Vehicle',
                      height=480, uniformtext_minsize=9, uniformtext_mode='show')
    fig.update_xaxes(categoryorder='array', categoryarray=slot_order)
    return fig


def vehicle_table_for_editor(source: dict, battery_capacity: float, key: str) -> pd.DataFrame:
    """Show SoC in percent and recalculate the third (read-only) energy column."""
    starting_capacity = float(source['battery_kwh'])
    df = pd.DataFrame([
        {'id': item['id'], 'soc_pct': round(100 * float(item['soc_kwh']) / starting_capacity, 2)}
        for item in source['vehicles']
    ])
    # st.data_editor edits live in widget state. Apply them BEFORE generating the
    # read-only column, so that it updates when the user edits a SoC cell.
    widget_state = st.session_state.get(key, {})
    if isinstance(widget_state, dict):
        for row_index, edits in widget_state.get('edited_rows', {}).items():
            index = int(row_index)
            if 0 <= index < len(df):
                for field in ('id', 'soc_pct'):
                    if field in edits:
                        df.at[index, field] = edits[field]
    df['available_kwh'] = (pd.to_numeric(df['soc_pct'], errors='coerce') * battery_capacity / 100).round(2)
    return df


if 'scenario' not in st.session_state:
    st.session_state.scenario = example('Standard fleet')
if 'results' not in st.session_state:
    st.session_state.results = None
if 'scenario_version' not in st.session_state:
    st.session_state.scenario_version = 0

st.title('⚡ EV Fleet Charging Optimizer')
st.caption('Fleet operations · mathematical optimization · cost and carbon decision support')
st.info('**Demo scope:** one depot, identical EV specifications, one trip per vehicle, and hourly charging before departure. All example data are synthetic.', icon='ℹ️')

with st.sidebar:
    st.header('Scenario')
    choice = st.selectbox('Load a prepared example', ['Standard fleet', 'Carbon-constrained fleet', 'Low charging capacity', 'Impossible trip'])
    if st.button('Load example', use_container_width=True):
        st.session_state.scenario = example(choice)
        st.session_state.scenario_version += 1
        st.session_state.results = None
        st.rerun()
    file = st.file_uploader('Or import a JSON scenario', type=['json'])
    if st.button('Import uploaded scenario', disabled=file is None, use_container_width=True):
        try:
            parsed = json.loads(file.getvalue())
            if not isinstance(parsed, dict):
                raise ValueError('JSON must contain an object')
            required = ['battery_kwh', 'reserve_kwh', 'chargers', 'charger_power_kw', 'site_power_kw',
                        'efficiency', 'consumption_kwh_km', 'vehicles', 'trips', 'slots',
                        'prices_eur_kwh', 'carbon_g_kwh']
            absent = [key for key in required if key not in parsed]
            if absent:
                raise ValueError('Missing scenario fields: ' + ', '.join(absent))
            st.session_state.scenario = parsed
            st.session_state.scenario_version += 1
            st.session_state.results = None
            st.rerun()
        except (ValueError, UnicodeDecodeError) as exc:
            st.error(f'Invalid JSON: {exc}')
    st.divider()
    st.write('**Optimization mode**')
    objective = st.radio('Primary goal', ['Minimize cost', 'Minimize emissions'], index=0)
    use_cap = st.toggle('Enforce CO₂ ceiling', value=st.session_state.scenario.get('max_emissions_kg') is not None)
    cap = st.number_input('Maximum CO₂ (kg)', min_value=0.0, value=float(st.session_state.scenario.get('max_emissions_kg') or 20.0), step=0.5, disabled=not use_cap)
    seconds = st.slider('Max solver time per plan (seconds)', 3, 30, 12)
    st.divider()
    st.info('All tariff and carbon-intensity values are illustrative. No grid API or charger hardware is connected.')

source = copy.deepcopy(st.session_state.scenario)

st.subheader('1 · Fleet, infrastructure & operations')
with st.expander('Infrastructure and assumptions', expanded=True):
    a,b,c,d = st.columns(4)
    battery = a.number_input('Battery capacity (kWh / vehicle)', min_value=1.0, value=float(source['battery_kwh']), step=5.0)
    reserve = b.number_input('Minimum arrival reserve (kWh)', min_value=0.0, value=float(source['reserve_kwh']), step=1.0)
    chargers = c.number_input('Number of chargers', min_value=1, max_value=200, value=int(source['chargers']), step=1)
    power = d.number_input('Charger power (kW)', min_value=0.1, value=float(source['charger_power_kw']), step=1.0)
    a,b,c = st.columns(3)
    site = a.number_input('Depot charging power limit (kW)', min_value=0.1, value=float(source['site_power_kw']), step=1.0)
    eff = b.number_input('Charging efficiency (%)', min_value=1.0, max_value=100.0, value=float(source['efficiency']) * 100, step=1.0)
    consumption = c.number_input('Consumption (kWh / km)', min_value=0.01, value=float(source['consumption_kwh_km']), step=0.01)

left,right = st.columns(2)
with left:
    st.markdown('**Vehicles · initial state of charge**')
    vehicle_editor_key = f'vehicle_editor_v3_{st.session_state.scenario_version}'
    vehicle_input = vehicle_table_for_editor(source, battery, vehicle_editor_key)
    vehicles_df = st.data_editor(
        vehicle_input, hide_index=True, num_rows='dynamic', use_container_width=True,
        column_order=['id', 'soc_pct', 'available_kwh'],
        disabled=['available_kwh'],
        column_config={
            'id': st.column_config.TextColumn('Vehicle'),
            'soc_pct': st.column_config.NumberColumn('SoC (%)', min_value=0.0, max_value=100.0, format='%.1f'),
            'available_kwh': st.column_config.NumberColumn('Available energy (kWh)', format='%.2f'),
        }, key=vehicle_editor_key)
    st.caption('Available energy = battery capacity × SoC / 100. Change the SoC; the kWh column is calculated automatically.')
with right:
    st.markdown('**Trips · required distance**')
    trips_df = st.data_editor(pd.DataFrame(source['trips']), hide_index=True, num_rows='dynamic', use_container_width=True,
                              column_config={'distance_km': st.column_config.NumberColumn('distance_km', min_value=0, format='%.1f')}, key=f'trip_editor_{st.session_state.scenario_version}')

st.subheader('2 · Hourly electricity assumptions')
st.caption('Each slot represents one hour, and all trips depart after the final slot. Prices and grid carbon intensities are editable.')
slots_df = pd.DataFrame({'slot': source['slots'], 'price_eur_kwh': source['prices_eur_kwh'],
                         'carbon_g_kwh': source['carbon_g_kwh']})
slots_edited = st.data_editor(slots_df, hide_index=True, use_container_width=True, num_rows='dynamic',
                             column_config={'price_eur_kwh': st.column_config.NumberColumn('€/kWh', min_value=0, format='%.3f'),
                                            'carbon_g_kwh': st.column_config.NumberColumn('gCO₂e/kWh', min_value=0, format='%.1f')}, key=f'hour_editor_{st.session_state.scenario_version}')

# The optimizer consumes kWh. The UI exposes SoC% and derives the kWh in
# a third read-only column; no change to the proven OR-Tools model is needed.
normalized_vehicles = vehicles_df.dropna(how='all').copy()
normalized_vehicles['soc_kwh'] = (
    pd.to_numeric(normalized_vehicles['soc_pct'], errors='coerce') * battery / 100
).round(4)
normalized_vehicles = normalized_vehicles[['id', 'soc_kwh']].to_dict('records')
edited = dict(source)
edited.update(battery_kwh=battery, reserve_kwh=reserve, chargers=int(chargers), charger_power_kw=power,
              site_power_kw=site, efficiency=eff/100, consumption_kwh_km=consumption,
              vehicles=normalized_vehicles,
              trips=trips_df.dropna(how='all').to_dict('records'),
              slots=slots_edited['slot'].tolist(),
              prices_eur_kwh=slots_edited['price_eur_kwh'].tolist(),
              carbon_g_kwh=slots_edited['carbon_g_kwh'].tolist())
if use_cap:
    edited['max_emissions_kg'] = cap
else:
    edited.pop('max_emissions_kg', None)

st.download_button('Download edited scenario · JSON', json.dumps(edited, indent=2, ensure_ascii=False).encode('utf-8'),
                   file_name='ev_scenario.json', mime='application/json')
st.divider()

st.subheader('3 · Optimize and compare')
st.caption('The comparison benchmarks use the same fleet and infrastructure without a CO₂ ceiling. Results are recomputed when you press Run optimization.')
if st.button('▶ Run optimization', type='primary', use_container_width=True):
    errors = validate(edited)
    if errors:
        st.session_state.results = {'errors': errors, 'edited': edited}
    else:
        with st.spinner('Solving schedules and checking feasibility...'):
            # Compare against both unconstrained objectives so the cost of a carbon cap is visible.
            base = copy.deepcopy(edited)
            base.pop('max_emissions_kg', None)
            cheapest = solve(base, 'cost', seconds=seconds)
            cleanest = solve(base, 'emissions', seconds=seconds)
            if edited.get('max_emissions_kg') is None:
                selected = cheapest if objective == 'Minimize cost' else cleanest
            else:
                selected = solve(edited, 'cost' if objective == 'Minimize cost' else 'emissions', seconds=seconds)
            # Only cost-minimization with various CO2 ceilings is a meaningful
            # frontier. The uncapped benchmarks are always the endpoints.
            frontier = []
            if cheapest['status'] in VALID and cleanest['status'] in VALID:
                ceilings = carbon_ceiling_candidates(
                    cleanest['total_emissions_kg'], cheapest['total_emissions_kg'])
                for threshold in ceilings:
                    capped_scenario = copy.deepcopy(base)
                    capped_scenario['max_emissions_kg'] = threshold
                    frontier.append({'ceiling_kg': threshold,
                                     'solution': solve(capped_scenario, 'cost', seconds=seconds)})
            st.session_state.results = dict(selected=selected, cheapest=cheapest, cleanest=cleanest,
                                            edited=edited, goal=objective, frontier=frontier)

results = st.session_state.results
if results and 'goal' in results and results['goal'] != objective:
    st.warning('Optimization objective changed. Press **Run optimization** to recalculate; previous results are hidden.')
    results = None
if results and 'edited' in results and json.dumps(edited, sort_keys=True, default=str) != json.dumps(results['edited'], sort_keys=True, default=str):
    st.warning('Inputs have changed since the last optimization. Press **Run optimization** to refresh; previous results are hidden.')
    results = None
if results and 'errors' in results:
    st.error('Inputs need correction:')
    for err in results['errors']:
        st.write('•', err)
elif results:
    selected = results['selected']
    goal = results['goal']

    # Always show the trip/vehicle matrix BEFORE the selected plan.
    st.markdown('#### Trip × vehicle · additional battery energy required')
    st.caption('Each cell is the extra battery energy (kWh) required if that EV takes that trip, INCLUDING the arrival reserve. 0 means no charge needed. An empty cell means the trip exceeds battery capacity even at full charge.')
    energy_matrix = pd.DataFrame(trip_vehicle_extra_energy(results['edited']))
    st.dataframe(energy_matrix, hide_index=True, use_container_width=True)
    st.download_button('Export trip–vehicle matrix · CSV',
                       energy_matrix.to_csv(index=False).encode('utf-8'),
                       'trip_vehicle_energy_matrix.csv', 'text/csv')

    # Immediate charging is a real heuristic, not the cheapest optimized plan.
    # Hold trip assignments fixed to isolate the charging-timing effect.
    comparison_name, comparison_plan = next(
        ((label, results[key]) for label, key in
         [('Selected plan', 'selected'), ('Lowest-cost plan', 'cheapest'),
          ('Lowest-emissions plan', 'cleanest')]
         if results[key]['status'] in VALID),
        (None, None))
    st.markdown('#### 18:00 charging reference · first EV first, without planned waiting')
    if comparison_plan is None:
        st.info('An 18:00 reference requires a feasible trip assignment. No feasible assignment has been found.')
    else:
        reference = immediate_18h_baseline(results['edited'], comparison_plan['assignment'])
        st.caption(f"Using the same trip assignments as: {comparison_name}. EVs are charged from 18:00 in fleet order, up to the minimum energy needed for each trip plus reserve. Charger count and depot power limits remain enforced. The CO₂ ceiling is NOT enforced for this reference.")
        if reference['status'] == 'UNAVAILABLE':
            st.warning(reference['reason'])
        else:
            if reference['status'] == 'INCOMPLETE':
                st.error(f"The first-EV-first policy cannot complete all charging before departure. {reference['reason']}")
                st.caption('Values below describe only energy already charged: they are NOT comparable to the complete optimized plan.')
            c1,c2,c3 = st.columns(3)
            c1.metric('Reference electricity cost', f"€{reference['total_cost_eur']:,.2f}")
            c2.metric('Reference CO₂e', f"{reference['total_emissions_kg']:,.3f} kg")
            c3.metric('Reference grid electricity', f"{reference['total_grid_kwh']:,.2f} kWh")
            if reference['status'] == 'COMPLETE':
                difference = reference['total_cost_eur'] - comparison_plan['total_cost_eur']
                st.caption(f"Electricity-cost difference vs the matching optimized plan: €{difference:+,.2f}. The reference is feasible but not necessarily optimal.")
            if reference['charging']:
                st.plotly_chart(schedule_plot(reference['charging'], results['edited']['slots'],
                                              '18:00 reference · grid energy by EV and hour'),
                                use_container_width=True)
                st.download_button('Export 18:00 reference schedule · CSV',
                                   to_csv(reference['charging']), 'reference_18h_schedule.csv', 'text/csv')
            else:
                st.info('No reference charging is needed for these trip assignments.')

    st.markdown(f"**Selected plan:** {goal} · **Status:** {status_text(selected['status'])}")
    if selected['status'] not in VALID:
        if selected['status'] == 'INFEASIBLE' and results['edited'].get('max_emissions_kg') is not None:
            st.error('No schedule satisfies all operating constraints and the CO₂ ceiling. Raise the ceiling or change charging capacity / energy demand.')
            if results['cleanest']['status'] in VALID:
                minimum = results['cleanest']['total_emissions_kg']
                st.info(f'The minimum-emissions benchmark is approximately {minimum:.4f} kg CO₂e. A limit below this value cannot be met under the current assumptions (provided the benchmark was solved optimally).')
            elif results['cheapest']['status'] == 'INFEASIBLE':
                st.info('Even without the emissions ceiling, the base scenario is infeasible. Check trips and charging capacity.')
        elif selected['status'] == 'INFEASIBLE':
            st.error('No physically feasible schedule for the current charging infrastructure and trips.')
        else:
            st.warning('The solver did not confirm a solution. A time limit is not proof of impossibility.')
        for diagnostic in selected.get('diagnostics', []):
            st.caption(diagnostic)
    else:
        if selected['status'] == 'FEASIBLE':
            st.warning('The solver found a valid plan but did not prove it is globally optimal. Increase the time limit for a stronger result.')
        m1,m2,m3,m4 = st.columns(4)
        m1.metric('Total electricity cost', f"€{selected['total_cost_eur']:,.2f}")
        m2.metric('Estimated emissions', f"{selected['total_emissions_kg']:,.3f} kg CO₂e")
        m3.metric('Grid electricity', f"{selected['total_grid_kwh']:,.2f} kWh")
        m4.metric('Trips assigned', f"{len(selected['assignment'])}/{len(results['edited']['trips'])}")
        ceiling = results['edited'].get('max_emissions_kg')
        if ceiling is not None:
            st.success(f'Emissions limit respected: {selected["total_emissions_kg"]:.3f} kg ≤ {ceiling:.3f} kg CO₂e')
        uncapped = results['cheapest']
        if uncapped['status'] in VALID and goal == 'Minimize cost':
            delta_cost = selected['total_cost_eur'] - uncapped['total_cost_eur']
            delta_carbon = uncapped['total_emissions_kg'] - selected['total_emissions_kg']
            st.markdown('#### Business impact · against unrestricted lowest-cost plan')
            c1,c2 = st.columns(2)
            c1.metric('Additional electricity cost', f'€{delta_cost:,.2f}')
            c2.metric('Estimated CO₂e reduction', f'{delta_carbon:,.3f} kg')
            st.caption('This comparison quantifies the impact of the carbon ceiling, not savings against an actual fleet baseline. The unconstrained cost benchmark excludes any carbon ceiling.')
        st.markdown('#### Charging schedule')
        charges = pd.DataFrame(selected['charging'])
        if len(charges):
            st.plotly_chart(schedule_plot(selected['charging'], results['edited']['slots'],
                                          'Optimized charging · grid energy by EV and hour'),
                            use_container_width=True)
            hourly = charges.groupby('slot', as_index=False)[['grid_energy_kwh', 'cost_eur', 'emissions_kg']].sum()
            with st.expander('Hourly charging totals'):
                st.dataframe(hourly, hide_index=True, use_container_width=True)
            with st.expander('Detailed charging instructions'):
                st.dataframe(charges, hide_index=True, use_container_width=True)
            st.download_button('Export charging schedule · CSV', to_csv(selected['charging']), 'charging_schedule.csv', 'text/csv')
        else:
            st.info('No charging necessary; the available battery energy already covers the assignments.')
        st.markdown('#### Trip assignments')
        st.dataframe(pd.DataFrame(selected['assignment']), hide_index=True, use_container_width=True)
        st.download_button('Export trip assignments · CSV', to_csv(selected['assignment']), 'trip_assignments.csv', 'text/csv')
    st.markdown('#### Cost versus environmental impact')
    rows=[]
    for label,key in [('Lowest-cost benchmark', 'cheapest'), ('Lowest-emissions benchmark', 'cleanest'),
                      ('Selected strategy', 'selected')]:
        outcome = results[key]
        rows.append({'Strategy': label, 'CO₂ ceiling (kg)': None, 'Status': status_text(outcome['status']),
                     'Cost (€)': outcome.get('total_cost_eur'),
                     'Emissions (kg CO₂e)': outcome.get('total_emissions_kg')})
    for run in results.get('frontier', []):
        outcome = run['solution']
        rows.append({'Strategy': f"CO₂ ceiling {run['ceiling_kg']} kg",
                     'CO₂ ceiling (kg)': run['ceiling_kg'], 'Status': status_text(outcome['status']),
                     'Cost (€)': outcome.get('total_cost_eur'),
                     'Emissions (kg CO₂e)': outcome.get('total_emissions_kg')})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    available = [r for r in rows if r['Cost (€)'] is not None]
    if available:
        fig2 = px.scatter(pd.DataFrame(available), x='Emissions (kg CO₂e)', y='Cost (€)',
                          color='Strategy', hover_name='Strategy',
                          hover_data={'CO₂ ceiling (kg)': True, 'Status': True},
                          title='Cost–carbon trade-off · benchmarks and CO₂ ceilings')
        fig2.update_traces(marker_size=14)
        st.plotly_chart(fig2, use_container_width=True)
    candidates = [run['ceiling_kg'] for run in results.get('frontier', [])]
    if candidates:
        st.caption('Ceilings are generated by rounding UP the lowest-emissions benchmark to the next whole kg, then adding 4 kg at each step until the next value would reach or exceed the lowest-cost benchmark’s emissions. Example: 13.7 → 14 → 18, 22, 26 (below 27.62). The points show actual optimized emissions, which may be below their ceilings.')
    else:
        st.caption('No intermediate 4 kg CO₂ ceilings fit strictly between the two benchmarks.')
    st.caption('Benchmarks or the selected plan can coincide. Only OPTIMAL status proves global optimality. Costs and emissions are estimates based on synthetic input data.')
    st.download_button('Export full results · JSON', json.dumps(results,indent=2,ensure_ascii=False).encode('utf-8'),
                       'optimization_results.json', 'application/json')

with st.expander('Methodology, interpretation and limitations'):
    st.markdown('''
- **Solver:** OR-Tools CP-SAT; jointly assigns each trip to one vehicle and selects hourly charging energy.
- **Operational restrictions:** a trip must fit in a battery with the required reserve; every vehicle receives at most one trip; charger concurrency, charger charging rate and depot capacity are enforced.
- **Carbon cap:** total estimated location-based charging emissions cannot exceed the entered **kg CO₂e** threshold; no automatic weakening of the cap.
- **Charging:** integer 0.1 kWh battery-energy increments, constant efficiency and fixed hourly power bounds. This model does not simulate nonlinear battery tapering or require a minimum charging session length.
- **Initial charge:** the UI accepts a SoC percentage, derives stored kWh as battery capacity × SoC / 100, and passes kWh to the optimizer.
- **Pairing matrix:** each cell estimates additional stored kWh for the indicated EV and trip, counting required arrival reserve and 0.1 kWh rounding.
- **18:00 reference:** holds the chosen optimized trip assignments fixed; starts charging the first EVs in ID/table order as soon as the 18:00 slot begins, using the available chargers continuously in successive hourly slots. Charges only to the minimum trip-plus-reserve requirement. If it does not finish by departure, its partial totals are not a valid comparison.
- **Trade-off curve:** solves additional cost-minimizing runs at integer CO₂ ceilings beginning at ceil(min-emissions)+4, then +4 again, strictly below lowest-cost benchmark emissions. Each run has its own solver status.
- **Timing:** all charging takes place in the listed hourly slots before all departures. No intermediate recharging, travel routing, or staggered departure times.
- **Economic scope:** electricity energy costs only; no network charges, PPA, battery degradation, demand charges or taxes.
- **Environmental scope:** estimated grid-consumption emissions from user-supplied average carbon intensity. Not a contractual Scope 2 inventory and not automatically marginal emissions.
- **Demonstration:** no live price, carbon, telematics or charger feeds. Outputs require verification against actual operations before real-world use.
''')
