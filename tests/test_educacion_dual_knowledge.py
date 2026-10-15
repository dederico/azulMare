import asyncio

from app.services.functions.function_manager import FunctionManager
from app.services.functions.function_registry import registered_functions
from app.services.functions.implementations.get_educacion_dual import (
    get_educacion_dual,
)


def test_educacion_dual_content_preserves_scope_and_safeguards():
    content = asyncio.run(get_educacion_dual())

    assert "Logística" in content
    assert "Robótica y Automatización" in content
    assert "Inteligencia Artificial" in content
    assert "no garantiza automáticamente un empleo" in content
    assert "seguro facultativo" in content
    assert "Coordinación de Educación Dual" in content


def test_educacion_dual_is_registered_and_mapped_in_runtime_prompt():
    names = [function.__name__ for function in registered_functions]
    assert names.count("get_educacion_dual") == 1

    definitions = FunctionManager(registered_functions).get_function_definition()
    tool = next(
        item for item in definitions
        if item["function"]["name"] == "get_educacion_dual"
    )
    assert tool["function"]["parameters"] == {
        "type": "object",
        "properties": {},
        "required": [],
    }
