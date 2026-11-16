"""Regression tests for the capped optimization."""
import copy
import json
import unittest
from pathlib import Path
from ev_optimizer import solve

BASE = json.loads((Path(__file__).parent / 'example.json').read_text(encoding='utf-8'))
GOOD = ('OPTIMAL', 'FEASIBLE')


class TestCarbonCeiling(unittest.TestCase):
    def test_cost_with_loose_ceiling_matches_unconstrained(self):
        original = solve(copy.deepcopy(BASE), 'cost', seconds=30)
        self.assertIn(original['status'], GOOD)
        scenario = copy.deepcopy(BASE)
        scenario['max_emissions_kg'] = 1000
        capped = solve(scenario, 'cost', seconds=30)
        self.assertIn(capped['status'], GOOD)
        self.assertTrue(capped['emissions_cap_respected'])
        self.assertAlmostEqual(capped['total_cost_eur'], original['total_cost_eur'], places=2)

    def test_zero_emissions_cap_makes_case_infeasible(self):
        scenario = copy.deepcopy(BASE)
        scenario['max_emissions_kg'] = 0
        self.assertEqual(solve(scenario, 'cost', seconds=30)['status'], 'INFEASIBLE')

    def test_negative_cap_rejected(self):
        scenario = copy.deepcopy(BASE)
        scenario['max_emissions_kg'] = -1
        self.assertEqual(solve(scenario, 'cost')['status'], 'INVALID')

    def test_cap_between_extrema(self):
        low = solve(copy.deepcopy(BASE), 'emissions', seconds=30)
        high = solve(copy.deepcopy(BASE), 'cost', seconds=30)
        self.assertIn(low['status'], GOOD)
        self.assertIn(high['status'], GOOD)
        self.assertLessEqual(low['total_emissions_kg'], high['total_emissions_kg'] + 0.0001)
        if high['total_emissions_kg'] - low['total_emissions_kg'] < 0.05:
            self.skipTest('No meaningful carbon trade-off in this scenario')
        scenario = copy.deepcopy(BASE)
        scenario['max_emissions_kg'] = (low['total_emissions_kg'] + high['total_emissions_kg']) / 2
        result = solve(scenario, 'cost', seconds=30)
        self.assertIn(result['status'], GOOD)
        self.assertTrue(result['emissions_cap_respected'])
        self.assertLessEqual(result['total_emissions_kg'], scenario['max_emissions_kg'] + 0.00011)
        self.assertGreaterEqual(result['total_cost_eur'], high['total_cost_eur'] - .01)


if __name__ == '__main__':
    unittest.main()
