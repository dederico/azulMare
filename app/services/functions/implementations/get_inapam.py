TC = """
Este documento contiene información sobre la tarjeta INAPAM, trámite correspondiente al gobierno federal

Pregunta: ¿Dónde puedo tramitar mi tarjeta INAPAM?
Respuesta: Alcaldía Poniente. Platino cruz con Cobalto, colonia San Pedro 400

Pregunta: ¿Cuál es el teléfono de contacto para la tarjeta INAPAM?
Contacto: 8181244998 y 8181244999

Pregunta: Cuál es el horario de atención para la tarjeta INAPAM?
Respuesta: Lunes a Viernes de 8:30am a 2:00pm

Pregunta: ¿Cuáles son los requisitos para la tarjeta INAPAM?
Respuesta:
Copia del CURP
Copia de Credencial de Elector (INE)
Copia de Acta de Nacimiento
Dos fotografías tamaño infantil a color o blanco y negro con fondo blanco (sin lentes, ni gorra)
"""

def get_inapam():
    """Obtener Información de los requisistos para tramitar la tarjeta INAPAM en caso de ser necesario.

    Returns:
        string: Informacion requisistos para tramitar tarjeta de INAPAM.
    """
    return TC