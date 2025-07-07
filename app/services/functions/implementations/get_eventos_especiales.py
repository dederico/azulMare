TC = """
Este documento contiene información sobre las actividades Culturales  de Julio 2025 correspondientes al municipio de San Pedro Garza García

Todos los domingos 6, 13 , 20 y 27 de Julio.

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

Actividades generales

Preguntas: ¿Qué eventos hay esta semana? / ¿Qué eventos culturales hay? / ¿Qué me recomiendas hacer hoy? / ¿Qué puedo hacer esta esta semana? / ¿Qué puedo hacer este fin de semana

Respuestas:
Exposición: Siestas Largas
Lugar: Casa de la Cultura San Pedro
Fecha: 3 de julio

Concierto en vivo + mercadito
Lugar: Casa de la Cultura Vista Montaña
Fecha: 4 de julio

Charla magistral: Pensamiento cuatorial
Lugar: Centro Cultural Fátima
Fecha: 14 de julio

Gala trifásica de danza
Lugar: Auditorio San Pedro
Fecha: 22 de julio

Velada Astronómica
Lugar: Parque el Capitán
Fecha: 21 de julio

Actividades al aire libre 
Parquecinema 
Lugar: Parque Bosques del Valle. 
Fecha: 2 de Julio.
Horario: 20:00 
Descripción:Espacio al aire libre en donde se proyectan películas. 

Parquecinema 
Lugar: Parque el Capitán.  
Fecha: 5 de Julio.
Horario: 20:00 
Descripción:Espacio al aire libre en donde se proyectan películas. 

Parquecinema 
Lugar: Parque Rufino Tamayo. 
Fecha: 11 de Julio.
Horario: 20:00 
Descripción:Espacio al aire libre en donde se proyectan películas. 
Parquecinema 
Lugar: Parque Clouthier. 
Fecha: 13 de Julio.
Horario: 20:00 
Descripción:Espacio al aire libre en donde se proyectan películas. 
Parquecinema 
Lugar: Parque Bosques del Valle.
Fecha: 16 de Julio.
Horario: 20:00 
Descripción:Espacio al aire libre en donde se proyectan películas. 
Parquecinema 
Lugar: Parque El Capitán.
Fecha: 19 de Julio.
Horario: 20:00 
Descripción:Espacio al aire libre en donde se proyectan películas. 
Parquecinema 
Lugar: Parque Rufino Tamayo.
Fecha: 25 de Julio.
Horario: 20:00 
Descripción:Espacio al aire libre en donde se proyectan películas.
Parquecinema 
Lugar: Parque Clouthier. 
Fecha: 27 de Julio.
Horario: 20:00 
Descripción:Espacio al aire libre en donde se proyectan películas.
Parquecinema 
Lugar: Parque Bosques del Valle.
Fecha: 30 de Julio.
Horario: 20:00 
Descripción:Espacio al aire libre en donde se proyectan películas.
Campamentos de Verano 

Campamento Auditorio San Pedro 
Lugar: Auditorio San Pedro.
Fecha: 28 de Julio al  8 de Agosto.  
Horario: Lunes a Viernes de 9:00 a 12:00 hrs.
Descripción:Experiencia recreativa y educativa, donde los niños participan en actividades al aire libre, juegos, talleres, deportes y dinámicas grupales.

Campamento Casa de la Cultura San Pedro 
Lugar: Casa de la Cultura San Pedro.
Fecha: 7 al 25 de julio. 
Horario: Lunes a Viernes de 9:00 a 13:00 hrs.
Descripción:Experiencia recreativa y educativa, donde los niños participan en actividades al aire libre, juegos, talleres, deportes y dinámicas grupales.

Campamento Casa de la Cultura Vista Montaña 
Lugar: Casa de la Cultura Vista Montaña.
Fecha: 28 de Julio al  8 de Agosto. 
Horario: Lunes a Viernes de 10:00 a 14:00 hrs.
Descripción:Experiencia recreativa y educativa, donde los niños participan en actividades al aire libre, juegos, talleres, deportes y dinámicas grupales.

Campamento Casa de la Cultura La Cima 
Lugar: Casa de la Cultura La Cima.
Fecha: 28 de Julio al  8 de Agosto. 
Horario: Lunes a Viernes de 10:00 a 14:00 hrs.
Descripción:Experiencia recreativa y educativa, donde los niños participan en actividades al aire libre, juegos, talleres, deportes y dinámicas grupales.

Exposición: Siestas largas 
Lugar: Casa de la cultura San pedro.
Fecha: 3 de Julio.
Horario: 7:00
Descripción: Exposición Cultural.

Exposición: Concierto en vivo + mercadito  
Lugar: Casa de la cultura Vista Montaña.
Fecha: 4 de Julio.
Horario: 20.00 hrs. 
Descripción: Evento que combina la música en vivo con un espacio de venta local.

Charla Magistrada: Pensamiento Cuatorial
Lugar:Centro cultural Plaza Fátima 
Fecha: 14 de Julio.
Horario: 7:00 
Descripción: Conferencia. 

Velada Astronómica 
Lugar: Parque el Capitán. 
Fecha: 31 de Julio.
Horario: 6:30 
Descripción: Actividad nocturna al aire libre en la que los participantes se reúnen a  observar el cielo.


"""

async def get_eventos_especiales():
    """Este documento contiene información sobre las actividades culturales de junio 2025 correspondientes a la Secretaría de Cultura del municipio de San Pedro Garza García

    Returns:
        string: Información sobre actividades culturales de junio 2025 correspondientes a la Secretaría de Cultura del municipio de San Pedro Garza García
    """
    return TC