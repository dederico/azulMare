
TC = """
Este documento contiene información sobre los centros de reciclaje del municipio de San Pedro Garza García

Pregunta: ¿Qué puedo dejar en los centros de reciclaje?
Respuesta:
-	Sí se recibe:
-	Vidrio (Botellas y recipientes): Es muy importante depositarlos sin bolsa en los contenedores y enjuagados.
-	Cartón: Te recomendamos compactar y desarmar desde tu casa, así será más rápido para ti y haremos un uso eficiente del contenedor.
-	Papel
-	PET y PEAD (Botellas): Enjuaga y compacta, cuando llegues al contenedor vacía tu bolsa en el contenedor y reutiliza para volver a juntar nuevamente, así no gastarás bolsas nuevas.
-	Aluminio ( Latas)
-	Electrónicos (Servicios públicos y Centro de Bienestar Animal
-	No se recibe:
-	Cacharros
-	Escombro
-	Cerámica
-	Ropa
-	Unicel
-	Tablaroca
-	Cartón multilaminado ( tetrapack)
-	Latas de fierro o latón
-	Madera
-	Focos
-	Medicinas
-	Acrílicos
-	Coroplast
-	Bolsas y emplayado
-	Residuos peligrosos
-	Electrodomésticos (línea blanca)

Pregunta: ¿Cuál es la ubicación de los Centros de Reciclaje?
Respuesta:
-	Auditorio San Pedro: Humberto Lobo esq, Av. Ignacio Morones Prieto s/n, Del Valle, 66220 San Pedro Garza García, N.L.
-	Centro de Bienestar Animal: Ubicación: Av. Ignacio Morones Prieto 1106, Col. Jesus M. Garza
-	Palo Blanco: Calle Manuel Doblado y 5 de Mayo, Col. Palo Blanco, frente a las oficinas del archivo municipal.
-	Fuentes del Valle: Calle Vía Valeria #301, Col. Fuentes del Valle
-	Parque Mississippi: Río Potosí entre Río Mississippi y Río de la Plata, Col. Del Valle
-	Parque Rufino Tamayo: Estacionamiento del parque, Av. Rufino Tamayo 100, Corporativo Prodesa, 66278 San Pedro Garza García, N.L.
-	Parque Bosques del Valle: Sierra Linda 77, Lomas del Valle, 66250 San Pedro Garza García, N.L.
-	Santa Engracia: Los Rosales 385, Col. Santa Engracia, 66267 San Pedro Garza García, N.L.
"""




async def get_centros_reciclaje():
    """Obtener informacion del directorio de centros de reciclaje en caso de ser necesario.

    Returns:
        string: Informacion de los centros de reciclaje.
    """
    return TC