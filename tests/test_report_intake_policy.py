import unittest

from app.services.report_intake_policy import (
    build_intake_confirmation,
    classify_intake_confirmation,
    extract_catalog_location,
    next_question_after_intake_confirmation,
    should_request_intake_confirmation,
)


class ReportIntakePolicyTests(unittest.TestCase):
    def test_andres_fragments_use_official_catalogs(self):
        fields = {}
        fields.update(extract_catalog_location("General Francisco Naranjo", fields))
        self.assertEqual(fields["selection5"], "General Francisco Naranjo")

        fields.update(extract_catalog_location("En Palo blanco", fields))
        self.assertEqual(fields["selection7"], "Palo Blanco")

    def test_ambiguous_palo_blanco_is_not_guessed_without_context(self):
        self.assertEqual(extract_catalog_location("Palo Blanco", {}), {})
        self.assertEqual(
            extract_catalog_location("Colonia Palo Blanco", {}),
            {"selection7": "Palo Blanco"},
        )

    def test_confirmation_requires_problem_street_colony_and_catalog(self):
        fields = {
            "selection1": "982",
            "selection4": "no hay luminarias",
            "selection5": "General Francisco Naranjo",
            "selection7": "Palo Blanco",
        }
        self.assertEqual(
            build_intake_confirmation(fields),
            "Entiendo que deseas levantar un reporte porque no hay luminarias, "
            "en la calle General Francisco Naranjo, colonia Palo Blanco. ¿Es correcto?",
        )
        self.assertIsNone(build_intake_confirmation({"selection4": "no hay luminarias"}))

    def test_confirmation_understands_natural_yes_and_no(self):
        for answer in ("Sí", "Simón", "Así es", "correcto"):
            self.assertEqual(classify_intake_confirmation(answer), "CONFIRMED")
        for answer in ("No", "Nel", "No es correcto", "está mal"):
            self.assertEqual(classify_intake_confirmation(answer), "REJECTED")
        self.assertEqual(classify_intake_confirmation("General Naranjo"), "UNKNOWN")

    def test_confirmation_continues_at_first_missing_field(self):
        self.assertIn("número", next_question_after_intake_confirmation({}))
        self.assertIn(
            "imagen",
            next_question_after_intake_confirmation({"selection6": "368"}),
        )

    def test_natural_wizard_does_not_activate_fragment_confirmation(self):
        fields = {
            "selection1": "982",
            "selection4": "no hay luminarias",
            "selection5": "General Francisco Naranjo",
            "selection7": "Palo Blanco",
        }
        self.assertFalse(should_request_intake_confirmation(fields, {}))
        self.assertFalse(
            should_request_intake_confirmation(
                fields,
                {"unsolicited_location_fragments": 2, "image_prompted": True},
            )
        )
        self.assertTrue(
            should_request_intake_confirmation(
                fields,
                {"unsolicited_location_fragments": 2},
            )
        )


if __name__ == "__main__":
    unittest.main()
