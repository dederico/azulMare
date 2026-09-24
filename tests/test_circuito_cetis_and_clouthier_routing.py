import unittest
from pathlib import Path

from app.services.functions.implementations.get_circuito_cetis import get_circuito_cetis
from app.services.functions.implementations.get_urls import get_urls


class CircuitoCetisAndClouthierRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_circuito_cetis_exposes_stops_schedules_and_requirements(self):
        content = await get_circuito_cetis()

        self.assertIn("Parque Los Rosales", content)
        self.assertIn("Entrada 1: 06:30 a. m.", content)
        self.assertIn("Salida 2: 08:40 p. m.", content)
        self.assertIn("portar uniforme oficial", content)

    async def test_urls_exposes_clouthier_tennis_reservation_link(self):
        content = await get_urls()

        self.assertIn("Canchas de Tenis Parque Clouthier", content)
        self.assertIn("https://playtomic.io/parque-clouthier/", content)

    def test_circuito_cetis_is_registered_as_a_tool(self):
        registry_source = Path("app/services/functions/function_registry.py").read_text()

        self.assertIn(
            "from .implementations.get_circuito_cetis import get_circuito_cetis",
            registry_source,
        )
        self.assertIn("    get_circuito_cetis,", registry_source)

    def test_prompt_routes_both_queries_to_the_correct_tools(self):
        prompt = Path("prompty.py").read_text()

        self.assertIn("canchas de tenis del Parque Clouthier", prompt)
        self.assertIn("OBLIGATORIO utilizar 'get_urls()'", prompt)
        self.assertIn("Para reservaciones de canchas NO utilices", prompt)
        self.assertIn("Circuito CETIS 66", prompt)
        self.assertIn("utiliza 'get_circuito_cetis()'", prompt)
        self.assertIn("otros circuitos de transporte distintos", prompt)

    def test_runtime_prompt_reinforces_both_routes(self):
        routes_source = Path("app/api/original_routes.py").read_text()

        self.assertIn("ENRUTAMIENTO DE INFORMACIÓN MUNICIPAL", routes_source)
        self.assertIn("llama obligatoriamente", routes_source)
        self.assertIn("a get_urls()", routes_source)
        self.assertIn("llama a get_circuito_cetis()", routes_source)


if __name__ == "__main__":
    unittest.main()
