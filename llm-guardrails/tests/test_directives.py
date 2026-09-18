import unittest

from app.directives import DirectiveValidationError, validate_directive_interpretations


class DirectiveValidationTests(unittest.TestCase):
    def test_accepts_all_supported_directive_shapes(self):
        raw = {
            "directives": [
                {
                    "note_index": 0,
                    "applies": True,
                    "directive_type": "solar_reduction",
                    "structured_adjustment": {"hours": [13, 14], "factor": 0.2},
                    "explanation": "Only 20% of solar remains.",
                },
                {
                    "note_index": 1,
                    "applies": True,
                    "directive_type": "max_grid_window",
                    "structured_adjustment": {"hours": [18, 19], "max_grid_kwh": 100},
                    "explanation": "Grid is capped in the evening.",
                },
                {
                    "note_index": 2,
                    "applies": False,
                    "directive_type": "no_op",
                    "structured_adjustment": None,
                    "explanation": "The note does not affect energy use.",
                },
            ]
        }

        directives = validate_directive_interpretations(
            raw, note_count=3, battery_capacity_kwh=500
        )

        self.assertEqual(directives[0]["structured_adjustment"]["factor"], 0.2)
        self.assertEqual(directives[1]["structured_adjustment"]["max_grid_kwh"], 100.0)
        self.assertIsNone(directives[2]["structured_adjustment"])

    def test_rejects_out_of_order_notes(self):
        raw = [
            {
                "note_index": 1,
                "applies": False,
                "directive_type": "no_op",
                "structured_adjustment": None,
                "explanation": "Irrelevant.",
            }
        ]

        with self.assertRaises(DirectiveValidationError):
            validate_directive_interpretations(
                raw, note_count=1, battery_capacity_kwh=500
            )

    def test_rejects_invalid_hour_windows(self):
        raw = [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "no_charge_window",
                "structured_adjustment": {"hours": [14, 13, 13]},
                "explanation": "No charging.",
            }
        ]

        with self.assertRaises(DirectiveValidationError):
            validate_directive_interpretations(
                raw, note_count=1, battery_capacity_kwh=500
            )

    def test_rejects_bad_no_op_semantics(self):
        raw = [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "no_op",
                "structured_adjustment": None,
                "explanation": "Irrelevant.",
            }
        ]

        with self.assertRaises(DirectiveValidationError):
            validate_directive_interpretations(
                raw, note_count=1, battery_capacity_kwh=500
            )

    def test_rejects_reserve_above_capacity(self):
        raw = [
            {
                "note_index": 0,
                "applies": True,
                "directive_type": "minimum_battery_reserve",
                "structured_adjustment": {
                    "hours": [18, 19, 20],
                    "minimum_energy_kwh": 501,
                },
                "explanation": "Keep a large reserve.",
            }
        ]

        with self.assertRaises(DirectiveValidationError):
            validate_directive_interpretations(
                raw, note_count=1, battery_capacity_kwh=500
            )


if __name__ == "__main__":
    unittest.main()
