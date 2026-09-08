TC = """
Este documento contiene información sobre admisiones al Colegio Ciudadano de Excelencia y Disciplina en Nuevo León dentro del Proceso de Asignación de Espacios en la Educación Media Superior del Estado de Nuevo León para ingreso en agosto de 2026.

¿En qué consiste el proceso?
El ingreso se realiza por medio del Proceso de Asignación de Espacios en la Educación Media Superior del Estado de Nuevo León. El registro es en línea y la asignación considera preferencias de plantel y puntaje obtenido.

¿Cuáles son las fechas clave?
Registro oficial: del 13 de marzo de 2026 a las 15:00 horas al 30 de abril de 2026 a las 23:59 horas.
Aplicación del diagnóstico: sábado 6 de junio de 2026.
Publicación de resultados: a partir del 29 de junio de 2026.
Inicio previsto de clases: agosto de 2026.

¿Cuál es el costo?
La aportación del proceso es de $636.00 MXN.

¿Cómo se realiza el registro?
1. Ingresar a UANL, sección Aspirantes, Registro de aspirantes junio 2026.
2. Capturar datos básicos para descargar la hoja de pre registro con número de registro y contraseña.
3. Entrar a captura de encuestas para completar datos personales y socioeconómicos.
4. Cargar fotografía, identificación, carta de consentimiento y CURP.
5. Realizar el pago en la institución bancaria indicada en la hoja de pre registro.
6. Regresar a captura de encuestas para descargar el pase de ingreso al diagnóstico.

¿Cómo se asignan los lugares?
La asignación toma en cuenta el puntaje y las preferencias de plantel. Si no hay espacio en la primera opción, se analizan las demás opciones registradas. Si ninguna opción tiene lugar, puede asignarse un plantel con disponibilidad.

¿Cómo se consultan los resultados?
La carta de resultado se descarga con número de registro y contraseña. La carta indica el plantel asignado y las instrucciones para inscripción.

¿Dónde se puede pedir ayuda oficial?
Centro de Evaluaciones UANL, Ciudad Universitaria, San Nicolás de los Garza, Nuevo León.
Horario: lunes a viernes de 08:00 a 15:00 horas.
Correo: registro.prepas@uanl.mx
Teléfonos: +52 81 8329 4069, +52 81 1340 4435, +52 81 1340 4436 y +52 81 1340 4437.
WhatsApp: 8111259702
Twitter: @aspirantes_uanl

Responsable de la convocatoria: Centro de Evaluaciones UANL.
Última actualización oficial compartida: 13 de febrero de 2026.
"""


async def get_admisiones_colegio_militarizado():
    """Obtener información sobre admisiones al Colegio Ciudadano de Excelencia y Disciplina en Nuevo León.

    Returns:
        string: Información del proceso de admisión y asignación de espacios 2026.
    """
    return TC
