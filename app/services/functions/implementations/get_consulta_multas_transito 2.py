


TC = """
Este documento contiene información sobre la consulta y pago de
multas de tránsito
Pregunta: ¿En qué página puede pagar una multa de tránsito?
Respuesta: Consulta de Multas de Tránsito
- https://www.sanpedro.gob.mx/multas-de-transito es necesario tener a la mano el
número de placas del vehículo
Si desea: Consulta de Pagos de Multas de Tránsito por Internet (Solo los pagos realizados
con Tarjeta de Crédito).
Pregunta: ¿Dónde puedo revisar una multa de tránsito?
Respuesta:
- Vía telefónica a 81-8988-1100 Ext. 6013
- Presencial:
- Coordinación de Ingresos Diversos. Juárez y Libertad S/N 2do. Piso del
Palacio Municipal. Tel: 84004400 Extensión: 4584
- Oficina de la Tesorería en Seguridad Pública. C2 San Pedro. Ave. Lazaro
Cardenas 2232, Valle Oriente. Tel: 84004584
Pregunta: ¿Dónde puedo solicitar una revisión de mi multa?
Respuesta: Puede dirigirse a las oficinas de Justicia Cívica para revisar su situación y
revisar las alternativas a la multa. C2 San Pedro, Lázaro Cárdenas 2232, Valle Oriente.
"""

async def get_consultas_multas_transito():
    """Obtener informacion de consultas sobre multas de transito en caso de ser necesario.

    Returns:
        string: Informacion de las multas de transito.
    """
    return TC