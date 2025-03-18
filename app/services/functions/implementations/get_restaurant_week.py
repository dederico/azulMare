TC = """
Este documento contiene información sobre el evento San Pedro Restaurant Week realizado por el municipio de San Pedro Garza García

Pregunta: ¿Qué es el San Pedro Restaurant Week / SPRW?
Respuesta: San Pedro Restaurant Week es un evento gastronómico en el que varios restaurantes del municipio se suman para ofrecer menús especiales a precios fijos por tiempo limitado. La idea es que la gente pueda probar diferentes propuestas culinarias, mientras que los restaurantes tienen la oportunidad de atraer nuevos clientes y dar a conocer su cocina. Es una semana para disfrutar, descubrir nuevos sabores y celebrar la increíble gastronomía de San Pedro Garza García.
Instagram: @sanpedrorestaurantweek

Pregunta: ¿Cuántos restaurantes participan?
Respuesta: +150

Pregunta: ¿Cuáles son las categorías de los restaurantes?
Respuesta:
Internacional
⁠Mexicana
Burgers&Sandwiches
⁠Asiática
⁠Del Mar
⁠Vegetariana
⁠Italiana
Fast Food
⁠Postres

Pregunta: ¿Cuál es el rango de precios?
Respuesta: Desde 149 hasta 799

Pregunta: ¿Cuáles son las fechas del SPRW?
Respuesta: Del 30 de enero al 9 de febrero

Pregunta: ¿Cuáles son los restaurantes que participan?
Respuesta:
El Rincón de Majahuitas
9 fuegos
Abisal Seafoods
Aló Café
Aloha Sushi Lounge
Amalay Coffee & Market
Animal Calzada
Barbaro
Bardot
Beastie Burger
Bestia
Black Market
BLAK
Bloom Craft Superfoods
Buckets
Butchers Universe
Butcher's Bgr
Cabron Empanadas y Pizzas Argentinas
Calle 7
Casa Benell
Casa Blasón
 Casa Macro
Chick n Chak
Chilaqueria MX
Choice Grill House
Clavadito
Cocina Habibi
Cofki Kid-Friendly Café 
Cometa
Cuerno Calzada
Daisuke Karaoke Metropolitan Center
Deep Seafood Joint
Don Macizo
Dora Elsa Galería de Paellas
El Che-Bichero
El Guayabo
El lugar de Max
El Mercadito de la Baja
Enrique Tomás
Fidencio Botanero
Fiships
Flacos Burgers
Flama Asador Bar
Francesco's 
Frida Chilaquiles
Frites Artois
Gagootz  
Grand Cru
Half & Half
Hanaichi
Hatxa
Hawaii Cinco Cero
Higuera
Hotsie
House of Toffee
Ichikani
Japonika
Jia Xing Comida China Cantonesa
John Hams 
Joker
Kadoya
Kampai
Kampai 401
Kebabes by Lahm
La Botiga
La Bonne
La Castellana
La Corriente Cevichería Nais
La Divina
La Embajada
La Mazatleca
La Reynita
Aliadas
Lázaro & Diego
LeCreepe & LeCream 
Lemonita
Liberato Eatery
Libertad
Los Arbolitos de Cajeme
Los Gyros
Los Hidalgos
Mahana Pizza
Maison Croque
Mala Leche
Mar del Zur
Masa Madre Vasconcelos
Masa Madre Sucursal Centrito
Melier
Mercado San Martín
Milk Pizzería Centrito
Milk Pizzería Metropolitan
Mirai
Mocca Bakery
Mochomos
Mon Paris
Moonwalk Cookies
Mr Smashie
Mr. Culichi
"Nectarworks 
Aurora, UDEM y Vita "
Nectarworks+ Arboleda
Nikkori
Nikkori UDEM
Nivem Hawaiian Shave Ice
Nolita Ice Cream Bakery
Ommani Holistic Kitchen
Orfebre Cocina Artesana
Oriental Grill Chipinque
Oriental Wok Gomez Morin
Orson
Orocanela
Tierra x Oum 
Pastelone
Pan de Cajeta
Piquina Cocina Mexicana
Pokeshack
Pound
Querida Adela 
Quincy
Reina
Rosta
 Señor Latino
Ryoshi
Saxy Jazz Club
Sr, Bigotes
Señor Tanaka
Señora Tanaka
Será el Sereno
Sibau
Signature Room
Suculenta
Suculenta Armida
Sushi Kado
Sushiitto 
Tacos Atarantados
Taller Vegánico
Tatemate
Los Tecatacos
Temakita
Terrae Trattoria Regia
Thai Thai
The Food Box
The Oven Pizzato
Tienda de Vinos Pangea
Tigre
Tito's Alitas Adictivas
Tortas Las Sevillanas
Umami Ramen House
La Vaca Argentina
Vasconcelos Paladar Mexicano
Vasto
Vino Premier San Pedro
We Love Burgers
Zatziki
"""

async def get_restaurant_week():
    """Obtener Información de Restaurant Week en caso de ser necesario.

    Returns:
        string: Informacion de Restaurant Week.
    """
    return TC