
TC = """
Este documento contiene información sobre estacionamiento para
residentes en zonas de parquímetros

Pregunta: ¿Cuáles son los requisitos para tener estacionamiento en la zona de
parquímetros?
Respuesta: Con fundamento en el Artículo 32. A los Residentes con domicilio en la Zona
de Parquímetros, que cuenten con cochera en su inmueble, la Secretaría de Finanzas y
Tesorería concederá el derecho a estacionar hasta 2-dos vehículos por vivienda, mediante
el pago de la Tarifa preferencial ($1800 y fracción y segundo $2500 y fracción, en total sería
un aproximado de $4000 por los dos autos de forma anual). Zona regulada sin cochera, un
permiso sin costo, presentando la documentación. Y puede dar de alta otro auto, pero este
segundo generaría un costo aproximado de $1800. Lo anterior para residentes con
vehículos en la Zona de Parquímetros correspondiente a su domicilio.
Para tales efectos, se otorgará a los residentes de la Zona de Parquímetros, un permiso con
vigencia de hasta 1-un año en formato físico o digital, para lo cual, deberán sujetarse a los
siguientes requisitos:
I. Se tramitarán hasta 2-dos permisos por inmueble y serán intransferibles para otros
vehículos;
II. Presentar solicitud por escrito en la que manifiesten la necesidad de espacio para
estacionamiento del inmueble en que habitan; no podrá exceder de 01-un Vehículo por
solicitud, adjuntando la siguiente documentación;
a) Copia de la tarjeta de circulación vigente del Vehículo;
b) Copia reciente de comprobante de domicilio, con fecha de expedición no mayor a
60-sesenta días naturales;
c) Copia simple del pago de predial al corriente y contrato de arrendamiento, en el caso de
ser arrendatarios;
d) Copia de identificación oficial con fotografía vigente;
e) Copia de licencia de conducir vigente;
f) Croquis de ubicación del inmueble; y
g) El vehículo que se registre no deberá contar con adeudos anteriores.
III. El otorgamiento de los beneficios a que se refiere este Capítulo está sujeto al
cumplimiento de los requisitos por parte del solicitante;
IV. La Secretaría de Finanzas y Tesorería proporcionará al solicitante el permiso
correspondiente, así como un distintivo impreso o electrónico que contendrá la matrícula del
Vehículo autorizado, el periodo de vigencia, los días y el horario de ocupación y la Zona de
Parquímetros en la cual se le autoriza a estacionar el Vehículo. El distintivo deberá
colocarse en el interior del Vehículo autorizado, en la parte inferior del parabrisas del mismo,
del lado del conductor, siempre a la vista desde el exterior del Vehículo;
V. La autorización del beneficio será expedida para la Zona de Parquímetros en donde se
encuentre ubicado el inmueble correspondiente; quedando prohibido colocar señales,
pintura o dispositivos de tránsito, tales como boyas, bordos, barreras o separar de cualquier
forma espacios para estacionar vehículos en la Vía pública;
VI. Será expedido por periodos anuales, comprendidos de enero a diciembre de cada año; y

VII. En ningún caso se otorgará permiso renovable para residentes con vehículos con
placas de circulación foráneas o extranjeras.
Se hará una visita de campo al domicilio mencionado para realizar el Vo.Bo., así mismo se
tomarán fotografías de la zona.
Nota: Este permiso no se autoriza para oficinas, locales comerciales o de negocios.
"""


async def get_parquimetros():
    """Obtener informacion de estacionamiento para residentes en zonas de parquímetros en caso de ser necesario.

    Returns:
        string: Informacion de estacionamiento para residentes en zonas de parquímetros.
    """
    return TC