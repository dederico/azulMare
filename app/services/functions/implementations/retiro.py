async def deposito(cuenta, tarjeta, monto, destino, moneda):
    """El cliente ha solicitado hacer un retiro

    Args:
        cuenta (string): numero de cuenta de la cual se hará el retiro.
        tarjeta (string): tarjeta de la cual se hará el retiro.
        monto (integer): numero de monto de la cual se hará el retiro.
        moneda (currency): tipo de moneda
        destion (string): tarjeta a la cual recibirá el retiro.
    Returns:
        string: Confirmar el retiro.
    """
    return "Se ha realizado un retiro de " + str(monto) + " " + str(moneda) + " de la cuenta " + str(cuenta) + " a la tarjeta " + str(destino) + "."