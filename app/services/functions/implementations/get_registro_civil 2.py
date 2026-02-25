TC = """
Este documento contiene información sobre las oficialías del registro civil que se encuentran en el municipio de San Pedro Garza García

Pregunta: ¿Cuáles son las oficialías que se encuentran en el municipio?
Respuesta: Las oficialías son de competencia del gobierno estatal, de acuerdo con la última información actualizada el 30 de octubre de 2024 las oficialías en el municipio de San Pedro Garza García son las siguientes:
Oficialía 1: Cobalto y Uranio s/n, Edificio Alcaldía Poniente, Planta Baja, San Pedro 400, San Pedro Garza García, N.L.
Teléfono: 81 81 84 78 20 Ext. 2056
Horario de atención: 8:00 am a 3:00 pm
Oficialía 2: Humberto Lobo 455-A, Col. Del Valle, San Pedro Garza García, N. L.
Teléfono: 81 20 20 57 40
Horario de atención: 8:00 am a 3:00 pm
Oficialía 3: Mississipi No.147, 2o. Piso, Col. Del Valle, San Pedro Garza García, N.L
Teléfono: 81 31 43 04 74
Horario de atención: 8:00 am a 3:00 pm
Oficialía 4: Vasconcelos No. 1561-B, Col. Mira Sierra, San Pedro Garza García, N. L.
Teléfono: 81 83 38 98 67
Horario de atención: 8:00 am a 3:00 pm
Oficialía 5: Av. Clouthier y Calle Oro, Col. San Pedro, San Pedro Garza García, N. L.
Teléfono: 81 83 15 92 90
Horario de atención: 8:00 am a 3:00 pm

Pregunta: ¿Cómo puedo obtener más información sobre las oficialías?
Respuesta: Comunícate al conmutador en el teléfono 81-2033-2880 o bien envía un inbox a la página de Facebook de la Dirección General del Registro Civil del Estado de Nuevo León. Página web: https://www.nl.gob.mx/es/oficialiasderegistrocivil
"""

async def get_registro_civil():
    """Obtener Información información sobre horarios y servicios brindados en el Miércoles Ciudadano de San Pedro Garza García en caso de ser necesario.


    Returns:
        string: Información información sobre horarios y servicios brindados en el Miércoles Ciudadano.
    """
    return TC