
TC = """
Este documento contiene información sobre denuncias de maltrato animal

Pregunta: ¿Cómo puedo denunciar maltrato animal?
Respuesta: Las denuncias de maltrato animal corresponden a la Secretaría de Medio Ambiente de Nuevo León, compartimos los siguientes requisitos y contactos:
-	Teléfono: 8120332124
-	Horarios: Lunes a Viernes de 9:00 a 17:00 horas
-	Requisitos:
-	Nombre y teléfono del quejoso
-	Breve descripción de los hechos
-	Domicilio donde se está suscitando el maltrato
-	Una fotografía que evidencie el maltrato y una donde aparezca el domicilio reportado (opcional), los cuáles deberán ser enviadas al correo proteccion.animal@nuevoleon.gob.mx o a la página de facebook Secretaría de Medio Ambiente
-	Horario en que se encuentran los propietarios de los animales que aparentemente están siendo maltratados.

"""


async def get_denuncia_maltrato_animal():
    """Obtener informacion de denuncias de maltrato animal en caso de ser necesario.

    Returns:
        string: Informacion de la denuncias de maltrato animal.
    """
    return TC