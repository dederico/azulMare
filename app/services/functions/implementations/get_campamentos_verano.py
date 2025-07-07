TC = """
Este documento contiene información sobre los Campamentos de Verano que se ofrecen en el municipio de San Pedro Garza García

Campamento de Verano Deportes

Pregunta: ¿Dónde será el campamento de verano de deportes?
Respuesta:
Gimnasio La Raza
Gimnasio San Pedro 400
CDI

Pregunta: ¿Cuál es el horario del campamento de verano de deportes?
Respuesta: De 9 am a 12 pm

Pregunta: ¿Cuándo es el campamento de verano de deportes?
Respuesta: Se llevará a cabo del lunes 21 de julio a viernes 8 de agosto

Pregunta: ¿Cuáles son las edades para el campamento de verano de deportes?
Respuesta: De 6 a 12 años

Pregunta: ¿Cuál es el registro para el campamento de verano de deportes?
Respuesta: El registro es de forma presencial en los centros deportivos

Pregunta: ¿Qué deportes son los que se imparten en el campamento de verano de deportes?
Respuesta: Baile, natación, tae kwon do, básquetbol, fútbol, gimnasia, voleibol, entre otros

Pregunta: ¿Cuál es el contacto para el campamento de verano de deportes?
Respuesta:
Gimnasio La Raza
Av. Manuel J. Clouthier y Platino, S/N, Col. San Pedro 400
8182425034
Gimnasio San Pedro 400
Av. Manuel J. Clouthier y División del Norte, Col. San Pedro 400
8183158814
CDI San Pedro
Lázaro Garza Ayala 1001, Col. Lázaro Garza Ayala
8110524343




Campamento de la Casa de la Cultura

Pregunta: ¿Dónde serán los campamentos de verano de las casas de la cultura?
Respuesta:
Casa de la Cultura San Pedro
Casa de la Cultura la Cima
Casa de la Cultura Vista Montaña

Pregunta: ¿Cuáles son las clases que se impartirán en el campamento de verano de la Casa de la Cultura Vista Montaña y la Casa de la Cultura La Cima?
Respuesta:
Soy capaz, soy arte
Cambiemos el arte
Expresión corporal
Movimiento y expresión
Carnaval musical
Baile moderno
Saborarte
Cantando, moviendo y creciendo

Pregunta: ¿Cuáles son las clases que se impartirán en el campamento de verano de la Casa de la Cultura San Pedro?
Respuesta:
Pintando con ilusión
Creando con alegría
Expresión corporal
Movimiento y expresión
Carnaval musical
Baile moderno

Pregunta: ¿Cuáles son las fechas y horarios para los campamentos de verano de las casas de la cultura?
Respuesta:
Casa de la Cultura San Pedro
Inscripciones: Del 1 al 4 de julio
Campamento: Del 7 al 26 de julio
Horario: 9:00 am a 1:00 pm
Edades de registro: 6 a 10 años
Casa de la Cultura la Cima
Inscripciones: Del 14 al 18 de julio
Campamento: Del 28 de julio al 8 de agosto
Horario: 10:00 am a 2:00 pm
Edades de registro: 7 a 12 años
Casa de la Cultura Vista Montaña
Inscripciones: Del 14 al 18 de julio
Campamento: Del 28 de julio al 8 de agosto
Horario: 10:00 am a 2:00 pm
Edades de registro: 7 a 12 años

Pregunta: ¿Cuáles son los requisitos para los campamentos de verano de las casas de la cultura?
Respuesta:
INE
Comprobante de domicilio que acredite residencia en San Pedro Garza García

Pregunta: ¿Cuál es el costo de inscripción para los campamentos de verano de las casas de la cultura?
Respuesta:
$100 por sampetrino, hermano adicional $50
$150 foráneo, hermano adicional $75



Campamento Exploradores del Parque de San Pedro Parques

Pregunta: ¿Dónde será el campamento Exploradores del Parque de San Pedro Parques?
Respuesta:
Parque Mississippi

Pregunta: ¿Cuáles son las fechas y horarios para el campamento Exploradores del Parque de San Pedro Parques?
Respuesta:
Del 14 al 25 de julio
De lunes a viernes
De 9:00 am a 1:00 pm

Pregunta: ¿Cuáles son las clases que se impartirán en el campamento Exploradores del Parque de San Pedro Parques?
Respuesta:
Naturaleza
Ciencia y arte
Activación física
Inteligencia emocional

Pregunta: ¿Cuáles son las edades para registrarse en el campamento Exploradores del Parque de San Pedro Parques?
Respuesta: Para peques de 5 a 12 años

Pregunta: ¿Cuál es el contacto para registrarme al campamento Exploradores del Parque de San Pedro Parques
Respuesta:
WhatsApp: 81 1801 5150
Correo: vinculacion@sanpedroparques.mx
Mediante redes sociales de San Pedro Parques

"""

async def get_campamentos_verano():
    """Obtener información sobre los Campamentos de Verano que se ofrecen en el municipio de San Pedro Garza García en caso de ser necesario.

    Returns:
        string: Informacion sobre los Campamentos de Verano que se ofrecen en el municipio de San Pedro Garza García.
    """
    return TC