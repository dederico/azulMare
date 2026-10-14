import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.report_summary import (
    build_report_summary_repair_prompt,
    repair_report_summary_with_model,
)


class ReportSummaryRepairTests(unittest.IsolatedAsyncioTestCase):
    def test_prompt_separates_evidence_and_location(self):
        prompt = build_report_summary_repair_prompt(
            citizen_messages=[
                "Quiero reportar un señalamiento vial vandalizado en Calzada Mauricio",
            ],
            current_summary="Señalamiento vandalizado en Calzada Mauricio",
            street="Calzada Mauricio",
            number="500",
            neighborhood="Del Valle",
        )

        self.assertIn("<EVIDENCIA_CIUDADANA>", prompt)
        self.assertIn("Ubicación que debes excluir", prompt)
        self.assertIn("máximo 35 palabras", prompt)

    async def test_model_returns_only_repaired_sentence(self):
        client = MagicMock()
        client.responses.create.return_value = SimpleNamespace(
            output_text=(
                "“El señalamiento vial está vandalizado con grafiti y "
                "calcomanías y se solicita su limpieza.”"
            )
        )

        result = await repair_report_summary_with_model(
            client,
            citizen_messages=[
                "Quiero reportar un señalamiento vandalizado y solicito limpieza",
            ],
            current_summary="Reporte en Calzada Mauricio 500",
            street="Calzada Mauricio",
            number="500",
            neighborhood="Del Valle",
        )

        self.assertEqual(
            result,
            "El señalamiento vial está vandalizado con grafiti y calcomanías y se solicita su limpieza.",
        )
        client.responses.create.assert_called_once()

    async def test_model_is_not_called_without_citizen_evidence(self):
        client = MagicMock()

        result = await repair_report_summary_with_model(
            client,
            citizen_messages=[],
            current_summary="Calzada Mauricio",
            street="Calzada Mauricio",
            number="500",
            neighborhood="Del Valle",
        )

        self.assertIsNone(result)
        client.responses.create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
