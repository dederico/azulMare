


TC = """
Este documento contiene información sobre la Capilla de Doña Mónica Rodriguez ubicada en San Pedro Garza García

Pregunta: ¿Cuál es la dirección de la Capilla de Doña Mónica Rodriguez?
Respuesta: Callejón de Capellanía 600, Los Callejones, San Pedro Garza García

Pregunta: ¿Cuál es el horario para ir a la Capilla de Doña Mónica Rodriguez?
Respuesta: Los horarios y citas se realizan bajo programación, puedes enviar un correo a zaida.martinez@sanpedro.gob.mx

Pregunta: ¿Cuál es el contacto para un permiso en la Capilla de Doña Mónica Rodriguez?
Respuesta: Puedes enviar correo a zaida.martinez@sanpedro.gob.mx
"""

async def get_info_capilla():
    """Obtener informacion de la Capilla de Doña Mónica Rodriguez en caso de ser necesario.

    Returns:
        string: informacion de la Capilla de Doña Mónica Rodriguez.
    """
    return TC