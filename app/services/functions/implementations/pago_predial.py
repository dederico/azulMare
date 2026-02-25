import os
import requests
from app.util.logger import logger


STRIPE_API_KEY = os.getenv("STRIPE_API_KEY", "")
MUNICIPAL_PREDIAL_API_URL = os.getenv("MUNICIPAL_PREDIAL_API_URL", "")


def _consultar_adeudo_predial(expediente_catastral: str) -> dict:
    """Llama a la API municipal para obtener el adeudo de predial."""
    try:
        url = f"{MUNICIPAL_PREDIAL_API_URL}/{expediente_catastral}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error consultando adeudo predial: {e}")
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


async def pago_predial(expediente_catastral: str, numero_tarjeta: str, vencimiento_mes: str, vencimiento_anio: str, cvv: str):
    """Consultar el adeudo de predial y realizar el cobro con tarjeta de crédito o débito.

    Args:
        expediente_catastral (string): Número de expediente catastral del inmueble del ciudadano.
        numero_tarjeta (string): Número de tarjeta de crédito o débito (16 dígitos, sin espacios).
        vencimiento_mes (string): Mes de vencimiento de la tarjeta (formato MM, ej: 07).
        vencimiento_anio (string): Año de vencimiento de la tarjeta (formato YYYY, ej: 2027).
        cvv (string): Código de seguridad de la tarjeta (3 o 4 dígitos).

    Returns:
        string: Confirmación del pago realizado o mensaje de error.
    """
    logger.info(f"[PAGO PREDIAL] Expediente: {expediente_catastral}")

    # 1. Consultar adeudo con la API municipal
    adeudo = _consultar_adeudo_predial(expediente_catastral)
    if not adeudo:
        return "No se pudo consultar el adeudo. Verifica que el expediente catastral sea correcto o intenta más tarde."

    monto = adeudo.get("monto") or adeudo.get("total") or adeudo.get("adeudo")
    if not monto or float(monto) <= 0:
        return "El expediente catastral no tiene adeudos pendientes. ¡Todo está al corriente!"

    monto = float(monto)

    # 2. Procesar pago con Stripe
    descripcion = f"Pago predial - Expediente {expediente_catastral}"
    resultado = _cobrar_con_stripe(monto, numero_tarjeta, vencimiento_mes, vencimiento_anio, cvv, descripcion)

    if "error" in resultado:
        logger.error(f"[PAGO PREDIAL] Error Stripe: {resultado['error']}")
        return f"No se pudo procesar el pago: {resultado['error']}"

    if resultado.get("status") in ("succeeded", "requires_capture"):
        logger.info(f"[PAGO PREDIAL] Pago exitoso. ID: {resultado['id']}")
        return (
            f"✅ Pago de predial realizado exitosamente.\n"
            f"Monto cobrado: ${monto:,.2f} MXN\n"
            f"Expediente catastral: {expediente_catastral}\n"
            f"Referencia de pago: {resultado['id']}\n"
            f"Guarda esta referencia para solicitar tu factura en: https://cajavirtual.sanpedro.gob.mx/facturacion/"
        )

    return f"El pago quedó en estado: {resultado.get('status')}. Comunícate al 81-8400-4491 para aclarar."
