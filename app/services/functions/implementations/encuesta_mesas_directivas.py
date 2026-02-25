import os
import requests
from app.util.logger import logger


MUNICIPAL_ENCUESTAS_API_URL = os.getenv("MUNICIPAL_ENCUESTAS_API_URL", "")


async def encuesta_mesas_directivas(
    nombre_completo: str,
    cargo: str,
    colonia: str,
    calificacion_servicios: str,
    comentarios: str,
    numero_contacto: str,
):
    """Registrar la respuesta de la encuesta de satisfacción para miembros de mesas directivas de colonias o condominios.

    Args:
        nombre_completo (string): Nombre completo del miembro de la mesa directiva.
        cargo (string): Cargo del miembro en la mesa directiva (ej: Presidente, Secretario, Tesorero, Vocal).
        colonia (string): Nombre de la colonia o condominio que representa.
        calificacion_servicios (string): Calificación del 1 al 10 sobre los servicios municipales recibidos.
        comentarios (string): Comentarios, sugerencias o quejas sobre los servicios municipales.
        numero_contacto (string): Número de teléfono o WhatsApp de contacto del miembro.

    Returns:
        string: Confirmación del registro de la encuesta o mensaje de error.
    """
    logger.info(f"[ENCUESTA MESAS DIRECTIVAS] Registrando respuesta de {nombre_completo} - {cargo} - {colonia}")

    payload = {
        "nombre_completo": nombre_completo,
        "cargo": cargo,
        "colonia": colonia,
        "calificacion_servicios": calificacion_servicios,
        "comentarios": comentarios,
        "numero_contacto": numero_contacto,
    }

    try:
        response = requests.post(
            MUNICIPAL_ENCUESTAS_API_URL,
            json=payload,
            timeout=10,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        folio = response.json().get("folio") or response.text.strip() or "Registrado"
        logger.info(f"[ENCUESTA MESAS DIRECTIVAS] Encuesta guardada. Folio: {folio}")
        return (
            f"✅ Encuesta registrada exitosamente.\n"
            f"Gracias, {nombre_completo}. Tu opinión como {cargo} de {colonia} es muy valiosa para nosotros.\n"
            f"Folio de registro: {folio}"
        )
    except Exception as e:
        logger.error(f"[ENCUESTA MESAS DIRECTIVAS] Error al guardar encuesta: {e}")
        return "Hubo un problema al registrar tu encuesta. Por favor intenta más tarde o comunícate al 81-8400-4400."
