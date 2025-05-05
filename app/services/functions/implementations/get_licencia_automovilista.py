TC = """
Este documento contiene información sobre los requisitos para tramitar
la licencia de conducir de automovilista / motociclista
Pregunta: ¿Cómo puedo realizar el trámite de licencia de conducir de automovilista o
motociclista?
Respuesta: Aquí te compartimos los links para realizar el trámite:
● Solicitud de licencia de conducir para mayores de 18 años (mexicano/a):
https://tramites.sanpedro.gob.mx/gobierno_de_san_pedro_garza_garcia_be055859/
solicitud_de_licencia_de_automovilista_provisional_para_jovenes_de_16-17_anos_c
ef0e5fc-211f-4164-a736-f69c671ed3dc
● Solicitud de licencia de conducir para mayores de 18 años (extranjero/a):
https://tramites.sanpedro.gob.mx/gobierno_de_san_pedro_garza_garcia_be055859/
solicitud_de_licencia_de_conducir_para_personas_extranjeras_mayores_de_18_an
os_ea1f750e-3dc4-4c9a-a658-0a22c7517f56
● Solicitud de licencia de conducir para motociclista (mexicano/a):
https://tramites.sanpedro.gob.mx/gobierno_de_san_pedro_garza_garcia_be055859/
solicitud_de_licencia_de_manejo_para_motociclista_8db9229f-ab7b-486b-a9a5-85f3
21e6c51a
● Solicitud de licencia de conducir para motociclista (extranjero/a):
https://tramites.sanpedro.gob.mx/gobierno_de_san_pedro_garza_garcia_be055859/
solicitud_de_licencia_de_conducir_para_motociclista_extranjero_24fd88f8-0cd5-498f
-a7e5-aa7ec2aa05d2

Pregunta: ¿Cuáles son los requisitos para licencia de automovilista / motociclista?
Respuesta: Sólo Residentes del Municipio de San Pedro (mayores de 18 años). Presentar
original y 3 copias
1. Identificación oficial vigente con fotografía como Credencial de Elector por ambos
lados, Pasaporte, Cartilla Militar o Cédula Profesional.
2. CURP (actualizado con QR).
3. Comprobante de Domicilio reciente (vigencia máximo 3 meses) de Agua, Luz,
Teléfono (TELMEX) a nombre del interesado o Padres.
NOTA: Si usted renta, anexar contrato de arrendamiento original y una carta poder
simple de uso de derecho del domicilio para el trámite de la licencia, con nombre y
firma del usuario del recibo y copia del INE por ambos lados del propietario de la
casa; dirigido al Departamento de Control Vehicular y al Departamento de Licencias.
4. 2 Fotografías tamaño credencial con rostro de cerca, de frente y fondo blanco
(vigentes) a color.
5. Certificado Médico de Buena Salud especificando si es apto para conducir y
especificando el tipo de sangre. (Médico Particular, Cruz Roja o Verde, Farmacias
Similares, Benavides.)
6. Aprobar exámenes que se le apliquen, teórico y práctico virtual.

7. Ir debidamente presentado con vestimenta y mostrar póliza de seguro vigente.
NOTA:
Si cuenta con Licencia de Automovilista Nacional y/o Extranjera, presentar dos copias.

Pregunta: ¿Cuál es el costo del trámite?
Respuesta: Costo:
● $2,597.94 Pago derecho Municipal
● $830.00 Instituto de Control Vehicular
Pregunta: ¿A dónde debo acudir?
Respuesta: INSTITUTO DE FORMACIÓN Y PERFECCIONAMIENTO POLICIAL ubicado
en Calle María Cantú 302 Col. La Leona San Pedro Garza García de lunes a viernes de
8:00 am a 15:00 pm o previa cita en licenciasmsp@sanpedro.gob.mx Tel. 8137157391
Depto. de Licencias para cualquier duda o aclaración, previa cita.
"""

async def get_licencia_automovilista():
    """Obtener información sobre los requisitos para tramitar la licencia de conducir licencia de conducir de automovilista / motociclista, en caso de ser necesario.

    Returns:
        string: información sobre los requisitos para tramitar la licencia de licencia de conducir de automovilista / motociclista."
    """
    return TC