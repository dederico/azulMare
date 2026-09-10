import asyncio

from app.services.functions.implementations.get_info_general_colegio_militarizado import (
    get_info_general_colegio_militarizado,
)
from app.services.functions.implementations.get_uniformes_colegio_militarizado import (
    get_uniformes_colegio_militarizado,
)


def test_general_information_contains_current_institutional_facts():
    content = asyncio.run(get_info_general_colegio_militarizado())

    assert "Es pública" in content
    assert "Ernesto Alfonso Robledo Leal" in content
    assert "inscripción y las mensualidades son gratuitas" in content
    assert "NL Aprende 2025" in content
    assert "Sistema de Educación Dual" in content


def test_uniform_information_distinguishes_free_issue_from_replacements():
    content = asyncio.run(get_uniformes_colegio_militarizado())

    assert "dotación institucional" in content
    assert "son gratuitos" in content
    assert "compras adicionales o reposiciones" in content
