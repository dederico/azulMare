TC = """
Este documento contiene información sobre la Tarjeta de la Secretaría del Bienestar, trámite correspondiente al gobierno federal

Pregunta: ¿Cuál es la papelería necesaria para la tarjeta del bienestar?
Respuesta:
Acudir personalmente con la siguiente papelería:
Acta de nacimiento
Curp
Comprobante de domicilio
Identificación oficial
Teléfonos de contacto.
Documentos legibles
Recomendaciones: 
Revisar el calendario con los días para cada letra del primer apellido paterno.
Acudir a los módulos del municipio donde radican.
Pregunta: ¿Cuál es el contacto para la tarjeta del bienestar?
Respuesta: Dudas al teléfono 800 639 42 64
Pregunta: Cuál es el módulo de la Secretaría del Bienestar en San Pedro?
Respuesta: Dirección: Cobalto SN Col. San Pedro 400 entre Uranio y Platino
"""

async def get_bienestar():
    """Obtener información sobre la Tarjeta de la Secretaría del Bienestar, trámite correspondiente al gobierno federal.

    Returns:
        string: Información sobre la Tarjeta de la Secretaría del Bienestar, trámite correspondiente al gobierno federal.
    """
    return TC