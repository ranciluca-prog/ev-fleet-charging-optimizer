"""Independent analytic tests: these also run when OR-Tools is not installed."""
import copy
import json
from pathlib import Path
import unittest

from demo_analysis import carbon_ceiling_candidates, immediate_18h_baseline, trip_vehicle_extra_energy

BASE = json.loads((Path(__file__).parent / 'example.json').read_text(encoding='utf-8'))


class DemoAnalysisTests(unittest.TestCase):
    def test_carbon_ceiling_explicit_steps(self):
        # The verbal rule is +4 each time, hence 18,22,26 (not 18,20,22,24).
        self.assertEqual(carbon_ceiling_candidates(13.705, 27.629), [18, 22, 26])
        self.assertEqual(carbon_ceiling_candidates(13.705, 18), [])
        self.assertEqual(carbon_ceiling_candidates(16, 20.01), [20])
        self.assertEqual(carbon_ceiling_candidates(24, 25), [])
        self.assertEqual(carbon_ceiling_candidates(27.63, 13.7), [])

    def test_matrix_zero_and_positive_shortfall(self):
        data = copy.deepcopy(BASE)
        rows = trip_vehicle_extra_energy(data)
        self.assertEqual(len(rows), 10)
        self.assertEqual(rows[0]['Trip'], 'TR01')
        # 240 km at 0.25 kWh/km + 10 reserve = 70 kWh, EV01 has 60.
        self.assertEqual(rows[0]['EV01'], 10.0)
        # TR10 = 80 km -> 20 + 10 reserve, EV01 already has enough.
        self.assertEqual(rows[-1]['EV01'], 0.0)
        self.assertEqual(rows[-1]['EV10'], 18.0)
        data['trips'][0]['distance_km'] = 500
        self.assertIsNone(trip_vehicle_extra_energy(data)[0]['EV01'])

    def test_first_ev_from_18_earliest_slot(self):
        data = {'vehicles': [{'id': 'EV01', 'soc_kwh': 0}, {'id': 'EV02', 'soc_kwh': 0}],
                'trips': [{'id': 'A', 'energy_kwh': 2}, {'id': 'B', 'energy_kwh': 1}],
                'slots': ['2026-12-10 18:00', '2026-12-10 19:00', '2026-12-10 20:00'],
                'prices_eur_kwh': [0.2, 0.5, 0.7],
                'carbon_g_kwh': [100, 200, 300],
                'battery_kwh': 5, 'reserve_kwh': 0, 'consumption_kwh_km': .25,
                'charger_power_kw': 1, 'site_power_kw': 1,
                'chargers': 1, 'efficiency': 1.0}
        assignments = [{'vehicle': 'EV01', 'trip': 'A'}, {'vehicle': 'EV02', 'trip': 'B'}]
        result = immediate_18h_baseline(data, assignments)
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual([r['vehicle'] for r in result['charging']], ['EV01', 'EV01', 'EV02'])
        self.assertEqual([r['slot'] for r in result['charging']], data['slots'])
        self.assertAlmostEqual(result['total_grid_kwh'], 3.0)
        self.assertAlmostEqual(result['total_cost_eur'], 1.4)
        self.assertAlmostEqual(result['total_emissions_kg'], .6)

    def test_parallel_chargers_obey_site_limit(self):
        data = {'vehicles': [{'id': 'EV01', 'soc_kwh': 0}, {'id': 'EV02', 'soc_kwh': 0}],
                'trips': [{'id': 'A', 'energy_kwh': 1}, {'id': 'B', 'energy_kwh': 1}],
                'slots': ['2026-12-10 18:00', '2026-12-10 19:00'],
                'prices_eur_kwh': [.1, .2], 'carbon_g_kwh': [100, 100],
                'battery_kwh': 5, 'reserve_kwh': 0, 'consumption_kwh_km': .25,
                'charger_power_kw': 2, 'site_power_kw': 1.5,
                'chargers': 2, 'efficiency': 1.0}
        assignments = [{'vehicle': 'EV01', 'trip': 'A'}, {'vehicle': 'EV02', 'trip': 'B'}]
        result = immediate_18h_baseline(data, assignments)
        self.assertEqual(result['status'], 'COMPLETE')
        totals = {}
        for record in result['charging']:
            totals.setdefault(record['slot'], 0.0)
            totals[record['slot']] += record['battery_added_kwh']
        self.assertLessEqual(totals[data['slots'][0]], 1.5)
        self.assertEqual([r['vehicle'] for r in result['charging']], ['EV01', 'EV02', 'EV02'])

    def test_unavailable_and_incomplete(self):
        data = copy.deepcopy(BASE)
        assigned = [{'vehicle': 'EV10', 'trip': 'TR01'}]
        data['slots'] = ['2026-12-10 20:00']
        data['prices_eur_kwh'] = [.1]
        data['carbon_g_kwh'] = [100]
        self.assertEqual(immediate_18h_baseline(data, assigned)['status'], 'UNAVAILABLE')
        data['slots'] = ['2026-12-10 18:00']
        result = immediate_18h_baseline(data, assigned)
        self.assertEqual(result['status'], 'INCOMPLETE')
        self.assertGreater(result['unserved_battery_kwh'], 0)


if __name__ == '__main__':
    unittest.main()
