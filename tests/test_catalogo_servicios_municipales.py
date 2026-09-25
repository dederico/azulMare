import unittest
from pathlib import Path

from app.services.functions.implementations.get_catalogo_servicios_municipales import (
    get_catalogo_servicios_municipales,
)


class CatalogoServiciosMunicipalesTests(unittest.IsolatedAsyncioTestCase):
    async def test_cacharros_returns_service_area_and_phone(self):
        result = await get_catalogo_servicios_municipales("recolección de cacharros")

        self.assertIn("Acción o servicio: Recolección de cacharros", result)
        self.assertIn("Área responsable: Dirección de Arbolado, Limpia y Cultura Ambiental", result)
        self.assertIn("Teléfono: 81 8400 4400 extensión 4208", result)
        self.assertNotIn("CIAC", result)
        self.assertNotIn("funcionario", result.lower())
        self.assertNotIn("Recolección de ramas", result)
        self.assertNotIn("Recolección de basura doméstica", result)

    async def test_synonym_finds_cacharros(self):
        result = await get_catalogo_servicios_municipales("quiero retirar muebles viejos")

        self.assertIn("Acción o servicio: Recolección de cacharros", result)
        self.assertIn("extensión 4208", result)

    async def test_unknown_service_forbids_directory_inference(self):
        result = await get_catalogo_servicios_municipales("servicio completamente desconocido")

        self.assertIn("No existe una entrada verificada", result)
        self.assertIn("No infieras el área ni el teléfono", result)

    async def test_baches_returns_pavement_contact(self):
        result = await get_catalogo_servicios_municipales("bache en la calle")

        self.assertIn("Dirección de Pavimentación", result)
        self.assertIn("extensión 2749", result)

    def test_tool_is_registered(self):
        registry = Path("app/services/functions/function_registry.py").read_text()

        self.assertIn(
            "from .implementations.get_catalogo_servicios_municipales import get_catalogo_servicios_municipales",
            registry,
        )
        self.assertIn("    get_catalogo_servicios_municipales,", registry)

    def test_prompt_and_runtime_route_service_contacts_to_catalog(self):
        prompt = Path("prompty.py").read_text()
        routes = Path("app/api/original_routes.py").read_text()

        self.assertIn("REGLA DE CONTACTOS DE SERVICIOS", prompt)
        self.assertIn("get_catalogo_servicios_municipales(servicio)", prompt)
        self.assertIn("CONTACTOS DE SERVICIOS MUNICIPALES", routes)
        self.assertIn("Nunca deduzcas", routes)


if __name__ == "__main__":
    unittest.main()
