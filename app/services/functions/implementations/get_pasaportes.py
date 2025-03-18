TC = """
Este documento contiene información sobre el trámite de pasaportes, costos, requisitos e información general

Pregunta: ¿Cuáles son los costos de los pasaportes?
Respuesta:
Vigencia 1 año: $885
Vigencia 3 años: $1,730
Vigencia 6 años: $2,350
Vigencia 10 años: $4,120
Cuota municipal: $450

Pregunta: ¿Cuáles son los requisitos para el tema de pasaportes?
Respuesta: 

Renovación de pasaporte para mayores de edad:
Copia de curp certificado
Copia de pasaporte
Pasaporte

Renovación de pasaporte para menor de edad:
Copia de curp certificado
Copia de pasaporte
Pasaporte
Original y copia de acta de nacimiento
Identificación del niño con fotografía (carta de pediatra/carta/constancia de estudios)
Copia de curp certificado de ambos padres
Copia de identificación de ambos padres (ine/pasaporte)
Se toma huellas y fotografías de ambos padres
El trámite no se podrá iniciar si ambos padres no están presentes

Primera vez de pasaporte para mayores de edad:
Copia de curp certificado
Original y copia de acta de nacimiento
Copia de identificación

Primera vez de pasaporte para menores de edad:
Copia de curp certificado
Original y copia de acta de nacimiento
Identificación del niño con fotografía (carta de pediatra/carta/constancia de estudios)
Copia de curp certificado de ambos padres
Copia de identificación de ambos padres (ine/pasaporte)

Pregunta: ¿Qué hago si perdí mi pasaporte?
Respuesta: En caso de robo/extravío de pasaporte, deberá levantarse denuncia para reportar el documento, y al agendar cita deberá ser como renovación de pasaporte sin documento.

"""

async def get_pasaportes():
    """Obtener información sobre el trámite de pasaportes, costos, requisitos e información general en caso de ser necesario.

    Returns:
        string: Información sobre el trámite de pasaportes, costos, requisitos e información general en caso de ser necesario.
    """
    return TC