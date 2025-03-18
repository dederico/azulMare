TC = """
Este documento contiene la información de los servicios de la dirección de Salud Pública del municipio
Pregunta: ¿Cuáles son los servicios de la Dirección de Salud Pública del municipio?
Respuesta: los servicios brindados por la dirección de Salud Pública son los siguientes:
Fumigación
Descripción:
Fumigación en avenidas contra enfermedades como Dengue, Zika y Chikungunya.
Se programa para el espacio público con el objetivo de prevenir enfermedades transmitidas por el mosquito Aedes aegypti.
Restricciones: No aplica para interiores de domicilios ni para parques.
Tiempo de compromiso: 15 días.
Insalubridad
Descripción:
Se atienden quejas de insalubridad de ciudadanos en espacios públicos.
Restricciones: No aplica para exterminio de roedores ni para terrenos baldíos.
Tiempo de compromiso: 18 días.
Ruta de la Salud
Descripción:
Inscripción al programa "Ruta de la Salud".
Se realiza un estudio socioeconómico por enlaces comunitarios y se evalúa desde Salud Pública la posibilidad de ingresar al programa.
Restricciones: No aplica para traslados inmediatos ni urgencias.
Tiempo de compromiso: 7 días.
"""

async def get_salud_publica():
    """Obtener Información de los servicios que ofrece la dirección de Salud Pública en caso de ser necesario.

    Returns:
        string: Informacion servicios que ofrece la dirección de Salud Pública.
    """
    return TC