TC = """ 
Este documento contiene información sobre los requisitos y costos para participar en el Mercado de la Fregonería

Pregunta: ¿Cómo puedo ser expositor en San Pedro de Pinta/Mercado de la Fregonería?
Respuesta: La convocatoria para ser expositor en el 2025 se ha cerrado, la convocatoria para serlo en el 2026 se abre en noviembre de 2025. Para registrarse en lista de espera son necesarios dos requisitos:
⁠Ser residente del Municipio de San Pedro (y comprobarlo con INE o Comprobante de domicilio)
⁠Que tu producto sea artesanal; es decir que lo elabores tu mism@.
Para realizar tu registro, solo debes enviar un correo con estos dos puntos y describir tu producto, así como el objetivo o el interés de ingresar al Mercado de la Fregonería:
mercado.fregoneria@sanpedro.gob.mx
ASUNTO: Interés expositor Mercado de la Fregoneria (nombre de la persona interesada)

Pregunta: ¿Qué requisitos debo tener para ser expositor en San Pedro de Pinta/Mercado de la Fregonería?
Respuesta: La convocatoria para ser expositor en el 2025 se ha cerrado, la convocatoria para serlo en el 2026 se abre en noviembre de 2025 Para registrarse en lista de espera son necesarios dos requisitos:
⁠Ser residente del Municipio de San Pedro (y comprobarlo con INE o Comprobante de domicilio)
⁠Que tu producto sea artesanal; es decir que lo elabores tu mism@.
Para realizar tu registro, solo debes enviar un correo con estos dos puntos y describir tu producto, así como el objetivo o el interés de ingresar al Mercado de la Fregonería:
mercado.fregoneria@sanpedro.gob.mx
ASUNTO: Interés expositor Mercado de la Fregoneria (nombre de la persona interesada)

Pregunta: ¿Cuánto cuesta un stand en San Pedro de Pinta/Mercado de la Fregonería?
Respuesta: De manera bimestral el precio varía dependiendo de la categoría del producto en venta:
Expositores con servicio de uso de luz $3,500
Expositores con servicio de uso de gas $3,000
Expositores sin servicio de uso de luz $2,500
Expositores arte-objeto $2,000
Expositores corredor del arte $700

"""

async def get_mercado_fregoneria():
    """Obtener información sobre los requisitos y costos para participar en el Mercado de la Fregonería en caso de ser necesario.

    Returns:
        string: Informacion sobre los requisitos y costos para participar en el Mercado de la Fregonería.
    """
    return TC