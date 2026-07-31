TC = """
INFORMACIÓN OFICIAL PARA ATENCIÓN SOBRE CECATI Y PROYECTO FORJA
Fuente: Carta Compromiso Familiar · Proyecto FORJA
Capacitación técnica certificada CMNL-CECATI · Ciclo agosto-diciembre 2026

RESUMEN EJECUTIVO
- El Proyecto FORJA es una capacitación técnica certificada por CECATI.
- Es un programa adicional, voluntario e independiente del bachillerato del Colegio.
- El bachillerato del Colegio sigue siendo gratuito.
- El programa consta de 3 módulos de 60 horas cada uno, para un total de 180 horas.
- La asistencia es de una jornada semanal de 5 horas.
- La metodología es 80% práctica.

QUÉ SE LE PUEDE DECIR A UN INTERESADO
- FORJA es una opción voluntaria de capacitación técnica certificada por CECATI para estudiantes del Colegio.
- No sustituye ni cambia la formación de bachillerato.
- El avance acreditado sí cuenta: cada módulo aprobado otorga constancia oficial con validez SEP.
- Si un módulo no se acredita, puede recursarse.

COSTOS OFICIALES RESPALDADOS POR EL DOCUMENTO
- Cuota CECATI por convenio institucional: $1,386.00 en pago único.
- Costo al público general referido en el documento: $5,000.00.
- Seguro de servicio médico contra accidentes: $100.00.
- Recurse de un módulo no acreditado: $800.00 ante CECATI.
- La cuota de transporte existe, pero el monto depende del plantel y en el documento aparece en blanco.

FECHAS Y PAGO
- La cuota CECATI debe pagarse a más tardar a finales de agosto de 2026.
- El documento no especifica una fecha exacta distinta a ese límite general.

ASISTENCIA Y ACREDITACIÓN
- La asistencia puntual es central para el programa.
- La acreditación depende directamente de la práctica en taller.
- Las inasistencias se identifican como la principal causa de no acreditación.
- Cada módulo acreditado genera constancia oficial con validez SEP.
- El avance acreditado no se pierde aunque después haya baja o no se acredite otro módulo.

BAJAS Y RECURSE
- Si el estudiante causa baja, conserva las constancias de los módulos acreditados.
- Las cuotas pagadas se rigen por las políticas del CECATI.
- Si no acredita un módulo, puede presentarlo nuevamente con costo de $800.00.

DISCIPLINA Y OPERACIÓN
- El estudiante debe sujetarse al reglamento del Colegio y a la normativa del CECATI.
- Esto aplica durante traslados, permanencia y jornada completa de capacitación.
- El acompañamiento se realiza bajo el instructor militar asignado.

MANEJO DE RECURSOS
- La cuota de capacitación se paga directamente al CECATI.
- Las cuotas de recuperación de transporte se administran a través del Patronato del Colegio.
- Ningún funcionario del plantel recibe ni maneja recursos de las familias.

SALUD Y SEGURIDAD
- La familia debe informar cualquier condición médica relevante del estudiante.
- Esa información sirve para la atención durante traslados y prácticas.
- El documento indica cobertura por seguro contra accidentes.

ACLARACIÓN IMPORTANTE SOBRE OTROS COBROS
- El estudiante inscrito en FORJA no cursa ni paga los estudios complementarios de promotor deportivo, promotor cultural y asistente contable por $600.00.
- Esto no afecta su trayectoria curricular.

DATOS QUE EL DOCUMENTO NO DEFINE
- No especifica el monto de transporte por plantel.
- No especifica especialidades disponibles.
- No especifica el día semanal de asistencia para cada estudiante.
- No especifica el CECATI asignado para cada alumno.
- No especifica criterios de selección o inscripción fuera de lo señalado en la carta.

GUÍA DE RESPUESTA
- Si preguntan qué es FORJA: explica que es una capacitación técnica voluntaria certificada por CECATI, adicional al bachillerato y con 3 módulos de 60 horas.
- Si preguntan cuánto cuesta: informa $1,386.00 de cuota CECATI, $100.00 de seguro y transporte variable por plantel.
- Si preguntan qué pasa si faltan: informa que las inasistencias son la principal causa de no acreditación.
- Si preguntan si pierden el avance: informa que no, los módulos acreditados conservan su constancia oficial.
- Si preguntan por recurse: informa que recursar un módulo no acreditado cuesta $800.00.
- Si preguntan por transporte, especialidad, día de asistencia o CECATI asignado: aclara que ese dato depende del plantel o del caso particular y no viene definido en la carta compartida.
"""


async def get_cecati_forja():
    """Obtener la carta compromiso familiar del Proyecto FORJA con CECATI.

    Returns:
        string: Información oficial sobre FORJA, CECATI, costos, asistencia y compromisos familiares.
    """
    return TC
