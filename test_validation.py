"""Input validation regression tests."""
import copy
import json
import unittest
from pathlib import Path
from ev_optimizer import validate

BASE = json.loads((Path(__file__).parent / 'example.json').read_text(encoding='utf-8'))


class ValidationTests(unittest.TestCase):
    def test_original_valid(self):
        self.assertEqual(validate(copy.deepcopy(BASE)), [])

    def test_mismatched_time_vectors(self):
        d = copy.deepcopy(BASE)
        d['prices_eur_kwh'].pop()
        self.assertTrue(validate(d))

    def test_duplicate_vehicle_id(self):
        d = copy.deepcopy(BASE)
        d['vehicles'][1]['id'] = d['vehicles'][0]['id']
        self.assertTrue(validate(d))

    def test_over_capacity_soc(self):
        d = copy.deepcopy(BASE)
        d['vehicles'][0]['soc_kwh'] = 999
        self.assertTrue(validate(d))

    def test_negative_emissions_ceiling(self):
        d = copy.deepcopy(BASE)
        d['max_emissions_kg'] = -0.01
        self.assertTrue(validate(d))


if __name__ == '__main__':
    unittest.main()
