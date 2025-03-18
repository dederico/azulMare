TC = """
Este documento contiene información sobre horarios y servicios brindados en el Miércoles Ciudadano

Pregunta: ¿Cuándo se realizará el Miércoles Ciudadano?
Respuesta: 12 y 26 de febrero

Pregunta: ¿En qué horario se realiza el Miércoles Ciudadano?
Respuesta: 11:30 am a 1:30 pm

Pregunta: ¿En dónde se realiza el Miércoles Ciudadano?
Respuesta: Bajos de Presidencia Municipal San Pedro Garza García, Juárez y Libertad S/N, Centro, 66238 San Pedro Garza García, N.L.

Pregunta: ¿Qué servicios brindan en el Miércoles Ciudadano?
Respuesta:
Productos a bajo costo
Consulta médica
Vacunación
Asistencia social
Corte de cabello
Bolsa de trabajo
"""

async def get_miercoles_ciudadano():
    """Obtener Información sobre las oficialías del registro civil que se encuentran en el municipio de San Pedro Garza García en caso de ser necesario.

    Returns:
        string: Información sobre las oficialías del registro civil que se encuentran en el municipio de San Pedro Garza García.
    """
    return TC