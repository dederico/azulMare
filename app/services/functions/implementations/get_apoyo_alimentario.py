TC = """
Este documento contiene información sobre la tarjeta de apoyo alimentario llamada Tarjeta Azul.

Descripción Tarjeta Azul: 
El trámite de Tarjeta de Apoyo Alimentario es un servicio destinado a brindar asistencia a personas en situación de vulnerabilidad alimentaria. A través de este programa, los beneficiarios pueden recibir apoyo en forma de tarjeta de despensa o despensa física, según corresponda a sus necesidades y condiciones.

Pregunta: ¿Cuándo van a depositar el dinero de la Tarjeta de Apoyo Alimentario / Tarjeta Azul / One Card / Tarjeta de Bonos?
Respuesta: El depósito quedará el día 28 de febrero, en ese pago también se integrarán los depósitos de las quincenas anteriores. Cualquier duda o aclaración pueden acudir a las oficinas de Asistencia Social ubicadas en Platino y Cobalto s/n en la Colonia San Pedro 400 o bien comunicarte a los teléfonos 8110524225, 8110524267 y 8110524287.

Pregunta: ¿Con quién me puedo comunicar para tramitar mi tarjeta?
Respuesta: Para trámites por primera vez puedes comunicarte a partir del mes de Febrero al teléfono 8110524225, 8110524267 y 8110524287.

Pregunta: ¿Cuáles son los requisitos para la reactivación de la tarjeta de apoyo alimentario?
Respuesta:
INE vigente de San Pedro. 
Comprobante de domicilio de San Pedro. 
CURP
Acta de nacimiento. 
Deberá acudir el beneficiario activo.
"""

async def get_apoyo_alimentario():
    """Obtener Información de los requisistos para tramitar el apoyo alimentario en caso de ser necesario.

    Returns:
        string: Informacion requisistos para tramitar apoyo alimentario.
    """
    return TC