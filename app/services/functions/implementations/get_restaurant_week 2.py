TC = """
Este documento contiene información sobre el evento San Pedro Restaurant Week realizado por el municipio de San Pedro Garza García

Pregunta: ¿Qué es el San Pedro Restaurant Week / SPRW?
Respuesta: San Pedro Restaurant Week es un evento gastronómico en el que varios restaurantes del municipio se suman para ofrecer menús especiales a precios fijos por tiempo limitado. La idea es que la gente pueda probar diferentes propuestas culinarias, mientras que los restaurantes tienen la oportunidad de atraer nuevos clientes y dar a conocer su cocina. Es una semana para disfrutar, descubrir nuevos sabores y celebrar la increíble gastronomía de San Pedro Garza García.
Instagram: @sanpedrorestaurantweek

Pregunta: ¿Cuántos restaurantes participan?
Respuesta: +170

Pregunta: ¿Cuáles son las categorías de los restaurantes?
Respuesta: Muy pronto estaremos compartiendo la lista completa de restaurantes participantes. Puedes visitar nuestro Instagram @sanpedrorestaurantweek, donde estaremos publicando toda la información y novedades del evento.

Pregunta: ¿Cuáles son los restaurantes que participan?
Respuesta: ¡Gracias por tu interés! Aún no hemos publicado la lista oficial de restaurantes participantes en esta edición de San Pedro Restaurant Week, pero estará disponible muy pronto. Te invitamos a seguirnos en Instagram @sanpedrorestaurantweek, donde estaremos anunciando el lineup y compartiendo todas las novedades.

Pregunta: ¿Cuál es el rango de precios?
Respuesta: Desde $149 hasta $799

Pregunta: ¿Cuáles son las fechas del SPRW?
Respuesta: Del 7 al 17 de agosto
"""

async def get_restaurant_week():
    """Obtener Información de Restaurant Week en caso de ser necesario.

    Returns:
        string: Informacion de Restaurant Week.
    """
    return TC