TC ="""
Este documento contiene información sobre la ruta de recolección de basura ordinaria o basura doméstica de San Pedro Garza García

Pregunta: ¿Cuáles son las rutas de basura ordinaria / basura doméstica?
Respuesta:

Lunes, miércoles y viernes
Turno Matutino
Jesús M. Garza
Linda Vista
Lucio Blanco 3er Sector
Valle de Vasconcelos
Lázaro Garza Ayala
Rincón de San Francisco
Los Sauces 1er y 2do Sector
Casco Urbano
Santa Elena
Misión del Valle
Las Sendas Galicias
Valle Poniente
Hacienda Palo Blanco
Hacienda Las Campanas
Hacienda El Rosario
La Ventana
Lomas del Rosario
Prados de la Sierra
Fraccionamiento La Reserva
Los Callejones
La Joya
Residencial Santa Barbara La Cripta
Los Sabinos
Mirasierra
San Gabriel
Los Encinos
Valle del Mezquite
Palo Blanco
Palo Blanco Sector Del Edén
Jardines Coloniales
Los Olmos
La Cima
Villa Montaña
San Francisco
Rincón de Corregidora
Nemesio García Naranjo
Rincón Colonial
Las Mapas
Los Pinos 1er y 2do Sector
Turno Vespertino
Zona Industrial
Valle del Seminario
Lucio Blanco 1er y 2do Sector
Luis Echeverría
Plan de Ayala
Revolución
Vista Montaña
Del Valle
Fuentes del Valle
Jardines del Valle
Tampiquito
La Montaña
Rincón de la Montaña 2do Sector
Provivienda Popular
Capistrano
Lomas del Valle Sector Convento
El Obispo
Villas del Obispo
San Pedro 400

Martes, Jueves y Sábado
Turno Matutino
San Patricio
Veredalta
San Agustín Campestre
Colonial de la Sierra
Bosques de la Sierra
Residencial Sierra del Valle
El Santuario
Valle de San Angel Sector Rincón Frances
Valle de San Ángel Sector Español
Valle de San Ángel Sector Mexicano
Valle de San Ángel Sector Frances
Valle de San Ángel Sector Jardines
Bosques de San Angel
Ampliación Palmillas
Colinas de San Angel
Olinalá
Ampliación Canteras
Canteras
San Mateo
Los Arcangeles
Los Amates
Los Quetzales
Misión de San Patricio
Colinas San Agustín
Antigua Hacienda San Agustín
Residencial Chipinque
Comercial Alpino
Mesa de la Corona
Joya de la Corona
Lomas de San Angel
Hacienda Carrizalejo
Real San Agustín
Residencial Magenta
Privada San Roberto
La Encantada
Las Ceibas
Santa Cruz
Villa Las Palmas
Hacienda San Agustín
El Refugio
Lomas de San Agustín
Las Querenzas
Los Olivos
Lomas de San Agustín
El Secreto
Colonial San Agustín
Balcones San Agustín
Balcones
 del Campestre
Valle Oriente Sur
Lomas del Campestre
La Muralla
Privanzas
Real del Valle
Santa Fe
Loma Blanca
Las Alondras
Villa Chipinque
Las Calzadas
Jardines San Agustín
Colorines
Olímpico
Hacienda Del Valle
Misión del Rosario
La Barranca
Ampliación Tampiquito
Lomas de Tampiquito
Barrancas del Pedregal
Pedregal del Valle
Villas del Pedregal
Bosques del Valle 4to y 5to Sector
Jeronimo Siller
Rincón de Carrizalejo
Valle de Chipinque
Zona Gomez Morín
Turno Vespertino
Fuentes del Valle
Residencial Santa Barbara 1er y 2do Sector
Valle del Campestre
Vista Real
Del Valle
Del Valle Oriente
Santa Engracia
Residencial San Agustín 1er y 2do Sector
Jardines del Campestre
Mirador del Campestre
Valle Oriente Norte
Residencial Frida Kahlo
Corporativo Proser
Zona Loma Larga
Portal de Santa Engracia
Hacienda de la Sierra
Ampliación Valle del Mirador
Ampliación Canteras
San Mateo
La Diana
Bosques del Valle 1er, 2do y 3er Sector
Villas de Aragón
Punto Central
Montebello
Del Valle Sector Fátima
Privada del Convertido
Villa de Terrasol
"""

async def get_basura_domestica():
    """Obtener Información de la basura domestica, las rutas, y los días en caso de ser necesario.

    Returns:
        string: Informacion sobre la basura domestica.
    """
    return TC