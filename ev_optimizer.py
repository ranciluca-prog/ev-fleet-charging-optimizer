"""MVP EV fleet: verification + joint trip assignment / night charging using OR-Tools CP-SAT.

Run: python ev_optimizer.py example.json --objective cost
     python ev_optimizer.py example.json --objective emissions
No live electricity or emissions feeds are used.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from ortools.sat.python import cp_model

SCALE = 10  # one integer energy unit = 0.1 kWh stored in a battery


def units(kwh: float, direction: str = 'ceil') -> int:
    number = float(kwh) * SCALE
    return math.ceil(number - 1e-9) if direction == 'ceil' else math.floor(number + 1e-9)


def energy_of_trip(trip: dict, consumption: float) -> float:
    if 'energy_kwh' in trip:
        return float(trip['energy_kwh'])
    return float(trip['distance_km']) * consumption


def validate(data: dict) -> list[str]:
    errors: list[str] = []
    try:
        vehicles, trips = data['vehicles'], data['trips']
        slots, tariffs, carbon = data['slots'], data['prices_eur_kwh'], data['carbon_g_kwh']
        capacity = float(data['battery_kwh'])
        reserve = float(data['reserve_kwh'])
        power = float(data['charger_power_kw'])
        site = float(data['site_power_kw'])
        eff = float(data['efficiency'])
        chargers = int(data['chargers'])
        consumption = float(data['consumption_kwh_km'])
        limit = data.get('max_emissions_kg')
        if limit is not None and (not math.isfinite(float(limit)) or float(limit) < 0):
            errors.append('Il limite massimo di emissioni deve essere un numero non negativo (kg CO2e).')
        if not vehicles or not slots:
            errors.append('Servono almeno un veicolo e un intervallo temporale.')
        if len(slots) != len(tariffs) or len(slots) != len(carbon):
            errors.append('Slots, prezzi ed emissioni devono avere la stessa lunghezza.')
        if len(set(slots)) != len(slots):
            errors.append('Gli intervalli temporali devono essere univoci.')
        if capacity <= 0 or not 0 <= reserve < capacity:
            errors.append('Capacita e riserva della batteria non valide.')
        if power <= 0 or site <= 0 or chargers <= 0 or not 0 < eff <= 1:
            errors.append('Potenza, numero colonnine o efficienza non validi.')
        if consumption <= 0:
            errors.append('Consumo kWh/km non valido.')
        if len({v['id'] for v in vehicles}) != len(vehicles):
            errors.append('ID veicolo duplicati.')
        if len({t['id'] for t in trips}) != len(trips):
            errors.append('ID viaggio duplicati.')
        if any(float(v['soc_kwh']) < 0 or float(v['soc_kwh']) > capacity for v in vehicles):
            errors.append('SoC iniziale fuori dai limiti della batteria.')
        if any(energy_of_trip(t, consumption) < 0 for t in trips):
            errors.append('Energia viaggio negativa.')
        if any(not math.isfinite(float(p)) or float(p) < 0 for p in tariffs) or any(not math.isfinite(float(c)) or float(c) < 0 for c in carbon):
            errors.append('Prezzi ed emissioni devono essere non negativi nell\'MVP.')
        if len(trips) > len(vehicles):
            errors.append('Piu viaggi che veicoli: nell\'MVP ogni mezzo svolge al massimo un viaggio.')
        for t in trips:
            needed = energy_of_trip(t, consumption) + reserve
            if needed > capacity + 1e-9:
                errors.append(f"Viaggio {t['id']}: richiede {needed:.1f} kWh inclusa riserva, "
                              f"ma la capacita e {capacity:.1f} kWh.")
        if len(trips) == 0:
            errors.append('Non ci sono viaggi da programmare.')
    except (KeyError, ValueError, TypeError, OverflowError) as exc:
        errors.append(f'Dati mancanti o non validi: {exc}')
    return errors


def build_model(data: dict, objective: str | None = None):
    """Make joint assignment and charging model. Every slot is one hour before every trip."""
    m = cp_model.CpModel()
    vehicles, trips, slots = data['vehicles'], data['trips'], data['slots']
    nv, nt, nh = len(vehicles), len(trips), len(slots)
    cap = units(data['battery_kwh'], 'floor')
    reserve = units(data['reserve_kwh'])
    eff = float(data['efficiency'])
    charger_gain = units(float(data['charger_power_kw']) * eff, 'floor')
    site_gain = units(float(data['site_power_kw']) * eff, 'floor')
    consumption = float(data['consumption_kwh_km'])
    demands = [units(energy_of_trip(t, consumption)) for t in trips]
    initial = [units(v['soc_kwh'], 'floor') for v in vehicles]

    assignment = {(v, t): m.NewBoolVar(f'assign_{v}_{t}')
                  for v in range(nv) for t in range(nt)}
    for t in range(nt):
        m.Add(sum(assignment[v, t] for v in range(nv)) == 1)
    for v in range(nv):
        m.Add(sum(assignment[v, t] for t in range(nt)) <= 1)

    plugged = {(v, h): m.NewBoolVar(f'plugged_{v}_{h}')
               for v in range(nv) for h in range(nh)}
    charge = {(v, h): m.NewIntVar(0, charger_gain, f'charge_{v}_{h}')
              for v in range(nv) for h in range(nh)}
    for h in range(nh):
        m.Add(sum(plugged[v, h] for v in range(nv)) <= int(data['chargers']))
        m.Add(sum(charge[v, h] for v in range(nv)) <= site_gain)
        for v in range(nv):
            m.Add(charge[v, h] <= charger_gain * plugged[v, h])
            m.Add(charge[v, h] >= plugged[v, h])
    for v in range(nv):
        total_charge = sum(charge[v, h] for h in range(nh))
        m.Add(initial[v] + total_charge <= cap)
        required = sum(demands[t] * assignment[v, t] for t in range(nt))
        # Every active vehicle must depart with its trip energy plus the reserve.
        m.Add(initial[v] + total_charge >= required + reserve * sum(
            assignment[v, t] for t in range(nt)))

    # Integer micro-kg coefficients. Ceil keeps the cap conservative despite CP-SAT integers.
    # charge unit = 0.1 kWh STORED; grid kWh = charge / (10 * efficiency).
    # 1e6 * charge * 0.1 * carbon_g_kwh / (efficiency * 1000)
    # = charge * carbon_g_kwh * 100 / efficiency micro-kg CO2e.
    emission_coefficients = [math.ceil(float(g) * 100 / eff - 1e-9) for g in data['carbon_g_kwh']]
    if data.get('max_emissions_kg') is not None:
        max_micro_kg = math.floor(float(data['max_emissions_kg']) * 1_000_000 + 1e-9)
        m.Add(sum(emission_coefficients[h] * charge[v, h]
                  for v in range(nv) for h in range(nh)) <= max_micro_kg)

    if objective is not None:
        if objective == 'cost':
            # Objective coefficients per 0.1 kWh stored; scaling removes fractions.
            weight = [round(float(p) * 100_000 / eff) for p in data['prices_eur_kwh']]
        elif objective == 'emissions':
            weight = emission_coefficients
        else:
            raise ValueError('Obiettivo sconosciuto: usare cost oppure emissions.')
        m.Minimize(sum(weight[h] * charge[v, h]
                       for v in range(nv) for h in range(nh)))
    return m, assignment, plugged, charge


def solve(data: dict, objective: str | None = None, seconds: float = 15) -> dict[str, Any]:
    errors = validate(data)
    if errors:
        return {'status': 'INVALID', 'diagnostics': errors}
    model, assignment, plugged, charge = build_model(data, objective)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)
    status_name = solver.StatusName(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {'status': status_name, 'diagnostics': [
            'Nessuna soluzione trovata con questi vincoli.' if status == cp_model.INFEASIBLE else
            'La ricerca non ha trovato una soluzione nel tempo concesso: non implica impossibilita.']}

    vehicles, trips, slots = data['vehicles'], data['trips'], data['slots']
    efficiency = float(data['efficiency'])
    charging = []
    assigned = []
    for v, vehicle in enumerate(vehicles):
        added = 0
        for h, label in enumerate(slots):
            q = solver.Value(charge[v, h])
            if q:
                stored = q / SCALE
                purchased = stored / efficiency
                charging.append({
                    'slot': label, 'vehicle': vehicle['id'], 'battery_added_kwh': stored,
                    'grid_energy_kwh': round(purchased, 3),
                    'cost_eur': round(purchased * float(data['prices_eur_kwh'][h]), 4),
                    'emissions_kg': round(purchased * float(data['carbon_g_kwh'][h]) / 1000, 4)})
                added += q
        for t, trip in enumerate(trips):
            if solver.Value(assignment[v, t]):
                assigned.append({
                    'trip': trip['id'], 'vehicle': vehicle['id'],
                    'trip_energy_kwh': round(energy_of_trip(trip, float(data['consumption_kwh_km'])), 2),
                    'departure_soc_kwh': round(units(vehicle['soc_kwh'], 'floor') / SCALE + added / SCALE, 2),
                    'expected_arrival_soc_kwh': round(units(vehicle['soc_kwh'], 'floor') / SCALE + added / SCALE -
                                                      energy_of_trip(trip, float(data['consumption_kwh_km'])), 2)})
    # Use unrounded contributions for cap/metrics; round only final values.
    exact_cost = sum(item['battery_added_kwh'] / efficiency * float(data['prices_eur_kwh'][slots.index(item['slot'])]) for item in charging)
    exact_emissions = sum(item['battery_added_kwh'] / efficiency * float(data['carbon_g_kwh'][slots.index(item['slot'])]) / 1000 for item in charging)
    return {'status': status_name, 'objective': objective or 'feasibility',
            'max_emissions_kg': data.get('max_emissions_kg'),
            'assignment': assigned, 'charging': charging,
            'total_grid_kwh': round(sum(item['battery_added_kwh'] / efficiency for item in charging), 3),
            'total_cost_eur': round(exact_cost, 2),
            'total_emissions_kg': round(exact_emissions, 4),
            'emissions_cap_respected': (data.get('max_emissions_kg') is None or
                                        exact_emissions <= float(data['max_emissions_kg']) + 1e-9)}


def main() -> None:
    ap = argparse.ArgumentParser(description='EV fleet feasibility and charging optimizer')
    ap.add_argument('input', type=Path, help='JSON dataset')
    ap.add_argument('--objective', choices=['cost', 'emissions'], default='cost')
    ap.add_argument('--seconds', type=float, default=15)
    ap.add_argument('--max-emissions-kg', type=float, default=None,
                    help='Optional total CO2e limit in kg, overriding JSON')
    ap.add_argument('--output', type=Path, default=None)
    args = ap.parse_args()
    data = json.loads(args.input.read_text(encoding='utf-8'))
    if args.max_emissions_kg is not None:
        data['max_emissions_kg'] = args.max_emissions_kg
    feasibility = solve(data, None, args.seconds)
    if feasibility['status'] in ('OPTIMAL', 'FEASIBLE'):
        optimization = solve(data, args.objective, args.seconds)
    else:
        optimization = None
    result = {'verification': {'status': feasibility['status'],
                               'diagnostics': feasibility.get('diagnostics', [])},
              'optimization': optimization}
    content = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(content, encoding='utf-8')
        print(f'Risultato salvato in {args.output}')
    else:
        print(content)


if __name__ == '__main__':
    main()
