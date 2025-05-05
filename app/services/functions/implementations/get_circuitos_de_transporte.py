TC = """
Este documento contiene información sobre los circuitos de transporte
del municipio de San Pedro Garza García
Pregunta: ¿Cuáles son los horarios de los circuitos de transporte del municipio?
Respuesta:
● Circuito Poniente
○ Lunes a viernes de 7:00 a 19:00 horas
● Circuito Sierra Madre
○ Lunes a viernes de 7:00 a 19:00 horas
● Circuito Valle
○ Lunes a miércoles de 8:00 a 20:00 horas
○ Jueves a sábado de 8:00 a 23:00 horas

Pregunta: Quisiera saber el recorrido del Circuito Poniente
Respuesta:
● Soriana La Fama (Diaz Ordaz)
● Clínica 58
● Clínica 7
● Centro de Salud
● Daltile
● Parque Clouthier
● Gimnasio 400
● Secundaria 28 (Cobalto)
● Comercial Treviño
● Tungsteno
● Centro Mover San pedro 400
● Casa de la cultura La Cima
● Alcaldía Poniente
● Gimnasio La Raza

Pregunta: Quisiera saber el recorrido del Circuito Sierra Madre
Respuesta:
● Puerta de Hierro (Gómez Morin)
● Alfonso Reyes
● Roberto Garza Sada
● Monte Blanco
● Alpino Chipinque
● Puente 1
● Puente 2
● Puente 3
● Uxmal
● Teotihuacan (Puente 4)
● Olinalá

Pregunta: Quisiera saber el recorrido del Circuito Centro Valle

Respuesta:
● Río Grijalva esquina con Río Amazonas
● Río Mississippi esquina con Río Grijalva
● Río Mississippi esquina con Tamazunchale
● Río Moctezuma en Parque Mississippi
● Calzada del Valle (afuera de Mr. Pampas)
● Gomez Morín (frente a Palacio de Hierro
● Arboleda (frente al Hotel Marriot)
● Plaza Chroma
● Punto Valle (por Río Missouri)
● Río Moctezuma
● Río Amazonas
"""

async def get_circuitos_de_transporte():
    """Obtener Información de los circuitos de transporte en caso de ser necesario.

    Returns:
        string: Informacion de los circuitos de transporte.
    """
    return TC