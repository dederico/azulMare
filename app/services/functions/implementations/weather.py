async def get_current_weather(location, unit):
    """Para cuando piden el clima/temperatura en tiempo real de una locacion.

    Args:
        location (string): locacion del lugar al cual se le hallara la temperatura.
        unit (string): escala de temperatura. enum["celsius", "fahrenheit"].

    Returns:
        string: Clima actual en la locacion especificada.
    """
    return "El clima actual en san francisco es de 35 grados celsius"