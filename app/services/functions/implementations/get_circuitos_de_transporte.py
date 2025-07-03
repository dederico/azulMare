TC = """
Este documento contiene información sobre los circuitos de transporte del municipio de San Pedro Garza García

Pregunta: ¿Cuáles son los horarios de los circuitos de transporte del municipio?
Respuesta:
Circuito Poniente
Lunes a viernes de 7:00 a 19:00 horas
Circuito Sierra Madre
Lunes a viernes de 7:00 a 19:00 horas

Pregunta: Quisiera saber el recorrido del Circuito Poniente
Respuesta:
Soriana La Fama (Diaz Ordaz)
Clínica 58
Clínica 7
Centro de Salud 
Daltile 
Parque Clouthier
Gimnasio 400 
Secundaria 28 (Cobalto)
Comercial Treviño 
Tungsteno 
Centro Mover San pedro 400 
Casa de la cultura La Cima
Alcaldía Poniente 
Gimnasio La Raza



Pregunta: Quisiera saber el recorrido del Circuito Sierra Madre
Respuesta:
Puerta de Hierro (Gómez Morin)
Alfonso Reyes
Roberto Garza Sada
Monte Blanco
Alpino Chipinque 
Puente 1 
Puente 2 
Puente 3 
Uxmal 
Teotihuacan (Puente 4)
Olinalá 

"""

async def get_circuitos_de_transporte():
    """Obtener Información de los circuitos de transporte en caso de ser necesario.

    Returns:
        string: Informacion de los circuitos de transporte.
    """
    return TC