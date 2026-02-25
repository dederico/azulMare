TC = """
Este documento contiene información sobre los requisitos para tramitar la licencia de conducir de menores de 16 y 17 años
Pregunta: ¿Cómo puedo realizar el trámite de licencia de conducir de menores de 16 y 17 años?
Respuesta: Todos los trámites se realizan de forma presencial en el Instituto de Formación y Perfeccionamiento Policial

Pregunta: ¿Cuál es el tiempo que dura la licencia de conducir?
Respuesta: 2 Años (Provisional) Sólo Habitantes de San Pedro

Pregunta: ¿Cuáles son los requisitos para licencia de automovilista / motociclista para menores de 16 y 17 años?
Respuesta: Presentar original y 3 copias

Tomar Curso de Manejo, presentar constancia (vigencia máximo 3 meses) solo con las escuelas autorizadas por SSP
Acta de Nacimiento Reciente.
Clave Única de Registro de Población (CURP), Actualizado con QR.
Identificación oficial vigente con fotografía como Pasaporte Mexicano y/o Credencial de Estudios.
Comprobante de domicilio, (vigencia máximo 3 meses) de AGUA, LUZ o TELÉFONO (TELMEX), a nombre del interesado, padres o abuelos. Nota: si usted renta Anexar CONTRATO DE ARRENDAMIENTO Y UNA CARTA PODER SIMPLE DIRIJIDO AL DEPARTAMENTO DE CONTROL VEHICULAR Y AL DEPARTAMENTO DE LICENCIAS; LA INE POR AMBOS LADOS DEL PROPIETARIO DEL DOMICILIO (no electrónico no escaneado) (NO SE ACEPTAN RECIBOS DE PROPIEDADES COMERCIALES)
2 Fotografías tamaño credencial con rostro de cerca, de frente y fondo blanco.
Venir acompañado por uno de los padres y/o tutor legal presentar identificación oficial vigente, (OBLIGATORIO)
Certificado Médico de Buena Salud (Pediatra Particular, Cruz Roja o Verde, Farmacias Similares, Benavides etc.). Especificar el tipo de sangre.
Presentarse con vehículo y mostrar póliza de seguro vigente.
Aún cuando hayan tomado el curso de manejo deberán aprobar los exámenes que se le aplicarán, tanto el teórico y práctico. VIRTUAL

Cambio de requisitos y costos sin previo aviso

Pregunta: ¿Cuál es el costo del trámite?
Respuesta: Costo:
$2,800.98 Pago de derecho Municipal.
$770.00 Instituto de Control Vehicular

Pregunta: ¿A dónde debo acudir?
Respuesta: INSTITUTO DE FORMACIÓN Y PERFECCIONAMIENTO POLICIAL ubicado en Calle María Cantú 302 Col. La Leona San Pedro Garza García de lunes a viernes de 8:00 am a 15:00 pm o previa cita en licenciasmsp@sanpedro.gob.mx Tel. 8137157391 Depto. de Licencias para cualquier duda o aclaración, previa cita.
Pregunta: ¿Donde puedo cambiar una cita que tenía programada de manejo de menores de edad?
Respuesta: Puede comunicarse vía telefónica al número: 8137157391 o al 8137157392 del área de Licencias de Tránsito para que le brinden la atención que usted necesita.

"""

async def get_licencia_16():
    """Obtener información sobre los requisitos para tramitar la licencia de conducir de menores de 16 y 17 años, en caso de ser necesario.

    Returns:
        string: información sobre los requisitos para tramitar la licencia de conducir de menores de 16 y 17 años."
    """
    return TC