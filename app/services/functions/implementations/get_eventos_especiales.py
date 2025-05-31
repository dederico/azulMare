TC = """
Este documento contiene información sobre las actividades culturales de junio 2025 correspondientes a la Secretaría de Cultura del municipio de San Pedro Garza García

San Pedro de Pinta

Pregunta: ¿Cuándo se realiza San Pedro de Pinta?
Respuesta: Todos los domingos

Pregunta: ¿Dónde se realiza San Pedro de Pinta?
Respuesta: En Calzada del Valle y Calzada San Pedro

Pregunta: ¿A qué hora se lleva a cabo San Pedro de Pinta?
Respuesta: De 9:00 am a 1:00 pm

Bailongo

Pregunta: ¿Cuándo es el bailongo?
Respuesta: Todos los domingos

Pregunta: ¿Dónde es el bailongo?
Respuesta: Bajos del Palacio, colonia Casco Urbano

Pregunta: ¿A qué hora es el bailongo?
Respuesta: De 3:00 pm a 7:00 pm

Música en el parque

Pregunta: ¿Cuándo hay música en el parque?
Respuesta: Todos los domingos

Pregunta: ¿Dónde puedo escuchar música en el parque?
Respuesta: Parque Bosques del Valle

Pregunta: ¿A qué hora es el evento de música en el parque?
Respuesta: De 7:00 pm a 8:00 pm

Fiestas de San Pedro y San Pablo

Pregunta: ¿Cuándo son las fiestas de San Pedro y San Pablo?
Respuesta: Los días 27, 28 y 29 de junio

Pregunta: ¿Dónde serán las fiestas de San Pedro y San Pablo?
Respuesta: Plaza Juárez, en Casco Urbano

Pregunta: ¿A qué hora son las fiestas de San Pedro y San Pablo?
Respuesta: De 5:00 pm a 10:00 pm

Actividades generales

Preguntas: ¿Qué eventos hay esta semana? / ¿Qué eventos culturales hay? / ¿Qué me recomiendas hacer hoy? / ¿Qué puedo hacer esta esta semana? / ¿Qué puedo hacer este fin de semana

Respuestas:
La Gran Batalla de Freestyle: Competencia de rap improvisado
Lugar: Casa de la Cultura la Cima
Fecha 7 de junio

Concierto en Vivo: Arturo Estrada y Desafina2 de la Cumbia
Lugar: Casa de la Cultura la Cima
Fecha: 14 de junio
Horario: Inicia 6:00 pm

Concierto en Vivo: Grupo Kambala y Los Patrones
Lugar: Mercadito Cultural de las Casas de la Cultura
Fecha: 21 de junio
Horario: Inicia 6:00 pm

Sabor a México
Lugar: Centro Cultural Plaza Fátima
Fecha: 26 de junio
Horario: 8:00 pm

"""

async def get_eventos_especiales():
    """Este documento contiene información sobre las actividades culturales de junio 2025 correspondientes a la Secretaría de Cultura del municipio de San Pedro Garza García

    Returns:
        string: Información sobre actividades culturales de junio 2025 correspondientes a la Secretaría de Cultura del municipio de San Pedro Garza García
    """
    return TC