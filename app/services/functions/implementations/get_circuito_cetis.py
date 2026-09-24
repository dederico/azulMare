TC = """
Este documento contiene información sobre el Circuito CETIS del municipio de San Pedro Garza García

Pregunta: ¿Cuáles son las paradas y horarios del circuito CETIS?
Respuesta:

Entradas
Parque Los Rosales:
Ubicación: Azufre entre Aluminio y Uranio
Entrada 1: 06:30 a. m.
Entrada 2: 01:30 p. m.
Grafito:
Ubicación: Fierro y Grafito
Entrada 1: 06:31 a. m.
Entrada 2: 01:31 p. m.
Estación Alcaldía Poniente:
Ubicación: Cobalto y Uranio
Entrada 1: 06:34 a. m.
Entrada 2: 01:34 p. m.
Estación Platino:
Ubicación: Cobalto y Platino
Entrada 1: 06:36 a. m.
Entrada 2: 01:36 p. m.
Estación La Retama:
Ubicación: Zapata y Niceforo Zambrano
Entrada 1: 06:38 a. m.
Entrada 2: 01:38 p. m.
El Obispo:
Ubicación: Zapata y Clouthier
Entrada 1: 06:40 a. m.
Entrada 2: 01:40 p. m.
Parque Clouthier:
Ubicación: Parque Clouthier
Entrada 1: 06:42 a. m.
Entrada 2: 01:42 p. m.
Estación Daltile:
Ubicación: Corregidora y Díaz Ordaz
Entrada 1: 06:44 a. m.
Entrada 2: 01:44 p. m.
Centro de Salud:
Ubicación: Corregidora y Lucio Blanco
Entrada 1: 06:45 a. m.
Entrada 2: 01:45 p. m.
CETIS 66:
Ubicación: 5 de Mayo entre Padre Mier y Siller
Entrada 1: 06:50 a. m.
Entrada 2: 01:50 p. m.
Salidas
CETIS 66:
Ubicación: 5 de Mayo entre Padre Mier y Siller
Salida 1: 02:00 p. m.
Salida 2: 08:20 p. m.
Centro de Salud:
Ubicación: Corregidora y Lucio Blanco
Salida 1: 02:06 p. m.
Salida 2: 08:26 p. m.
El Obispo:
Ubicación: Zapata y Clouthier
Salida 1: 02:10 p. m.
Salida 2: 08:30 p. m.
Estación La Retama:
Ubicación: Zapata y Niceforo Zambrano
Salida 1: 02:13 p. m.
Salida 2: 08:33 p. m.
Estación Platino:
Ubicación: Cobalto y Platino
Salida 1: 02:15 p. m.
Salida 2: 08:35 p. m.
Estación Alcaldía Poniente:
Ubicación: Cobalto y Uranio
Salida 1: 02:17 p. m.
Salida 2: 08:37 p. m.
Parque Los Rosales:
Ubicación: Azufre entre Aluminio y Uranio
Salida 1: 02:20 p. m.
Salida 2: 08:40 p. m.
Pregunta: ¿Cuáles son los requisitos para subir al Circuito CETIS?
Respuesta: Ser estudiante del CETIS y portar uniforme oficial de la institución.
"""

async def get_circuito_cetis():
    """Obtener Información del circuito CETIS 66 en caso de ser necesario.

    Returns:
        string: Informacion del circuito CETIS.
    """
    return TC