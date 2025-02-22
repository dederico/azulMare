

TC = """
Este documento contiene información sobre la Carta de Radicación para personas morales

Pregunta: ¿Cómo puedo tramitar mi carta de radicación?
Respuesta: Municipio realiza carta de radicación para personas físicas mediante su juez auxiliar. 
En el caso de las personas morales ninguna dependencia municipal está facultada para comprobar su domicilio o radicación en el municipio. 
Lo que podemos sugerir es que solicite a un notario público una carta para comprobar el domicilio fiscal, o que consulte ante el SAT alguna otra opción para poder comprobar su domicilio.

"""


async def get_carta_radicacion():
    """Obtener informacion de carta de radicación en caso de ser necesario.

    Returns:
        string: Informacion de la carta de radicación.
    """
    return TC