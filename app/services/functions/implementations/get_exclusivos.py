TC = """
Este documento contiene información sobre el Permiso Exclusivo Residencial 2026 en el municipio de San Pedro Garza García.

Pregunta: ¿Cómo puedo tramitar mi Exclusivo Residencial?
Respuesta: De manera virtual en el siguiente link:
https://exclusivo.sanpedro.gob.mx/

Pregunta: ¿Cuáles son los requisitos para tramitar mi exclusivo residencial?
Respuesta:
- No. de expediente catastral sin adeudo
- Identificación oficial INE
- Comprobante de domicilio, puede ser agua, luz o gas
- Carta petición dirigida a la Dirección de Movilidad
- Acuerdo de responsabilidad

Pregunta: ¿Cuál es el costo para tramitar mi exclusivo residencial?
Respuesta:
Refrendo de agosto a diciembre de 2026: 1,601.25 pesos
Instalación con delimitación horizontal técnica: 2,815.44 pesos

Pregunta: ¿Qué incluye el costo de instalación?
Respuesta:
- Vigencia hasta el 31 de diciembre de 2026
- Incluye la delimitación oficial con el folio rotulado sobre el pavimento

Pregunta: ¿Cuándo se realiza el pago?
Respuesta: El pago se realiza al final, una vez aprobada la inspección.

Pregunta: ¿El refrendo cuesta lo mismo todo el año?
Respuesta: No. El refrendo se cobra proporcional a los meses que restan del año, por eso baja conforme avanza el año.

Pregunta: ¿Hay algo importante que deba considerar antes de iniciar el trámite?
Respuesta: Sí. Tu expediente catastral debe estar al corriente del impuesto predial.
"""


async def get_exclusivos():
    """Obtener información del permiso Exclusivo Residencial 2026.

    Returns:
        string: Información del permiso Exclusivo Residencial 2026.
    """
    return TC
