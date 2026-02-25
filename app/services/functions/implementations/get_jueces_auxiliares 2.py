TC = """
Este documento contiene información sobre trámites y contactos de Jueces Auxiliares
Pregunta: ¿Qué trámites realiza un juez auxiliar?
Respuesta: A continuación te compartimos los distintos tipos de constancias que expiden
los Jueces Auxiliares:
● Constancia de Residencia: Sirve para comprobar tu Residencia o Domicilio / se
solicita cuando tu INE, tiene domicilio diferente al que vives, no está actualizado, o
rentas y el comprobante no se encuentra a tu nombre.
● Constancia de Abandono de hogar: Sirve como constancia de hechos para
comprobar la ausencia de algún miembro de la familia / Se solicita cuando algún
miembro de la familia abandonó el hogar.
● Constancia de Ingresos: Sirve para comprobar los ingresos que percibes / Se solicita
cuando no cuentas con recibos de nómina o estados de cuenta bancarios.
● Constancia de Identidad: Sirve para comprobar tu Identidad / Se solicita cuando no
cuentas con acta de nacimiento expedida por el registro civil, perdida de tu INE, o
cuando existe un error en algún documento oficial.
● Constancia de Soltería: Sirve para comprobar su estado civil en vida o en caso de
fallecimiento / Se solicita cuando requieres comprobar que no tienes dependientes
económicos (esposa, cónyuge e hijos).
● Constancia de Hechos: Sirve para hacer constar un acontecimiento o cualquier
hecho suscitado en su Sector K / Se solicita cuando el ciudadano requiere hacer
constar o tener alguna evidencia de un acontecimiento relevante.
● Carta certificada: Si necesitas tu carta certificada comunícate al 81 8400 4412 con la
Secretaría del Replublicano Ayuntamiento para mayor información.
Pregunta: ¿Qué documentos necesito para el trámite con el Juez Auxiliar?
Respuesta: Ten preparados los siguientes documentos en original y con una copia para tu
cita con el Juez(a):
● Identificación Oficial del solicitante
● Comprobante de domicilio del solicitante con antigüedad no mayor a 3 meses.
● INE vigente del primer testigo. El testigo no puede ser un familiar consanguíneo.
● INE vigente del segundo testigo. El testigo no puede ser un familiar consanguíneo.
● Comprobante de domicilio del primer testigo con antigüedad no mayor a 3 meses.
● Comprobante de domicilio del segundo testigo con antigüedad no mayor a 3 meses.
Pregunta: ¿En qué horario puedo consultar mi Juez Auxiliar?
Respuesta: Horario de atención. De lunes a viernes de 08:00 a 16:00 horas.
Pregunta: ¿Cómo puedo saber quien es mi Juez Auxiliar?
Respuesta: No se pueden proporcionar los datos por este medio, puedes comunicarte a los
siguientes contactos:
- Enrique Luis Cardona Muñoz. Coordinador de Jueces Auxiliares.Tel: 8184782916 -
Ext. 2961. Correo electrónico: enrique.cardona@sanpedro.gob.mx
- Diana Janeth Guajardo González. Tel: 8184782916 - Ext. 2961.
diana.guajardo@sanpedro.gob.mx

- Andrea Janeth Azpeitia Benavides. Tel: 8184782945 - Ext. 2945
andrea.azpeitia@sanpedro.gob.mx
"""

async def get_jueces_auxiliares():
    """Obtener informacion de información sobre trámites y contactos de Jueces Auxiliares en caso de ser necesario.

    Returns:
        string: informacion de información sobre trámites y contactos de Jueces Auxiliares.
    """
    return TC