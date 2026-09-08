TC = """
Este documento contiene información del proceso de credencialización y toma de fotografía para credencial del Colegio Ciudadano de Excelencia y Disciplina en Nuevo León.

¿Cuál es el proceso general de credencialización?
1. Enterarse de la fecha de toma de fotografía por conducto del plantel respectivo.
2. Acudir a la toma de fotografía, de preferencia con la playera beige del uniforme.
3. Cubrir el costo de la credencial.
4. Esperar la entrega de la credencial en los primeros días de clases, en el mismo plantel.

¿Qué fechas de fotografía de primer semestre se compartieron por plantel?
Plantel García: del 5 al 7 de agosto de 2026.
Plantel Juárez: 30 y 31 de julio de 2026.
Plantel Sabinas: 5 de agosto de 2026.
Plantel San Nicolás: 5 de agosto de 2026.
Plantel Galeana: 3 de agosto de 2026.
Plantel Pesquería: 31 de julio de 2026.
Plantel Montemorelos: del 3 al 6 de agosto de 2026.
Plantel Linares: del 4 al 7 de agosto de 2026.

¿Hay planteles sin fecha compartida en esta referencia?
Sí. En esta información no se compartió fecha específica para Monterrey, Apodaca ni Escobedo.

Si preguntan por credencialización, toma de fotografía, foto para credencial o entrega de credenciales, esta es la referencia vigente compartida.
"""


async def get_credencializacion_colegio_militarizado():
    """Obtener información de credencialización y toma de fotografía del Colegio Ciudadano de Excelencia y Disciplina en Nuevo León.

    Returns:
        string: Proceso general y fechas compartidas de fotografía por plantel.
    """
    return TC
