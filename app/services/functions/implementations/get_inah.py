TC = """
Este documento contiene información sobre el Instituto Nacional de
Antropología e Historia
Pregunta: ¿Cuál es la dirección y contacto del INAH?
Respuesta:
Domicilio: Rafael J. Verger s/n, Colonia Obispado, 64060 Monterrey, N.L.
Teléfonos: 8183339588 y 8183339751
Protección y Conservación de Patrimonio Cultural
"""

async def get_inah():
    """Obtener informacion de Instituto Nacional de Antropología e Historia en caso de ser necesario.

    Returns:
        string: informacion de Instituto Nacional de Antropología e Historia.
    """
    return TC