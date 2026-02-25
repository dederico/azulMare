
TC = """
Este documento contiene información sobre los requisitos, registros y colaboraciones en temas de voluntariado del municipio de San Pedro Garza García

Descripción del programa de voluntariado: 

Pregunta: Quiero información sobre el voluntariado
Respuesta: La Coordinación de Vinculación Social y Voluntariado, parte de la Dirección de Movilidad Social de la Secretaría de Desarrollo Social y Calidad de Vida, busca integrar una visión equitativa, inclusiva, justa y sostenible. A través de la interacción entre ciudadanía y gobierno, trabaja para concientizar y movilizar a la sociedad, mediante la colaboración en la construcción de soluciones conjuntas que hacen frente a las necesidades del municipio https://voluntarios.sanpedro.gob.mx/

Pregunta: ¿Cómo me puedo inscribir para ser voluntario?
Respuesta: Si te interesa ser parte del grupo de Voluntariado San Pedro, implementar tu iniciativa social o realizar alguna acción en conjunto contactanos al correo: voluntariado@sanpedro.gob.mx

Pregunta: ¿Cómo puedo proponer un proyecto social con el municipio?
Respuesta: Si te interesa ser parte del grupo de Voluntariado San Pedro, implementar tu iniciativa social o realizar alguna acción en conjunto contactanos al correo: voluntariado@sanpedro.gob.mx

Pregunta: ¿Dónde se encuentran las oficinas de los responsables del voluntariado?
Respuesta: Doña María Cantú 329 Col. La Leona C.P. 66217 SPGG, N.L.

"""


async def get_voluntarios():
    """Obtener informacion de voluntarios en caso de ser necesario.

    Returns:
        string: Informacion de los voluntarios.
    """
    return TC