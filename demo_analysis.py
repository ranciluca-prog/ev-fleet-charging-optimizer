"""Transparent analysis helpers for the EV Streamlit demo.

No OR-Tools or Streamlit dependency: tests can check the reference policy,
trip-vehicle energy matrix and carbon-ceiling sequence independently.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import math
from typing import Any

SCALE = 10  # Consistent with ev_optimizer: 0.1 kWh stored in a battery.


def to_units(value_kwh: float, rounding: str = 'ceil') -> int:
    scaled = float(value_kwh) * SCALE
    if rounding == 'floor':
        return math.floor(scaled + 1e-9)
    if rounding == 'ceil':
        return math.ceil(scaled - 1e-9)
    raise ValueError('rounding must be ceil or floor')


def trip_energy_kwh(trip: dict, consumption_kwh_km: float) -> float:
    return (float(trip['energy_kwh']) if 'energy_kwh' in trip
            else float(trip['distance_km']) * float(consumption_kwh_km))


def trip_vehicle_extra_energy(data: dict) -> list[dict]:
    """How much EXTRA stored battery energy each vehicle needs for each trip.

    None denotes a physically impossible pair (trip + reserve exceeds usable
    battery capacity). The displayed figures follow the solver's 0.1 kWh
    discretization and reserve convention.
    """
    rows: list[dict] = []
    capacity = to_units(data['battery_kwh'], 'floor')
    reserve = to_units(data['reserve_kwh'])
    initial = {v['id']: to_units(v['soc_kwh'], 'floor') for v in data['vehicles']}
    for trip in data['trips']:
        demand = to_units(trip_energy_kwh(trip, data['consumption_kwh_km'])) + reserve
        row = {'Trip': trip['id']}
        for vehicle in data['vehicles']:
            row[vehicle['id']] = (None if demand > capacity
                                  else round(max(0, demand - initial[vehicle['id']]) / SCALE, 1))
        rows.append(row)
    return rows


def carbon_ceiling_candidates(low_emissions_kg: float, high_emissions_kg: float,
                              increment_kg: int = 4) -> list[int]:
    """Ceil(minimum emissions), add 4 kg each step; stop strictly below lowest-cost emissions.

    Example: 13.705 -> ceil=14 -> 18, 22, 26 (if lowest-cost is 27.629).
    """
    low = float(low_emissions_kg)
    high = float(high_emissions_kg)
    if not (math.isfinite(low) and math.isfinite(high)):
        return []
    if increment_kg <= 0:
        raise ValueError('increment_kg must be strictly positive')
    if high <= low:
        return []
    first = math.ceil(low - 1e-9) + increment_kg
    # strict upper endpoint: avoid a cap equal to the lowest-cost benchmark.
    last = math.ceil(high - 1e-9) - 1
    if first > last:
        return []
    return list(range(first, last + 1, increment_kg))


def immediate_18h_baseline(data: dict, assignments: list[dict]) -> dict[str, Any]:
    """FIFO first-EV-first reference charge beginning at 18:00.

    The reference keeps the SAME trip assignments as the given optimized plan
    and adds only the minimum energy for each trip including the reserve.
    At each hourly slot, serve up to N EVs in fleet order (one charger/EV),
    filling available charger and depot power before moving to the next EV.
    No strategic waiting or shifting to cheap/clean slots is performed.

    If the hourly time series or available hours cannot cover all shortages,
    the return status is UNAVAILABLE or INCOMPLETE; partial energy expenditure
    is NOT a valid like-for-like benchmark.
    """
    slots = data['slots']
    try:
        timestamps = [datetime.fromisoformat(str(s)) for s in slots]
    except (TypeError, ValueError):
        return {'status': 'UNAVAILABLE', 'reason': 'Slot labels must be ISO dates and hours, e.g. 2026-12-10 18:00.'}
    if not timestamps or any((timestamps[i + 1] - timestamps[i]) != timedelta(hours=1)
                                 for i in range(len(timestamps) - 1)):
        return {'status': 'UNAVAILABLE', 'reason': 'Hourly slots must be chronological and consecutive for the 18:00 reference.'}
    start_positions = [i for i, dt in enumerate(timestamps) if dt.hour == 18 and dt.minute == 0]
    if not start_positions:
        return {'status': 'UNAVAILABLE', 'reason': 'The time horizon has no 18:00 slot. Add a slot at 18:00 to calculate this baseline.'}
    start_index = start_positions[0]

    by_trip = {trip['id']: trip for trip in data['trips']}
    by_vehicle = {v['id']: v for v in data['vehicles']}
    assignment_by_vehicle = {a['vehicle']: a['trip'] for a in assignments}
    reserve = to_units(data['reserve_kwh'])
    capacity = to_units(data['battery_kwh'], 'floor')
    remaining: dict[str, int] = {}
    for vehicle in data['vehicles']:
        vehicle_id = vehicle['id']
        if vehicle_id not in assignment_by_vehicle:
            continue
        trip_id = assignment_by_vehicle[vehicle_id]
        if trip_id not in by_trip:
            return {'status': 'UNAVAILABLE', 'reason': f'Unknown assigned trip: {trip_id}.'}
        requirement = to_units(trip_energy_kwh(by_trip[trip_id], data['consumption_kwh_km'])) + reserve
        if requirement > capacity:
            return {'status': 'UNAVAILABLE', 'reason': f'{trip_id} exceeds battery capacity including the reserve.'}
        available = to_units(vehicle['soc_kwh'], 'floor')
        remaining[vehicle_id] = max(0, requirement - available)

    # Apply the same per-hour stored-energy quantization as OR-Tools.
    eff = float(data['efficiency'])
    charger_limit = to_units(float(data['charger_power_kw']) * eff, 'floor')
    site_limit = to_units(float(data['site_power_kw']) * eff, 'floor')
    num_chargers = int(data['chargers'])
    items: list[dict] = []
    total_cost = total_emissions = total_grid = 0.0

    for h in range(start_index, len(slots)):
        # The first unfinished EVs keep their priority until sufficiently charged.
        chosen = [v['id'] for v in data['vehicles'] if remaining.get(v['id'], 0) > 0][:num_chargers]
        slot_remaining = site_limit
        for v_id in chosen:
            q = min(remaining[v_id], charger_limit, slot_remaining)
            if q <= 0:
                continue
            remaining[v_id] -= q
            slot_remaining -= q
            stored = q / SCALE
            purchased = stored / eff
            cost = purchased * float(data['prices_eur_kwh'][h])
            carbon = purchased * float(data['carbon_g_kwh'][h]) / 1000
            total_grid += purchased
            total_cost += cost
            total_emissions += carbon
            items.append({'slot': slots[h], 'vehicle': v_id,
                          'battery_added_kwh': stored,
                          'grid_energy_kwh': round(purchased, 3),
                          'cost_eur': round(cost, 4),
                          'emissions_kg': round(carbon, 4)})

    shortage = sum(remaining.values()) / SCALE
    return {'status': 'COMPLETE' if shortage == 0 else 'INCOMPLETE',
            'start_hour': slots[start_index],
            'charging': items,
            'total_grid_kwh': round(total_grid, 3),
            'total_cost_eur': round(total_cost, 2),
            'total_emissions_kg': round(total_emissions, 4),
            'unserved_battery_kwh': round(shortage, 2),
            'target_battery_kwh': round(sum(item['battery_added_kwh'] for item in items) + shortage, 2),
            'reason': ('All assigned trips receive their required battery energy.' if shortage == 0
                       else f'Insufficient charging time/capacity: {shortage:.1f} kWh of required battery energy remain uncharged.')}
