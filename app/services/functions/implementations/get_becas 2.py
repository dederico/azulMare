TC = """
Este documento contiene información sobre los requisitos para el trámite de becas por parte del municipio de San Pedro Garza García

Pregunta: ¿Cuáles son los requisitos para el trámite de beca municipal?
Respuesta:
Vivir en el municipio de San Pedro Garza García, N.L.
Tener todas las materias aprobadas al momento de solicitar la beca.
Documentos para iniciar su trámite:
Boleta de calificaciones del último grado de estudios cursado (sin materias pendientes)
Comprobante a pagar en la escuela del alumno (Ficha de pago)
Credencial de elector vigente de ambos padres o tutor, y del alumno si es mayor de edad (las identificaciones por ambos lados)
Comprobante de domicilio no mayor a 3 meses (puede ser de luz, agua, gas o teléfono)
Comprobante de ingresos de padres, y del alumno solamente si este se encuentra trabajando
Descargar, leer y firmar la “Carta Compromiso de Colaboración”
Fotografía del Alumno fuera de la fachada de su domicilio
Nota: Realizar la solicitud a nombre del alumno.

Pregunta: ¿Cuál es la dirección de la oficina de becas?
Respuesta: María Cantú 329, entre Blvd. Díaz Ordaz y Lucio Blanco, Col. La Leona, San Pedro Garza García, N.L.

Pregunta: ¿Cuál es el teléfono de la oficina de becas?
Respuesta:
Teléfonos: 8186765364, 8184004542 y 8184782083
WhatsApp: 8110603535
Correo: becaseducacion@sanpedro.gob.mx
"""
async def get_becas():
    """Obtener Información de los requisistos para tramitar el apoyo alimentario en caso de ser necesario.

    Returns:
        string: Informacion requisistos para tramitar apoyo alimentario.
    """
    return TC