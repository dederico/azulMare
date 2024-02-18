TC = """
La tarjeta PRE APROBADA es "THE GOLD BUSINESS CARD" esta tarjeta no tiene la LÍMITE DE CRÉDITO , maneja una tasa ya preferente para usted, que es del 2%, fija mensual, adicional contara con FLEXIBILIDAD FINANCIERA Hasta 50 días naturales de financiamiento sin
intereses para liquidar todas sus compras, más Meses Sin Intereses y contará con el Plan AMEX de Pagos Diferidos en todas sus compras de hasta 3, 6 y 12 meses sin intereses BONIFICACIÓN DE 10 MIL PESOS que AMERICAN EXPRESS le da a todo cliente nuevo, 
el cual usted lo va a ver reflejado como saldo a favor en su tarjeta. La tarjeta ya está PRE APROBADA"""


async def get_credit_card_options():
    """Obtener informacion de las tarjetas de credito en caso de ser solicitada.

    Returns:
        string: Informacion de las tarjetas de credito.
    """
    return TC