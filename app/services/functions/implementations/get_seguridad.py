TC = """
Este documento contiene información sobre los trámites de la Secretaría de Seguridad del municipio de San Pedro Garza García

Pregunta: ¿Cómo puedo realizar una solicitud de permiso de circulación de vehículos de carga pesada?

Respuesta: Por medio de este trámite se puede obtener un permiso especial para la circulación de vehículos de carga pesada dentro del territorio municipal.

Requisitos:
Factura o contrato de arrendamiento del vehículo y su remolque
Identificación oficial 
Tarjeta de circulación y su remolque
Póliza de seguro de responsabilidad civil por daños a terceros
Licencia de conducir vigente del operador del vehículo
Permiso o licencia de construcción en su caso
Solicitud por escrito que deberá tener la siguiente información de manera correcta:
Nombre del solicitante
Documento con el que se identifica 
Teléfono 
Correo electrónico
Dirección del lugar destino, proporcionando el domicilio ya sea casa particular o empresa
Nombre de la empresa destinataria
Principales avenidas a transitar 
Horario y fechas a transitar en vías restringidas dentro del municipio
Tipo de vehículo, marca, modelo, placas y número de serie
En caso de llevar remolque, indicar el tió, así como la marca, modelo, placas y número de serie

Tiempo de Atención:
Plazo máximo de 3 días hábiles

Tipo de Trámite: 
Presencial
Ubicación: C2 San Pedro, Av. Lázaro Cárdenas 2232, Col. Valle Oriente

Teléfono:
81 89 88 11 00 Extensión 6011

Link del trámite: https://tramites.sanpedro.gob.mx/gobierno_de_san_pedro_garza_garcia_be055859/solicitud_de_permiso_de_circulacion_de_vehiculos_de_carga_pesada_2efcdace-b94b-4b52-8a7c-7bd7b99ac2fa

Pregunta: ¿Cuál es el teléfono del C2?
Respuesta: 81 89 88 11 00 Extensión 6011

Pregunta: ¿Cuál es el teléfono del C4?
Respuesta: 81 89 88 20 00
"""

async def get_seguridad():
    """Obtener informacion de seguridad, tramites y telefonos de C2, C4 y dependencias de la Secretaria de Seguridad del municipio.

    Returns:
        string: Informacion de los trámites de la Secretaria de Seguridad.
    """
    return TC
