TC = """
Este Documento contiene información sobre el Permiso  Exclusivo Residencial 2026  en el municipio de San Pedro Garza García

Pregunta: ¿Cómo puedo tramitar mi Exclusivo Residencial?
Respuesta: De manera virtual en el siguiente link: https://exclusivo.sanpedro.gob.mx/

Pregunta: ¿Cuáles son los requisitos para tramitar mi exclusivo residencial?
Respuesta:
No. de expediente catastral (Sin Adeudo)
Identificación oficial (INE)
Comprobante de domicilio (Agua, luz o gas)
Carta petición dirigida a la Dirección de Movilidad
Acuerdo de responsabilidad

Pregunta: ¿Cuál es el costo para tramitar mi exclusivo Residencial?
Respuesta:
Refrendo (Agosto-Diciembre) $1,601.25
Instalación (delimitación horizontal técnica) $2,815.44
Vigencia hasta el 31 de diciembre de 2026
Incluye la delimitación oficial con el folio rotulado sobre el pavimento.
El pago se realiza al final, una vez aprobada la inspección.
El refrendo se cobra proporcional a los meses que restan del año (por eso baja conforme avanza el año).
Importante: Tu expediente catastral debe estar al corriente del impuesto predial.
Pregunta: ¿Dónde se ubican las oficinas de Movilidad?
Respuesta: Independencia 233 cruz con Corregidora, Casco Urbano
Pregunta: ¿Cómo puedo conseguir una pensión de parquímetro?
Respuesta: Las pensiones de parquímetros son únicamente para residentes, se puede comunicar al 8189881157 o acudir a las oficinas ubicadas en Independencia 233 cruz con Corregidora, Casco Urbano


"""


async def get_exclusivos():
    """Obtener información del permiso Exclusivo Residencial 2026.

    Returns:
        string: Información del permiso Exclusivo Residencial 2026.
    """
    return TC
