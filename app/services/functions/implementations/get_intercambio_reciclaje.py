TC = """
Este documento contiene información sobre el intercambio de reciclaje realizado por la Secretaría de Servicios Públicos y Mantenimiento de la Ciudad del municipio de San Pedro Garza García

Pregunta: ¿Qué puedo canjear en el intercambio de reciclaje?
Respuesta:

Podrás canjear tu material por: 
Plástico (PET, tapitas, aluminio) 👉🏻 Productos de Limpieza 
Vidrio 👉🏻 Utensilios de cocina, vasos, tequileros, vaporeras, etc. 
Cartón 👉🏻 Paquete de hojas 

El Instituto de Bienestar Animal estará aplicando: 

Vacunación antirrábica 
Desparasitación interna parásitos 
Desparasitación externa, garrapatas y pulgas

Pregunta: ¿Dónde será el próximo intercambio de reciclaje?
Respuesta: Auditorio San Pedro en modalidad Drive Thru

Pregunta: ¿Cuándo será el próximo intercambio de reciclaje?
Respuesta: Sábado 11 de octubre

Pregunta: ¿Cuál es el horario del intercambio de reciclaje?
Respuesta: 9:00 am a 12:00 pm
"""

async def get_intercambio_reciclaje():
    """Obtener Información del intercambio de reciclaje realizado por la Secretaría de Servicios Públicos y Mantenimiento de la Ciudad del municipio de San Pedro Garza García, en caso de ser necesario.

    Returns:
        string: Informacion del intercambio de reciclaje realizado por la Secretaría de Servicios Públicos y Mantenimiento de la Ciudad del municipio de San Pedro Garza García.
    """
    return TC