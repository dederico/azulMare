TC = """
Este documento contiene información sobre los requisitos para tramitar
la licencia de conducir de menores de 16 y 17 años
Pregunta: ¿Cómo puedo realizar el trámite de licencia de conducir de menores de 16 y 17
años?
Respuesta: Aquí te compartimos los links para realizar el trámite:
● Solicitud de licencia de conducir provisional para jóvenes de 16-17 años
(mexicano/a):
https://tramites.sanpedro.gob.mx/gobierno_de_san_pedro_garza_garcia_be055859/
solicitud_de_licencia_de_automovilista_provisional_para_jovenes_de_16-17_anos_c
ef0e5fc-211f-4164-a736-f69c671ed3dc
● Solicitud de licencia de conducir provisional para jóvenes de 16-17 años
(extranjero/a):
https://tramites.sanpedro.gob.mx/gobierno_de_san_pedro_garza_garcia_be055859/
copia_solicitud_de_licencia_de_conducir_provisional_para_jovenes_de_16-17_anos
_extranjero_f9996473-d4ce-4aec-94ff-9c553dae3d35
● Cambio de permiso novel a solicitud de licencia de conducir para jóvenes de 16-17
años (mexicano/a):
https://tramites.sanpedro.gob.mx/gobierno_de_san_pedro_garza_garcia_be055859/
cambio_de_licencia_novel_a_solicitud_de_licencia_de_16-17_anos_c67243f6-1282-
4049-8ac7-6be276fa70af
● Cambio de permiso novel a solicitud de licencia de conducir para jóvenes de 16-17
años (extranjero/a):
https://tramites.sanpedro.gob.mx/gobierno_de_san_pedro_garza_garcia_be055859/
cambio_de_permiso_novel_a_solicitud_de_licencia_de_conducir_para_jovenes_de_
16-17_anos_extranjero_883a7aa2-e8df-4338-8cd1-efe682ffedbf
Pregunta: ¿Cuál es el tiempo que dura la licencia de conducir?
Respuesta: 2 Años (Provisional) Sólo Habitantes de San Pedro
Pregunta: ¿Cuáles son los requisitos para licencia de automovilista / motociclista para
menores de 16 y 17 años?
Respuesta: Presentar original y 3 copias
1. Tomar Curso de Manejo, presentar constancia (vigencia máximo 3 meses) solo con
las escuelas autorizadas por SSP
2. Acta de Nacimiento Reciente.
3. Clave Única de Registro de Población (CURP), Actualizado con QR.
4. Identificación oficial vigente con fotografía como Pasaporte Mexicano y/o Credencial
de Estudios.
5. Comprobante de domicilio, (vigencia máximo 3 meses) de AGUA, LUZ o
TELÉFONO (TELMEX), a nombre del interesado, padres o abuelos. Nota: si usted
renta Anexar CONTRATO DE ARRENDAMIENTO Y UNA CARTA PODER SIMPLE
DIRIJIDO AL DEPARTAMENTO DE CONTROL VEHICULAR Y AL
DEPARTAMENTO DE LICENCIAS; LA INE POR AMBOS LADOS DEL

PROPIETARIO DEL DOMICILIO (no electrónico no escaneado) (NO SE ACEPTAN
RECIBOS DE PROPIEDADES COMERCIALES)
6. 2 Fotografías tamaño credencial con rostro de cerca, de frente y fondo blanco.
7. Venir acompañado por uno de los padres y/o tutor legal presentar identificación
oficial vigente, (OBLIGATORIO)
8. Certificado Médico de Buena Salud (Pediatra Particular, Cruz Roja o Verde,
Farmacias Similares, Benavides etc.). Especificar el tipo de sangre.
9. Presentarse con vehículo y mostrar póliza de seguro vigente.
10. Aún cuando hayan tomado el curso de manejo deberán aprobar los exámenes que
se le aplicarán, tanto el teórico y práctico. VIRTUAL
Cambio de requisitos y costos sin previo aviso

Pregunta: ¿Cuál es el costo del trámite?
Respuesta: Costo:
- $2,800.98 Pago de derecho Municipal.
- $770.00 Instituto de Control Vehicular

Pregunta: ¿A dónde debo acudir?
Respuesta: INSTITUTO DE FORMACIÓN Y PERFECCIONAMIENTO POLICIAL ubicado
en Calle María Cantú 302 Col. La Leona San Pedro Garza García de lunes a viernes de
8:00 am a 15:00 pm o previa cita en licenciasmsp@sanpedro.gob.mx Tel. 8137157391
Depto. de Licencias para cualquier duda o aclaración, previa cita.
Pregunta: ¿Donde puedo cambiar una cita que tenía programada de manejo de menores
de edad?
Respuesta: Puede comunicarse vía telefónica al número: 8137157391 o al 8137157392 del
área de Licencias de Tránsito para que le brinden la atención que usted necesita.
"""

async def get_licencia_provisional():
    """Obtener información sobre los requisitos para tramitar la licencia de conducir provisional para 15 años en caso de ser necesario.

    Returns:
        string: información sobre los requisitos para tramitar la licencia de conducir provisional para 15 años.
    """
    return TC