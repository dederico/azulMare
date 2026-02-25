TC = """
Este documento contiene información sobre horarios y servicios brindados en el Miércoles Ciudadano

Pregunta: ¿Cada cuándo se realiza el Miércoles Ciudadano?
Respuesta: Cada 15 días

Pregunta: ¿En qué horario se realiza el Miércoles Ciudadano?
Respuesta: 11:30 am a 1:30 pm

Pregunta: ¿En dónde se realiza el Miércoles Ciudadano?
Respuesta: Bajos de Presidencia Municipal San Pedro Garza García, Juárez y Libertad S/N, Centro, 66238 San Pedro Garza García, N.L.

Pregunta: ¿Dónde puedo adoptar o recibir árboles?
Respuesta: En el Miércoles Ciudadano se realizan entregas de árboles endémicos y frutales.

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
    """Obtener Información sobre sobre horarios y servicios brindados en el Miércoles Ciudadano, en caso de ser necesario.

    Returns:
        string: Información sobre sobre horarios y servicios brindados en el Miércoles Ciudadano, en el municipio de San Pedro Garza García.
    """
    return TC