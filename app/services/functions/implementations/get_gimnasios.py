
TC = """
Este documento contiene información sobre las actividades, programas, servicios, requisitos, ubicaciones e información general sobre la Dirección de Deportes del municipio de San Pedro Garza García

Pregunta: ¿Cuáles son los gimnasios municipales?
Respuesta: 

Centro de Desarrollo Integral (CDI)
Ubicación: Lázaro Garza Ayala 1001, Col. Lázaro Garza Ayala https://maps.app.goo.gl/nY7JEduWtGGAEwW6A
Instalaciones: Gimnasio
Horario: De 6:00 a 21:00 horas
Télefono: 8110524343
Link de registro: https://forms.gle/32WubmuvMg5V3XZU7

Unidad Deportiva San Pedro 400
Ubicación: Av. Manuel Jesus Clouthier 157, Col. San Pedro 400 https://maps.app.goo.gl/aN5bJhVZLfCtd92K6
Instalaciones: Gimnasio y Alberca
Horario: De 6:00 a 21:00 horas
Teléfono: 8183158814
Link de registro: https://forms.gle/qytDKdrDUgHgDfzc6

Unidad Deportiva La Raza
Ubicación: Av. Manuel Jesus Clouthier y Platino, S/N, Col. San Pedro 400 https://maps.app.goo.gl/2ga33z7wCmSDoBeC6
Instalaciones: Gimnasio y Alberca
Horario: De 7:00 a 21:00 horas
Teléfono: 8182425034
Link de registro: https://forms.gle/12eNQXiHr5RfJmh57

Unidad Deportiva Vista Montaña
Ubicación: Nicéforo Zambrano S/N, Col. Vista Montaña https://maps.app.goo.gl/bco8PaxQA2rgsaLJ7
Instalaciones: Gimnasio
Horario: De 7:00 a 21:00 horas
Teléfono: 8189891759
Link de registro: https://forms.gle/kcehncckgR8VNAWaA

Unidad Deportiva El Obispo
Ubicación: Landon 820, Col. Villa del Obispo https://maps.app.goo.gl/2xTT8nLMFtQR6t4n8
Instalaciones: Gimnasio
Horario: De 7:00 a 21:00 horas
Teléfono: 
Link de registro: https://forms.gle/iuVkSt9T6izxkmJr7

Unidad Deportiva Tampiquito
Ubicación: Plutarco Elías Calles y Amatista S/N, Col. Lomas de Tampiquito https://maps.app.goo.gl/LymTfHNHLFidq5dw9
Instalaciones: Gimnasio
Horario: 7:00 a 21:00 horas
Teléfono: 
Link de registro: https://forms.gle/Ax5uHnNUCPszc7nJ9

Unidad Deportiva Jesús D. González
Ubicación: Libertad 206, Col. Casco Urbano 
Instalaciones: Gimnasio
Horario: 6:00 a 22:00 horas
Teléfono: 
Link de registro: https://forms.gle/b27PEQzvgLFgFNsy8

Unidad Deportiva Oriente
Ubicación: Paseo Irma y Paseo Olga	 S/N, Col. Ampliación Valle del Mirador
Instalaciones: Gimnasio
Horario: De 6:00 a 22:00 horas

Centro Deportivo FUD
Ubicación: Av María Cantú Treviño 329, Col. La Leona
Instalaciones: Gimnasio
Horario: 6:00 a 21:00 horas
Teléfono: 8186765356
Link de registro: https://forms.gle/S3EGzJEEWhqjZPRj7

Pregunta: ¿Dónde se encuentran las oficinas de deportes?
Respuesta:

Av. María Cantú Treviño 329, Col. La Leona
Dirección de Deportes
Coordinación de Deporte Inclusivo
Coordinación de Deporte Social
Coordinación Deporte Competitivo

Av. Clouthier y Platino S/N, Col. San Pedro 400
Ligas Deportivas

Pregunta: ¿Cuáles son los costos por actividades deportivas?
Respuesta:

Actividad deportiva mensual
Residentes de SPGG: $200.00
Residentes de otros municipios: $500.00
Actividad extra
Residentes de SPGG: $100.00
Residentes de otros municipios: $200.00
Paquete familiar (2 personas con una actividad deportiva mensual)
Residentes de SPGG: $300.00
Residentes de otros municipios: $800.00
Paquete familiar (3 a 5 personas en una actividad deportiva mensual) no aplican actividades acuáticas ni gimnasia olímpica
Residentes de SPGG: $400.00
Residentes de otros municipios: $1000.00
Reposición de credencial
Residentes de SPGG: $30.00
Residentes de otros municipios: $30.00
Notas:
Actividades acuáticas y gimnasio no aplican en paquetes familiares.
Personas mayores de 60 años quedan exentos de cobro mensual

"""


async def get_gimnasios():
    """
    Este documento contiene información sobre las actividades, programas, servicios, requisitos, ubicaciones e información general sobre la Dirección de Deportes del municipio de San Pedro Garza García

    Returns:
        string: Información sobre ubicaciones, horarios y contactos de los gimnasios y áreas deportivas municipales.
    """
    return TC