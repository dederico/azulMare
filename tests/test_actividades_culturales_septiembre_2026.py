import unittest

from app.services.functions.implementations.get_actividades_culturales_septiembre_2026 import (
    get_actividades_culturales_septiembre_2026,
)


class ActividadesCulturalesSeptiembreTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_the_september_2026_agenda(self):
        content = await get_actividades_culturales_septiembre_2026()
        normalized = content.lower()

        self.assertIn("septiembre de 2026", normalized)
        self.assertIn("Lotería atmosférica con OCCAMM", content)
        self.assertIn("arte al parque", normalized)
        self.assertIn("parque mississippi", normalized)
        self.assertIn("parque el capitán", normalized)
        self.assertIn("parque bosques del valle", normalized)
        self.assertIn("parque clouthier", normalized)
        self.assertIn("parque mirador garza ayala", normalized)
        self.assertIn("parque jardines del valle", normalized)

    async def test_preserves_unspecified_locations_instead_of_inventing_them(self):
        content = await get_actividades_culturales_septiembre_2026()

        self.assertIn("lugar no especificado", content.lower())
        self.assertIn("no inventes parque, dirección o punto de reunión", content)


if __name__ == "__main__":
    unittest.main()
