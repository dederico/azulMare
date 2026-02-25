
TC = """
Este documento contiene información sobre los requisitos, registros y colaboraciones en temas de voluntariado del municipio de San Pedro Garza García

Descripción del programa de voluntariado: La Coordinación de Vinculación Social y Voluntariado, parte de la Dirección de Movilidad Social de la Secretaría de Desarrollo Social y Calidad de Vida, busca integrar una visión equitativa, inclusiva, justa y sostenible. A través de la interacción entre ciudadanía y gobierno, trabaja para concientizar y movilizar a la sociedad, mediante la colaboración en la construcción de soluciones conjuntas que hacen frente a las necesidades del municipio https://voluntarios.sanpedro.gob.mx/

Pregunta: ¿Cuáles son las actividades de voluntariado que tiene municipio?
Respuesta: Las actividades permanentes de voluntariado son las siguientes:

Instituto Municipal de Bienestar Animal (Garritas a la Obra)
Días: Miércoles, y viernes
Horario: 10:00 am a 12:00 pm

Actívate y Aprende
Días: Miércoles, Jueves y Viernes
Horario: 3:00 pm a 4:00 pm

Mural en tu escuela
Días: Miércoles, Jueves y Viernes
Horario: 4:00 pm a 7:00 pm

Guardabosques en el Parque Chipinque
Día: Sábado 28 de febrero
Horario: 9 am a 01:00 pm.

Pregunta: Quiero información sobre el voluntariado
Respuesta: Para registrarte, proponer un proyecto social o participar en las actividades de voluntariado del municipio puedes visitar la página web: https://voluntarios.sanpedro.gob.mx/, comunicarte al WhatsApp 8112146315 o visitar las oficinas en Doña María Cantú 329, Col. La Leona en un horario de 8:00 a 16:00 horas

Pregunta: ¿Cómo me puedo inscribir para ser voluntario?
Respuesta: Si te interesa ser parte del grupo de Voluntariado San Pedro, implementar tu iniciativa social o realizar alguna acción en conjunto contactanos al correo: voluntariado@sanpedro.gob.mx o comunicate al WhatsApp 8112146315

Pregunta: ¿Cómo puedo proponer un proyecto social con el municipio?
Respuesta: Si te interesa ser parte del grupo de Voluntariado San Pedro, implementar tu iniciativa social o realizar alguna acción en conjunto contactanos al correo: voluntariado@sanpedro.gob.mx o comunicate al WhatsApp 8112146315

Pregunta: ¿Dónde se encuentran las oficinas de los responsables del voluntariado?
Respuesta: Doña María Cantú 329 Col. La Leona C.P. 66217 SPGG, N.L.


"""


async def get_voluntarios():
    """Obtener informacion de voluntarios en caso de ser necesario.

    Returns:
        string: Informacion de los voluntarios.
    """
    return TC