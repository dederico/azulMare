

TC = """
Este documento contiene información sobre clases y talleres en los centros comunitarios / centros MOVER de San Pedro Garza García. 

Pregunta: ¿Cuáles son los centros comunitarios / MOVER del municipio?
Respuesta:
- El Obispo: Corregidora y Eulalio Guzmán, El Obispo, San Pedro Garza García
- Jesús M. Garza: Francisco Villa y Morones Prieto S/N, Col. Jesús M. Garza
- Los Pinos: Francisco I. Madero, Los Pinos 2o Sector, 66239 San Pedro Garza García, N.L.
- Luis Echeverría: Av. Corregidora 301, Lucio Blanco 2o Sector, 66233 San Pedro Garza García, N.L.
- Revolución: Plan de Guadalupe, Revolución 3ER Sector, 66219 San Pedro Garza García, N.L.
- Santa Elena: Priv. Allende 501, Santa Elena, 66233 San Pedro Garza García, N.L.
- San Pedro 400: Uranio 602, San Pedro 400, 66210 San Pedro Garza García, N.L.
- Villas del Obispo: Landon 820-601, Villa del Obispo, 66214 San Pedro Garza García, N.L.
- Zona Oriente: P.º Esperanza 980, Ampliación Valle del Mirador, 66260 San Pedro Garza García, N.L.

Pregunta: ¿Cuál es el contacto para registrarse en las clases?
Respuesta: Teléfono: 81 8400 2791

Pregunta: ¿Cuáles son los talleres / clases que brindan en los centros comunitarios?
Respuesta:
- Belleza
- Repostería
- Corte y confección
- Huertos
- Mini Chef
- Bailoterapia
- Yoga
- Danzón

Pregunta: ¿Cuáles son los requisitos para las clases / talleres?
Respuesta:
- Adultos:
- INE
- CURP
- Comprobante de domicilio
- Niños:
- Acta de nacimiento
- CURP
- Comprobante de domicilio
- INE del tutor
"""


async def get_centros_comunitarios():
    """Obtener informacion del directorio de centros comunitarios en caso de ser necesario.

    Returns:
        string: Informacion de los centros comunitarios.
    """
    return TC