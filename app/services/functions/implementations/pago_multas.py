import os
import requests
from app.util.logger import logger


STRIPE_API_KEY = os.getenv("STRIPE_API_KEY", "")
MUNICIPAL_MULTAS_API_URL = os.getenv("MUNICIPAL_MULTAS_API_URL", "")


def _consultar_adeudo_multa(identificador: str) -> dict:
    """Llama a la API municipal para obtener el adeudo de una multa por placa o folio."""
    try:
        url = f"{MUNICIPAL_MULTAS_API_URL}/{identificador}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error consultando adeudo multa: {e}")
        return None


def _cobrar_con_stripe(monto_pesos: float, numero_tarjeta: str, vencimiento_mes: str, vencimiento_anio: str, cvv: str, descripcion: str) -> dict:
    """Crea un PaymentMethod y un PaymentIntent confirmado en Stripe."""
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    auth = (STRIPE_API_KEY, "")

    # 1. Crear PaymentMethod con datos de tarjeta
    pm_response = requests.post(
        "https://api.stripe.com/v1/payment_methods",
        auth=auth,
        headers=headers,
        data={
            "type": "card",
            "card[number]": numero_tarjeta,
            "card[exp_month]": vencimiento_mes,
            "card[exp_year]": vencimiento_anio,
            "card[cvc]": cvv,
        }
    )
    pm_data = pm_response.json()
    if "error" in pm_data:
        return {"error": pm_data["error"].get("message", "Error al procesar la tarjeta")}

    payment_method_id = pm_data["id"]

    # 2. Crear y confirmar PaymentIntent
    monto_centavos = int(monto_pesos * 100)
    pi_response = requests.post(
        "https://api.stripe.com/v1/payment_intents",
        auth=auth,
        headers=headers,
        data={
            "amount": monto_centavos,
            "currency": "mxn",
            "payment_method": payment_method_id,
            "confirm": "true",
            "description": descripcion,
        }
    )
    pi_data = pi_response.json()
    if "error" in pi_data:
        return {"error": pi_data["error"].get("message", "Error al confirmar el pago")}

    return {"status": pi_data.get("status"), "id": pi_data.get("id")}


async def pago_multas(numero_placa: str, numero_tarjeta: str, vencimiento_mes: str, vencimiento_anio: str, cvv: str):
    """Consultar el adeudo de una multa de tránsito y realizar el cobro con tarjeta de crédito o débito.

    Args:
        numero_placa (string): Número de placas del vehículo o folio de la multa para consultar el adeudo.
        numero_tarjeta (string): Número de tarjeta de crédito o débito (16 dígitos, sin espacios).
        vencimiento_mes (string): Mes de vencimiento de la tarjeta (formato MM, ej: 07).
        vencimiento_anio (string): Año de vencimiento de la tarjeta (formato YYYY, ej: 2027).
        cvv (string): Código de seguridad de la tarjeta (3 o 4 dígitos).

    Returns:
        string: Confirmación del pago realizado o mensaje de error.
    """
    logger.info(f"[PAGO MULTAS] Placa/folio: {numero_placa}")

    # 1. Consultar adeudo con la API municipal
    adeudo = _consultar_adeudo_multa(numero_placa)
    if not adeudo:
        return "No se pudo consultar la multa. Verifica el número de placas o folio e intenta más tarde."

    monto = adeudo.get("monto") or adeudo.get("total") or adeudo.get("adeudo")
    if not monto or float(monto) <= 0:
        return "No se encontraron multas pendientes para ese número de placas o folio."

    monto = float(monto)
    folio_multa = adeudo.get("folio") or adeudo.get("id") or numero_placa

    # 2. Procesar pago con Stripe
    descripcion = f"Pago multa - Placa/Folio {numero_placa}"
    resultado = _cobrar_con_stripe(monto, numero_tarjeta, vencimiento_mes, vencimiento_anio, cvv, descripcion)

    if "error" in resultado:
        logger.error(f"[PAGO MULTAS] Error Stripe: {resultado['error']}")
        return f"No se pudo procesar el pago: {resultado['error']}"

    if resultado.get("status") in ("succeeded", "requires_capture"):
        logger.info(f"[PAGO MULTAS] Pago exitoso. ID: {resultado['id']}")
        return (
            f"✅ Pago de multa realizado exitosamente.\n"
            f"Monto cobrado: ${monto:,.2f} MXN\n"
            f"Placa / Folio: {folio_multa}\n"
            f"Referencia de pago: {resultado['id']}\n"
            f"Para cualquier aclaración comunícate al 81-8988-1100 Ext. 6013."
        )

    return f"El pago quedó en estado: {resultado.get('status')}. Comunícate al 81-8988-1100 Ext. 6013 para aclarar."
