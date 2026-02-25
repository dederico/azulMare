TC = """
Este documento contiene información sobre el programa de equipamiento de vivienda de la Dirección de Bienestar Social del Municipio de San Pedro Garza García

Pregunta: ¿Cuáles son los requisitos para equipamiento de vivienda?
Respuesta:
Ser habitante del municipio de San Pedro Garza García
Ser propietario del predio
Copia del INE
Copia de CURP
Copia de comprobante de domicilio (agua, luz o gas)
Copia estado de cuenta del predial
Pago del 5% del valor del apoyo recibido

Pregunta: ¿Cómo puedo inscribirme al proyecto de equipamiento de vivienda?
Respuesta:
Por medio de los Enlaces Comunitarios
Oficinas de Dirección de Bienestar Social: Doña María Cantú Treviño 329, Col. La Leona
Teléfono: 8184004594
WhatsApp: 8120309382

Pregunta: ¿Qué materiales puedo adquirir de equipamiento de vivienda?
Respuesta:
Kit de Pintura
Kit de Impermeabilizantes
Kit de Sanitario y Lavabo

"""

async def get_equipamiento_vivienda():
    """Obtener información sobre el programa de equipamiento de vivienda en caso de ser necesario.

    Returns:
        string: Informacion sobre el programa de equipamiento de vivienda.
    """
    return TC