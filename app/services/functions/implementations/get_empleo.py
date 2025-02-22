
TC = """
Este documento contiene información sobre la bolsa de trabajo del municipio de San Pedro Garza García

Pregunta: ¿Cuál es la bolsa de trabajo del municipio?
Respuesta:
-	Página web: https://empleo.sanpedro.gob.mx/pages/de/index.aspx
-	Correo electrónico: empleo@sanpedro.gob.mx

Pregunta: ¿Cómo puedo inscribirme como empresa para la bolsa de trabajo del municipio?
Respuesta:
-	Página web: https://empleo.sanpedro.gob.mx/pages/de/index.aspx
-	Correo electrónico: empleo@sanpedro.gob.mx

"""

async def get_empleo():
    """Obtener informacion de bolsa de trabajo en caso de ser necesario.

    Returns:
        string: Informacion de bolsa de trabajo.
    """
    return TC