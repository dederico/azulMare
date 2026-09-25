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

    def test_real_andres_street_typo_is_uniquely_normalized(self):
        self.assertEqual(
            extract_catalog_location("General Garcia Naranjo", {}),
            {"selection5": "General Francisco Naranjo"},
        )

    def test_short_ambiguous_street_fragment_is_not_fuzzy_guessed(self):
        self.assertEqual(extract_catalog_location("Garcia Naranjo", {}), {})

    def test_exact_captured_conversation_reaches_one_confirmation(self):
        fields = {}
        session = {"unsolicited_location_fragments": 0}

        for message in ("General Garcia Naranjo", "En Palo Blanco"):
            location = extract_catalog_location(message, fields)
            self.assertTrue(location)
            fields.update(location)
            session["unsolicited_location_fragments"] += 1

        fields.update(
            {
                "selection1": "982",
                "selection4": "No hay luminarias",
            }
        )
        self.assertTrue(should_request_intake_confirmation(fields, session))
        self.assertEqual(
            build_intake_confirmation(fields),
            "Entiendo que deseas levantar un reporte porque No hay luminarias, "
            "en la calle General Francisco Naranjo, colonia Palo Blanco. ¿Es correcto?",
        )

    def test_ambiguous_palo_blanco_is_not_guessed_without_context(self):
        self.assertEqual(extract_catalog_location("Palo Blanco", {}), {})
        self.assertEqual(
            extract_catalog_location("Colonia Palo Blanco", {}),
            {"selection7": "Palo Blanco"},
        )

    def test_explicit_colony_never_falls_through_to_street_catalog(self):
        existing = {
            "selection5": "Francisco Siller y Agustín Siller",
            "selection7": "",
        }

        self.assertEqual(
            extract_catalog_location(
                "Col. General Lázaro Garza Ayala",
                existing,
            ),
            {"selection7": "Lázaro Garza Ayala"},
        )
        self.assertEqual(
            extract_catalog_location(
                "Colonia General. Lazaro Garza Ayala",
                existing,
            ),
            {"selection7": "Lázaro Garza Ayala"},
        )

    def test_requested_colony_uses_only_colony_catalog(self):
        existing = {
            "selection5": "Francisco Siller y Agustín Siller",
            "selection7": "",
        }

        self.assertEqual(
            extract_catalog_location(
                "General Lázaro Garza Ayala",
                existing,
                expected_field="selection7",
            ),
            {"selection7": "Lázaro Garza Ayala"},
        )
        # Santa Catarina is also the name of a local street. When SAM asked
        # for a colony it must not be accepted by crossing into that catalog.
        self.assertEqual(
            extract_catalog_location(
                "Santa Catarina",
                existing,
                expected_field="selection7",
            ),
            {},
        )

    def test_requested_street_uses_only_street_catalog(self):
        self.assertEqual(
            extract_catalog_location(
                "General Garcia Naranjo",
                {},
                expected_field="selection5",
            ),
            {"selection5": "General Francisco Naranjo"},
        )

    def test_full_address_splits_inline_colony_without_losing_landmark(self):
        self.assertEqual(
            extract_catalog_location(
                "Francisco Siller y Agustín Siller Frente al parque hormiguitas "
                "Col. General Lázaro Garza Ayala.",
                {"selection5": "", "selection7": ""},
                expected_field="selection5",
            ),
            {
                "selection5": (
                    "Francisco Siller y Agustín Siller Frente al parque hormiguitas"
                ),
                "selection7": "Lázaro Garza Ayala",
            },
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
