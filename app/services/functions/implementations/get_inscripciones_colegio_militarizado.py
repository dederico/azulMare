TC = """
Este documento contiene información sobre inscripciones al Colegio Ciudadano de Excelencia y Disciplina en Nuevo León para el ciclo de ingreso de agosto de 2026.

¿Cuándo ocurre la inscripción?
Las inscripciones de nuevo ingreso se realizaron del 18 al 21 de agosto de 2026, de 08:00 a 12:00 horas.

¿Las inscripciones de nuevo ingreso siguen abiertas?
No. El periodo de inscripción de nuevo ingreso de agosto de 2026 ya concluyó.

¿Cómo sé si fui asignado?
La carta de resultado se descarga con número de registro y contraseña. Ahí se indica el plantel asignado y las instrucciones para inscripción.

¿Qué se necesita para la inscripción definitiva?
Certificado de secundaria.
Además, se deben cumplir los requisitos particulares del plantel asignado.

¿Qué pasa si no confirmo mi lugar?
Los lugares no confirmados pueden reasignarse.

¿Qué debo considerar?
La inscripción corresponde al ingreso para iniciar clases en agosto de 2026.
Es importante revisar cuidadosamente la carta de resultado y seguir las instrucciones del plantel asignado.

ACLARACIÓN IMPORTANTE
- Estas fechas corresponden a la inscripción general de nuevo ingreso al Colegio.
- No son las fechas de inscripción al programa CECATI/FORJA.
- Si preguntan específicamente por CECATI o FORJA, debe consultarse la función get_cecati_forja.
"""


async def get_inscripciones_colegio_militarizado():
    """Obtener información sobre inscripciones al Colegio Ciudadano de Excelencia y Disciplina en Nuevo León.

    Returns:
        string: Información de inscripción posterior a la asignación 2026.
    """
    return TC
