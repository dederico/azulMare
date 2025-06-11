TC = """
Este documento contiene información sobre los requisitos para tramitar la licencia de conducir provisional para 15 años
Pregunta: ¿Cómo puedo realizar el trámite de licencia de conducir provisional para 15 años?
Respuesta: Respuesta: Todos los trámites se realizan de forma presencial en el Instituto de Formación y Perfeccionamiento Policial

Pregunta: ¿Cuáles son los requisitos para permiso provisional para jóvenes de 15 años?
Respuesta: ORIGINAL Y 4 COPIAS
Tomar curso de manejo en una Escuela autorizada por la S.S.P.V. vigente.
CONSTANCIA DE MANEJO Vigente ORIGINAL y 4 copias.
Copia de Póliza de Seguro del vehículo elegido para conducir vigente.
Copia de la Tarjeta de Circulación del vehículo elegido vigente, a nombre de los padres o carta membretada de la empresa y copia del INE del que la firma.
Acta de Nacimiento original y 4 copias recientes.
CURP 4 impresiones actualizada con QR impreso.
Identificación de los padres y/o tutor 4 copias c/u (IFE o Pasaporte).
Original y 4 copias de Comprobante de Domicilio (vigencia máxima 3 meses) de Agua, Luz o Teléfono (Telmex) a nombre de los padres y/o abuelos. En caso de rentar, anexar contrato de arrendamiento y una carta poder simple dirigida al Departamento de Control Vehicular y al Departamento de Licencias, la INE por ambos lados del propietario del domicilio (no electrónico ni escaneado). No se aceptan recibos de propiedades comerciales.
(3) Fotografías 2 tamaño credencial y 1 infantil (estudio fotográfico reciente con fondo blanco).
4 copias de Identificación del interesado (Credencial de Estudiante o Pasaporte).
Constancia médica de buena salud, original y 1 copia especificando si es apto para conducir y especificando el tipo de sangre (Médico Particular, Cruz Roja, Farmacias Similares, etc.).
Ir acompañado de alguno de sus padres para firma de la carta responsiva, obligatorio.
Calificaciones con promedio de 8.5.

Pregunta: ¿Cuáles son las restricciones y disposiciones de permiso para jóvenes de 15 años?
Respuesta:
Sólo podrán manejar el vehículo asignado, así como también deberán portar siempre su permiso con fotografía el cual lo identifica como conductor novel.
El horario autorizado para circular es de 06:00 a 22:00 hrs.
Este permiso es válido únicamente en el Municipio de San Pedro Garza García.
Es obligatorio renovar cada 3 meses hasta cumplir los 16 años.
En caso de ser infraccionado, se le decomisará el permiso en el Departamento de Licencias a partir del día en que pague la infracción.
Se entregará Permiso Novel al tramitar la Licencia de 16 años con la papelería correspondiente; de lo contrario, se efectuará el pago en caja por la pérdida o extravío del permiso.
Traer el vehículo asignado y portar ambas placas, solo vehículo nacional, excepto pick-up.
Si extravía o emite el permiso, se le cobrará por uno nuevo.
Al cambiar de vehículo, se tramitará un permiso nuevo.
Nota:
El permiso deberá tener las renovaciones anteriores; en caso de que no cuente con ellas, se le cobrará por cada una.
Cambio de requisitos y costos sin previo aviso (evite sanciones).

Pregunta: ¿Cuál es el horario y contacto del departamento de licencias?
Respuesta:
HORARIO:
Lunes a viernes de 8:00 a 15:00 hrs. Previa cita, trámite exclusivo en Calle María Cantú Col. La Leona #329, San Pedro Garza García, N.L.
TEL: 8137157391. Departamento de Licencias para cualquier duda o aclaración, previa cita.
Email: licenciasmsp@sanpedro.gob.mx
Pregunta: ¿Cuál es el costo del trámite?
Respuesta: Pago de derecho municipal:
Costo: $2,597.94 (primera vez).
Refrendo: $1,250.86 (cada 3 meses).
"""

async def get_licencia_15():
    """Obtener información sobre los requisitos para tramitar la licencia de conducir provisional para 15 años en caso de ser necesario.

    Returns:
        string: información sobre los requisitos para tramitar la licencia de conducir provisional para 15 años.
    """
    return TC