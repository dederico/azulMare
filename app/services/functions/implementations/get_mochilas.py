TC = """
Este documento contiene información sobre el registro para la impartición de mochilas escolares municipales de San Pedro Garza García

Pregunta: ¿Cuáles son los requisitos para la entrega de mochilas escolares?
Respuesta:
Vivir en San Pedro
CURP
Comprobante de domicilio
Comprobante de estudios reciente
En caso de ser alumno mayor de edad presentar copia de INE
En caso de ser alumno menor de edad presentar copia de INE de padre o tutor

Pregunta: ¿Qué edades son las que aplican para la entrega de mochilas escolares?
Respuesta: Aplican estudiantes de nivel secundaria, preparatoria y universidad

Pregunta: ¿Dónde me puedo registrar para obtener una mochila escolar?
Respuesta: Puedes registrarte en la siguiente liga: https://docs.google.com/forms/d/e/1FAIpQLSeHsLQtmU3WiKVtpyZiPlg41pQ7waHdDt80246WwA60N__ZiQ/viewform?fbclid=PAQ0xDSwLTpnJleHRuA2FlbQIxMQABp8o3cdhwZp2fi5d2gHLtDv0pQKRkOhE4GU7q0Qs_VaD3P6MH3usiOF3e5sRm_aem_4N7YWtgkzNvFBOmS3t7s0w

"""

async def get_mochilas():
    """Este documento contiene información sobre el registro para la impartición de mochilas escolares municipales de San Pedro Garza García.

    Returns:
        string: Información sobre el registro para la impartición de mochilas escolares municipales de San Pedro Garza García.
    """
    return TC