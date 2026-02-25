

TC = """
Este documento contiene información sobre los contactos de los
Centros de Bienestar Animal de otros municipios del Áreas
Metropolitana de Monterrey
Pregunta: ¿Cuáles otros Centros de Bienestar Animal / Control Canino hay?
Respuesta:
● CBA Solidaridad Monterrey: 8151027405
● Santa Catarina: 8186761700
● San Nicolás: 8181581218
● Dirección de protección animal Escobedo: 8129683141
● Centro de Bienestar Animal Nuevo León: 8120332124 o 2108.
proteccion.animal@nuevoleon.com.mx
"""


async def get_centros_bienestar():
    """Obtener informacion de los centros de bienestar animal de otros municipios en caso de ser necesario.

    Returns:
        string: Informacion de centros de bienestar animal en el estado.
    """
    return TC