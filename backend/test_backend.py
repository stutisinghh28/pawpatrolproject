"""
Unit & Integration Tests for PawPatrol Triage Logic and API Payloads
"""

import unittest
import sys
import os

# Add backend directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from local_server import calculate_risk

class TestPawPatrolTriageLogic(unittest.TestCase):

    def test_critical_unconscious(self):
        """Unconscious animal must always evaluate to CRITICAL priority."""
        level, score, reasons = calculate_risk('CRITICAL_INJURY', ['unconscious'], False, 'adult')
        self.assertEqual(level, 'CRITICAL')
        self.assertGreaterEqual(score, 10)
        self.assertTrue(any('unconscious' in r.lower() for r in reasons))

    def test_critical_hit_by_car_and_bleeding(self):
        """Hit by vehicle with active bleeding should be CRITICAL."""
        level, score, reasons = calculate_risk('CRITICAL_INJURY', ['hit_by_vehicle', 'bleeding_heavily'], False, 'adult')
        self.assertEqual(level, 'CRITICAL')
        self.assertGreaterEqual(score, 10)

    def test_high_broken_bone(self):
        """Broken bone or fracture should be HIGH priority."""
        level, score, reasons = calculate_risk('MODERATE_INJURY', ['broken_bone'], False, 'adult')
        self.assertEqual(level, 'HIGH')
        self.assertIn(score, range(5, 12))

    def test_high_trapped_infant(self):
        """Trapped infant puppy/kitten in hazard should evaluate to HIGH or higher."""
        level, score, reasons = calculate_risk('MODERATE_INJURY', ['severe_malnutrition'], True, 'infant')
        self.assertIn(level, ['HIGH', 'CRITICAL'])

    def test_medium_skin_mange(self):
        """Severe skin mange on adult stray should evaluate to MEDIUM priority."""
        level, score, reasons = calculate_risk('SKIN_OR_SICK', ['skin_mange'], False, 'adult')
        self.assertEqual(level, 'MEDIUM')
        self.assertIn(score, [3, 4, 5, 6])

    def test_low_healthy_stray(self):
        """Healthy stray without injuries should be LOW priority."""
        level, score, reasons = calculate_risk('HEALTHY_STRAY', [], False, 'adult')
        self.assertEqual(level, 'LOW')
        self.assertLessEqual(score, 2)

if __name__ == '__main__':
    unittest.main()
