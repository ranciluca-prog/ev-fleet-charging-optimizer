"""Run: python -m unittest -v test_ev_optimizer.py (after installing OR-Tools)."""
import copy
import json
import unittest
from pathlib import Path

from ev_optimizer import solve

BASE = json.loads((Path(__file__).parent / 'example.json').read_text(encoding='utf-8'))


class TestEVOptimizer(unittest.TestCase):
    def test_example_has_feasible_plan(self):
        result = solve(copy.deepcopy(BASE), 'cost', seconds=30)
        self.assertIn(result['status'], ('OPTIMAL', 'FEASIBLE'))
        self.assertEqual(len(result['assignment']), len(BASE['trips']))
        self.assertEqual(len({a['vehicle'] for a in result['assignment']}), len(BASE['trips']))
        for assignment in result['assignment']:
            self.assertGreaterEqual(assignment['expected_arrival_soc_kwh'], BASE['reserve_kwh'] - 0.001)

    def test_impossible_trip_rejected(self):
        data = copy.deepcopy(BASE)
        data['trips'][0]['distance_km'] = 500  # 125 + 10 kWh > 80 kWh
        result = solve(data, 'cost')
        self.assertEqual(result['status'], 'INVALID')
        self.assertIn('TR01', ' '.join(result['diagnostics']))

    def test_insufficient_charging_capacity(self):
        data = copy.deepcopy(BASE)
        for v in data['vehicles']:
            v['soc_kwh'] = 0
        data['chargers'] = 1
        data['site_power_kw'] = 1  # only about 12.6 kWh stored over 14 hours
        result = solve(data, None, seconds=30)
        self.assertEqual(result['status'], 'INFEASIBLE')

    def test_emissions_mode_returns_metrics(self):
        result = solve(copy.deepcopy(BASE), 'emissions', seconds=30)
        self.assertIn(result['status'], ('OPTIMAL', 'FEASIBLE'))
        self.assertGreaterEqual(result['total_emissions_kg'], 0)
        self.assertGreaterEqual(result['total_cost_eur'], 0)


if __name__ == '__main__':
    unittest.main()
