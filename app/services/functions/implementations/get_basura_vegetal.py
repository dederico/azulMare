TC = """
Este documento contiene información sobre las Rutas de Basura Vegetal

Pregunta: ¿Cómo debe estar la basura vegetal para que se la lleven?
Respuesta:
Para el retiro de hojas:
Deben estar en bolsas cerradas (de preferencia en sacos)
Sin líquidos
Se retira un máximo de 10 bolsas por vivienda.
Para el retiro de ramas:
Deben estar amarradas.
Los troncos deben estar cortados a un metro de largo x 50 cm de diámetro.
Se retira un máximo de un metro cúbico por domicilio.

Pregunta: ¿Cuándo pasa la ruta de basura vegetal en mi colonia?
Respuesta:
Lunes
Antigua Hacienda San Agustín
Balcones de San Agustín
Bosques de San Pedro
Casco Urbano "SUR"
Carrizalejo
Conj. Hab. Las Bugambilias
Corp. PRODESA
El Refugio
Flor de Mayo
Hacienda San Agustin
La Cañada
Loma Blanca
Lomas de San Agustin
Lomas del Campestre
Los Amates
Los Sabinos
Los Sauces 1er. y 2º Sector "OTE"
Palo Blanco
Parque Corp. Uccaly
Privada Lomas de San Agustin
Privada San Roberto
Real de San Agustin
San Patricio
Santa Cruz
Santa Elena
Sector El Eden
Valle de San Agustín Sec. Jardines
Valle de San Agustin 
Valle de San Angel "Rincon Frances"
Veredalta
Villa Chipinque
La Muralla
Las Privanzas
Villa Las Palmas
Colinas de San Agustín
Valle de san Angel "Sector Jardines"

Martes
Colonia del Valle "NTE-PTE"
Colonia del Valle "SUR-PTE"
Colorines Sec. 1, 2, 3, 4 y 5
Jardines de Mirasierra
Fuentes del Valle
Jardines de San Agustín Sec. 1 y 2
Jardines del Valle
Mirasierra Sec. 4 y 5
Valle del Mezquite
Antigua Hacienda San Agustin
Misión de San Patricio

Miércoles
Bosque de San Agustin Sec. Palmilla
Bosque de San Angel Amp. Palmilla
Colinas de San Angel
Colonia del Valle "SUR-OTE"
Colonia del Valle "SUR-PTE"
Comercial Alpino
Cortijo del Valle
Del Valle Sec. "NTE"
Fuentes del Valle
Fuentes del Valle Sec. 7 Colinas
Hacienda Carrizalejo
Lomas de San Angel
Los Encinos
Mesa de la Corona, Sec. 1 y 2
Olinalá
Priv. Sierra Madre
Santa Engracia
Valle de San Angel "Sector Español"
Valle de San Angel "Sector Francés"
Valle de San Angel "Sector Mexicano"
Valle de san Angel "Sector Jardines"
Valle de Santa Engracia
Villas de Santa Engracia
 Joya de la Corona
Joya del Venado



Jueves
Ampliación Tampiquito
Balcones del Valle
Barrancas del Pedregal
Capistrano
Bosques de Valle Sec. 1, 2, 3, 4 y 5
Colinas de la Sierra Madre
Colonial de la Sierra
Del Valle Sec. Fátima
Fatima
Hacienda del Valle
Hacienda el Rosario
Hacienda Palo Blanco
Jardines Coloniales
La Cima
La Cooperativa
La Montaña Sec. 1, 2 y 3
La Ventana
Lomas del Rosario
Lomas de Tampiquito
Lomas del Valle
Lomas del Valle Sec. Convento
Mision del Rosario
Olímpico
Pedregal del Valle
Prados de la Sierra
Residencial La Cima
Residencial Sierra del Valle
Rincón de la Montaña
Sierra Nevada
Tampiquito
Villa Montaña
Villas del Pedregal
Villas del Valle

Viernes
Ampliación Valle del Mirador
Ampliación Canteras
Casco Urbano "NTE"
Corp. PROSER
Centro Histórico
Del Valle "OTE"
Jardines del Campestre
Jeronimo Siller
La Barranca
Linda Vista
Lomas del Valle
Montebello
Nemesio Garcia Naranjo
Privada Callejones
Residencial Chipinque Sec. 1, 2 y 3
Residencial San Agustín Sec. 1 y 2
Residencial Sta. Barbara
Rincon Colonial
Rincon de Carrizalejo
Rincon de Corregidora
San Francisco
Valle del Campestre
Valle de Chipinque
Villas de Aragón
Villas de Terrasol
Volkswagen
Mirador del Campestre
Los Soles

Sábado


El Obispo "NTE"
El Obispo "SUR"
Fomerrey 22 "NTE" San Pedro 400
Jesus M. Garza
Fomerrey 22 "SUR" San Pedro 400
Los Pinos 1 y 2
Los Sauces Sec. 1 y 2 "PTE"
Lazaro Garza Ayala
Revolución
Rincón de San Francisco
Unidad Habitacional San Pedro
Valle de Vasconcelos
Villas del Obispo
Vista Montaña Sec. 1, 2 y 3
Callejones  Capellanía, Ayala ,Arizpe
Sendas

Servicio con Reporte:
Lucio Blanco Sec. 1, 2 y 3
Plan de Ayala
Valle del Seminario
Luis echeverria
"""

def get_basura_vegetal():
    """Obtener Información de la basura vegetal, las rutas, y los días en caso de ser necesario.

    Returns:
        string: Informacion sobre la basura vegetal.
    """
    return TC