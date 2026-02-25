


TC = """
Este documento contiene información sobre el Consultorio Médico Canteras del municipio de San Pedro Garza García

Pregunta: ¿Cuál es la dirección del Consultorio Médico Canteras?
Respuesta: Enrique H. Herrera 824 Col. Canteras

Pregunta: ¿Se necesita hacer cita para consultar en el Consultorio Médico Canteras?
Respuesta: No se requiere previa cita

Pregunta: ¿Cuál es el horario del Consultorio Médico Canteras?
Respuesta: El Centro Médico Canteras abre a partir del 9 de julio con los siguientes horarios:
Lunes a viernes de 9:00 am a 5:00 pm
Sábado 9:00 am a 2:00 pm

Pregunta: ¿Qué servicios tienen en el Consultorio Médico Canteras?
Respuesta:
- Consulta médica gratuita
- Farmacia (medicamento cuadro básico, posterior a consulta)
- Aplicación de inyecciones
- Toma de signos vitales
- Estudios de laboratorio
    - Biometría hemática completa
    - Examen General de orina
    - ⁠Glucosa sérica
    - ⁠⁠Antigeno Prostatico
    - ⁠Perfil bioquímico 16 elementos
    - ⁠⁠Prueba de embarazo en sangre
    - ⁠⁠Reacciones febriles
⁠    - ⁠Coproparasitoscopico unico
⁠    - ⁠Perfil de lípidos
⁠    - ⁠Química sanguínea 3 (7 elementos)
⁠    - ⁠Coprológico
⁠    - ⁠Perfil prenatal 1
    - Urocultivo⁠⁠
    - Hemoglobina glucosilada

"""

async def get_consultorio_medio_canteras():
    """Obtener información sobre el Consultorio Médico Canteras del municipio de San Pedro Garza García en caso de ser necesario.

    Returns:
        string: Informacion información sobre el Consultorio Médico Canteras.
    """
    return TC