TC = """
Este documento contiene la información de los servicios de la dirección de Salud Pública del municipio
Pregunta: ¿Cuáles son los servicios de la Dirección de Salud Pública del municipio?
Respuesta: Los servicios que brinda la Dirección de Salud Pública son los siguientes:
Consultorio Médico Canteras
Consultorio Médico Los Pinos
Consultorio Médico El Obispo
Consultorio Movil
Ruta de la Salud
Brigada UN SOLO SAN PEDRO
Salud Preventiva
Pregunta: ¿Cuál es la información de fechas, requisitos, ubicación y costo del Consultorio Médico Canteras?
Respuesta:
Fechas y horarios de atención:
Lunes a viernes 9:00 am a 5:00 pm
Sábados 9:00 am a 2:00 pm
Requisitos
INE
Comprobante de domicilio o CURP
En caso de menores, llevar preferentemente su cartilla de vacunación y estar acompañado de padre o tutor
Ubicación:
Enrique H Herrera 824, Colonia Canteras, 67150, San Pedro Garza García, N.L.
Costo:
Gratuito

Pregunta: ¿Cuál es la información de fechas, requisitos, ubicación y costo del Consultorio Médico Los Pinos?
Respuesta:
Fechas y horarios de atención:
Lunes a viernes 9:00 am a 5:00 pm
Sábados 9:00 am a 2:00 pm
Requisitos
INE
Comprobante de domicilio o CURP
En caso de menores, llevar preferentemente su cartilla de vacunación y estar acompañado de padre o tutor
Ubicación:
Modesto Arreola 228, Colonia los Pinos 1er Sector, 66239, San Pedro Garza García, N.L.
Costo:
Gratuito

Pregunta: ¿Cuál es la información de fechas, requisitos, ubicación y costo del Consultorio Médico El Obispo?
Respuesta:
Fechas y horarios de atención:
Lunes a viernes 9:00 am a 5:00 pm
Sábados 9:00 am a 2:00 pm
Requisitos
INE
Comprobante de domicilio o CURP
En caso de menores, llevar preferentemente su cartilla de vacunación y estar acompañado de padre o tutor
Ubicación:
Eulalio Guzmán 693, Colonia El Obispo, 66216, San Pedro Garza García, N.L.
Costo:
Gratuito

Pregunta: ¿Cuál es la información de fechas, requisitos y ubicación del Consultorio Móvil?
Respuesta:
Fechas y horarios de atención:
Lunes a viernes 8:30 am a 12:00 pm
Requisitos
Registro Previo
Ser ciudadano de San Pedro Garza García. 
Ubicación:
Clouthier/A. I. Villarreal Col. Revolución San Pedro Garza García, N.L.

Pregunta: ¿Cuál es la información de fechas, requisitos, ubicación y costo de la Ruta de la Salud?
Respuesta:
Fechas y horarios de atención:
Lunes a viernes 8:30 am a 3:30 pm
Requisitos
Vivir en el municipio de San Pedro Garza García
Tener movilidad
Contar con red de apoyo
Ser vulnerable (se realiza estudio socioeconómico)
Ubicación:
Centro Administrativo Municipal (CAM), Calle Maria Cantú 329 Col. La Leona Zona Industrial
Costo:
Gratuito

Pregunta: ¿Cuál es la información de fechas, requisitos, ubicación y costo de la Brigada UN SOLO SAN PEDRO?
Respuesta:
Fechas y horarios de atención:
Último jueves de cada mes, durante todo el año
Requisitos
Ser ciudadano de San Pedro Garza García
Ubicación:
Variable
Costo:
Gratuito

Pregunta: ¿Cuál es la información de fechas, requisitos, ubicación y costo del programa Salud Preventiva?
Respuesta:
Fechas y horarios de atención:
Último jueves de cada mes, durante todo el año
Requisitos
Ser ciudadano de San Pedro Garza García
Ubicación:
Variable
Costo:
Gratuito

"""

async def get_salud_publica():
    """Obtener Información de los servicios que ofrece la dirección de Salud Pública en caso de ser necesario.

    Returns:
        string: Informacion servicios que ofrece la dirección de Salud Pública.
    """
    return TC