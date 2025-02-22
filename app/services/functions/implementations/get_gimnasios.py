
TC = """
Este documento contiene información sobre ubicaciones, horarios y contactos de los gimnasios y áreas deportivas municipales

Pregunta: ¿Cuáles son los gimnasios municipales?
Respuesta:
Centro Deportivo FUD
-	Ubicación: Ma. Cantú Treviño 329 Col. La Leona, San Pedro Garza García, N.L.
-	Horario de atención: Lunes a viernes de 09:00 a 17:00 hrs.
-	Horario de gimnasio: Lunes a viernes 08:00 a 21:00 hrs. y sábado de 08:00 a 12:00 hrs.
-	Teléfono: 81 8676 5356

Gimnasio San Pedro 400
-	Ubicación: Av. Clouthier No. 157, col. San Pedro 400, San Pedro Garza García, N.L.
-	Horario de atención: Lunes a Viernes de 08:00 a 21:00 hrs.
-	Horario de gimnasio: Lunes a viernes de 07:00 a 21:00 hrs. y sábado de 08:00 a 13:00 hrs.
-	Teléfono: 81 8315 8814

Gimnasio La Raza
-	Ubicación: Av. Clouthier y Platino S/N, col. San Pedro 400, San Pedro Garza García, N.L.
-	Horario de atención: Lunes a viernes de 08:00 a 21:00 hrs.
-	Horario de gimnasio: Lunes a viernes de 07:00 a 21:00 hrs. y sábado de 08:00 a 13:00 hrs.
-	Teléfono: 81 8242 5034

CDI San Pedro
-	Ubicación: Lázaro Garza Ayala 1001, col. Lázaro Garza Ayala, San Pedro Garza García, N.L.
-	Horario de atención: Lunes a viernes de 08:00 a 21:00 hrs.
-	Horario de gimnasio: Lunes a viernes de 07:00 a 21:00h y sábado de 08:00 a 13:00 hrs.
-	Teléfono:81 1052 4343

Jesús D. González
-	Ubicación: Libertad 206, col. Centro, San Pedro Garza García, N.L.
-	Horario de atención: Lunes a viernes de 08:00 a 21:00 hrs.
-	Horario de gimnasio: Lunes a viernes de 06:00 a 21:00 hrs. y sábado de 08:00 a 13:00 hrs.
-	Teléfono: 81 8400 4513 

Gimnasio Tampiquito
-	Ubicación: Plutarco Elías Calles y Amatista S/N, col. Lomas de Tampiquito, San Pedro Garza García, N.L.
-	Horario de atención: Lunes a viernes de 08:00 a 21:00 hrs.
-	Horario de gimnasio: Lunes a viernes de 07:00 a 21:00 hrs. y sábado de 08:00 a 13:00h hrs.
-	Teléfono: 81 8338 7611

Gimnasio Vista Montaña:
-	Ubicación: Nicéforo Zambrano S/N, col. Vista Montaña, San Pedro Garza García, N.L.
-	Horario de atención: Lunes a viernes de 08:00 a 21:00h hrs.
-	Horario de gimnasio: Lunes a viernes de 07:00 a 21:00 hrs. y sábado de 08:00 a 13:00 hrs.
-	Teléfono: 81 8989 1759

Gimnasio El Obispo
-	Ubicación: Landon S/N, col. Villa del Obispo, San Pedro Garza García, N.L.
-	Horario de atención: Lunes a viernes de 08:00 a 21:00h hrs.
-	Horario de gimnasio: Lunes a viernes de 07:00 a 21:00 hrs. y sábado de 08:00 a 13:00 hrs.
-	Teléfono: 81 8315 8971

Pregunta: ¿Qué espacios deportivos tiene el municipio?
Respuesta:

-	Alberca Olímpica: Ubicada en el gimnasio La Raza, cuenta con clases para niños desde los 6 años hasta adultos mayores, además de ser casa de nuestro equipo representativo de natación. Conoce las distintas actividades y horarios que tenemos para ti:

Adultos: Lunes a viernes de 06:00 a 10:00 hrs. y lunes a viernes de 19:00 a 21:00 hrs.
Niños de 4 a 14 años: Lunes a viernes de 15:00 a 17:00 hrs.

Informes:
Teléfono: 818 242 5034
Ubicación: Av. Clouthier y Platino S/N, col. San Pedro 400, San Pedro Garza García, N.L.

-	Cancha de la U: Con instalaciones de primer nivel, cuenta con baños en buen estado y en los que el mantenimiento es constante. Acércate a preguntar sobre las ligas y actividades que ofrecemos en esta cancha.

Informes: 
Teléfono: 818 315 6912
WhatsApp: 813 238 4611
Correo: jessica.martinez@sanpedro.gob.mx
Ubicación: Zona Clouthier, entre Ruiz Cortinez y Corregidora, San Pedro Garza García, N.L.

-	Parque de Béisbol Carlos Bremer: Remodelado recientemente, este parque de béisbol cuenta con instalaciones en excelente estado. Acércate a preguntar sobre las ligas de béisbol y softbol que ofrecemos en este parque.

Informes:
Tel: 818 315 6912
Correo: elba.wong@sanpedro.gob.mx
Ubicación: Av. Corregidora S/N, entre 16 de septiembre y 5 de mayo, col. Casco Urbano, San Pedro Garza García, N.L.

-	Biciparque: Ciclismo de montaña y BMX, en este biciparque pueden disfrutar de la emoción de rodar chicos y grandes. Abierto a todo el público y con entrada libre, los únicos requisitos son tener casco y cubrebocas.

Informes: 
WhatsApp: 818 111 9995
Correo: deporte.social@sanpedro.gob.mx
Ubicación: Palma S/N, óvalo de ciclismo frente la UDEM, Col. La Leona. San Pedro Garza García, N.L.
"""


async def get_gimnasios():
    """Obtener informacion sobre ubicaciones, horarios y contactos de los gimnasios y áreas deportivas municipales en caso de ser necesario.

    Returns:
        string: Información sobre ubicaciones, horarios y contactos de los gimnasios y áreas deportivas municipales.
    """
    return TC