TC = """
Este documento contiene información sobre los requisitos para tramitar la licencia de conducir de chofer
Pregunta: ¿Cómo puedo realizar el trámite de licencia de conducir de chofer?
Respuesta:Todos los trámites se realizan de forma presencial en el Instituto de Formación y Perfeccionamiento Policial

Pregunta: ¿Cuáles son los requisitos para licencia de chofer?
Respuesta: Sólo Residentes del Municipio de San Pedro (mayores de 18 años). Presentar original y 3 copias
Identificación oficial vigente con fotografía como Credencial de Elector por ambos lados, Pasaporte, Cartilla Militar o Cédula Profesional.
CURP (actualizado con el QR).
Comprobante de Domicilio reciente (vigencia máximo 3 meses) de Agua, Luz, Teléfono (TELMEX). Gas a nombre del interesado o Padres. NOTA: Si usted renta, anexar contrato de arrendamiento y una carta poder simple de uso de derecho del domicilio para el trámite de la licencia con nombre y firma del usuario del recibo y copia del INE por ambos lados del propietario de la casa; dirigido al Departamento de Control Vehicular y al Departamento de Licencias.
2 Fotografías tamaño credencial con rostro de frente, a color y fondo blanco, a color.
Certificado Médico de Buena Salud especificando si es apto para conducir y especificando el tipo de sangre. (Médico Particular, Cruz Roja o Verde, Farmacias Similares, etc.)
Aprobar exámenes de manejo, teórico y práctico, previo a cita virtual.
Ir debidamente presentado con vestimenta y mostrar póliza de seguro vigente.
NOTA:
Si cuentan con Licencia de Automovilista Nacional y/o Extranjera, presentar dos copias.

Pregunta: ¿Cuál es el costo del trámite?
Respuesta: Costo:
$2,979.82 Pago derecho Municipal
$830.00 Instituto de Control Vehicular
Pregunta: ¿A dónde debo acudir?
Respuesta: INSTITUTO DE FORMACIÓN Y PERFECCIONAMIENTO POLICIAL ubicado en Calle María Cantú 302 Col. La Leona San Pedro Garza García de lunes a viernes de 8:00 am a 3:00 pm con previa cita en licenciasmsp@sanpedro.gob.mx Tel. 8137157391 Depto. de Licencias para cualquier duda o aclaración, previa cita.
"""

async def get_licencia_chofer():
    """Obtener información sobre los requisitos para tramitar la licencia de conducir de chofer, en caso de ser necesario.

    Returns:
        string: información sobre los requisitos para tramitar la licencia de conducir de chofer."
    """
    return TC