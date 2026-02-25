TC = """
Este documento contiene información sobre los museos ubicados en el municipio de San Pedro Garza García y recomendaciones de otros museos de interés cultural

Preguntas: ¿Cuáles son los museos del municipio? / ¿Qué actividades puedo hacer en San Pedro? / ¿Qué museos me recomiendas visitar?

Museo Antiguos Mexicano

Pregunta: ¿Dónde se encuentra el Museo Antiguos Mexicanos?
Respuesta: Libertad 116 Ote, Centro de San Pedro

Pregunta: ¿Cuál es el costo del Museo Antiguos Mexicanos?
Respuesta: El acceso es gratuito, solo se requiere reservación en: https://museoarqueologico.sanpedro.gob.mx/

Pregunta: ¿Cuál es el horario del Museo Antiguos Mexicanos?
Respuesta: Martes a Domingo de 10:00 am a 7:00 pm

Otros museos

Pregunta: ¿Qué otros museos puedo visitar en San Pedro?
Respuesta: La siguiente recomendación de museos no son de administración municipal, sin embargo pueden ser de tu interés:

Museo La Milarca
Dirección: Ubicado en Eugenio Garza Lagüera #400 entre Rufino Tamayo y María Izquierdo, dentro del Parque Rufino Tamayo, Zona Valle Oriente, en el Municipio de San Pedro Garza García.
Horario:
Martes a viernes de 2:00 pm a 7:00 pm
Sábados y domingos de 10:00 am a 8:00 pm
Costo: Para consultar costos te recomendamos consultarlo directamente en la página web del museo


"""

async def get_info_museos():
    """Obtener Información de los museos de San Pedro Garza García en caso de ser necesario.

    Returns:
        string: Informacion sobre los museos de San Pedro Garza García.
    """
    return TC