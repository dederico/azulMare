
TC = """
Este documento contiene información sobre el Instituto de Control Vehicular, el cual es de competencia del gobierno estatal

El instituto tambien es conocido como ICV NL

Pregunta: ¿Dónde puedo renovar mi licencia de conducir?
Respuesta: Las renovaciones de licencias de conducir son competencia del gobierno estatal, puede realizarla en el Instituto de Control Vehicular o mediante la página web: https://www.icvnl.gob.mx/Licencia
(Es lo mismo: -liga, -pagina web, -link, -pagina, -url)
Pregunta: ¿Dónde se ubica el Instituto de Control Vehicular?
Respuesta: Punto Valle, Río Missouri 555, Valle de Santa Engracia, 66220 San Pedro Garza García, N.L.
"""

async def get_icvnl():
    """Obtener Información información sobre el Instituto de Control Vehicular, el cual es de competencia del gobierno estatal en caso de ser necesario.


    Returns:
        string: Información información sobre el Instituto de Control Vehicular, el cual es de competencia del gobierno estatal.
    """
    return TC