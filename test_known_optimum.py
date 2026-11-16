"""Small hand-checkable optimization tests, run with: python -m unittest discover -v."""
import unittest

from ev_optimizer import solve


def tiny_scenario():
    return {
        'vehicles': [{'id': 'EV1', 'soc_kwh': 0.0}],
        'trips': [{'id': 'T1', 'energy_kwh': 1.0}],
        'slots': ['2026-12-10 23:00'],
        'prices_eur_kwh': [0.2],
        'carbon_g_kwh': [100.0],
        'battery_kwh': 10.0,
        'reserve_kwh': 0.0,
        'consumption_kwh_km': 0.25,
        'charger_power_kw': 2.0,
        'site_power_kw': 2.0,
        'chargers': 1,
        'efficiency': 1.0,
    }


class KnownOptimumTests(unittest.TestCase):
    def test_one_vehicle_exact_optimum(self):
        out = solve(tiny_scenario(), 'cost', seconds=10)
        self.assertEqual(out['status'], 'OPTIMAL')
        self.assertAlmostEqual(out['total_grid_kwh'], 1.0, places=3)
        self.assertAlmostEqual(out['total_cost_eur'], 0.2, places=2)
        self.assertAlmostEqual(out['total_emissions_kg'], 0.1, places=4)
        self.assertEqual(out['assignment'][0]['vehicle'], 'EV1')

    def test_exact_carbon_cap_is_feasible(self):
        scenario = tiny_scenario()
        scenario['max_emissions_kg'] = 0.1
        out = solve(scenario, 'cost', seconds=10)
        self.assertEqual(out['status'], 'OPTIMAL')
        self.assertTrue(out['emissions_cap_respected'])

    def test_cap_just_below_minimum_is_infeasible(self):
        scenario = tiny_scenario()
        scenario['max_emissions_kg'] = 0.0999
        self.assertEqual(solve(scenario, 'cost', seconds=10)['status'], 'INFEASIBLE')

    def test_site_power_prevents_required_energy(self):
        scenario = tiny_scenario()
        scenario['site_power_kw'] = 0.5
        self.assertEqual(solve(scenario, 'cost', seconds=10)['status'], 'INFEASIBLE')


if __name__ == '__main__':
    unittest.main()
