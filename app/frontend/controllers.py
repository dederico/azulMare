import json
import os
import platform
import re
import sys
import importlib
import csv
import requests
from pathlib import Path
from io import BytesIO, StringIO
from openai import OpenAI
from datetime import datetime, timedelta
from threading import Thread
import openpyxl
from app.models.File import File
from app.models.Call import Call
from app.models.Message import Message
from app.models.Config import Config
from app.models.Notification import Notification
from app.models.OutgoingCampaign import OutgoingCampaign
from app.models.OutgoingRecipient import OutgoingRecipient
from app.util.database import LocalStorage
from app.util.logger import logger
from app.outbound import InitOutboundCalls
from app.services.functions import function_registry as function_registry_module


REPO_ROOT = Path(__file__).resolve().parents[2]
IMPLEMENTATIONS_DIR = REPO_ROOT / "app/services/functions/implementations"
FUNCTION_REGISTRY_PATH = REPO_ROOT / "app/services/functions/function_registry.py"
PROMPT_DYNAMIC_START = "[KB_DYNAMIC_START]"
PROMPT_DYNAMIC_END = "[KB_DYNAMIC_END]"
PROMPT_PRIMARY_ANCHOR = "get_actividades_mayo_junio()"
PROMPT_FALLBACK_PATTERN = re.compile(r"^\s*-\s+consultas\s+sobre.+Utiliza\s+get_[a-z0-9_]+\(\).*$", re.IGNORECASE)
RECIPIENT_FIELD_PATTERN = re.compile(
    r"([A-Za-zÁÉÍÓÚÑáéíóúñ0-9_]+)\s*:\s*",
    re.UNICODE,
)
DEFAULT_CHAT2DESK_CHANNEL_ID = 43906
PROACTIVE_AUDIENCE_FTYPE = "proactive_audience"
PROACTIVE_AUDIENCE_PREFIX = "audience::"
PROACTIVE_HSM_REPLY_GUARD_KEY = "proactive_hsm_guard"
DEFAULT_RETURN_TO_SAM_MESSAGE = "Gracias por comunicarte con el Colegio Militarizado. Procederé a reiniciar el chatbot para que puedas continuar con GUERRERO."
APPROVED_HSM_TEMPLATES = {
    "invitacion_evento": {
        "label": "Invitación a evento",
        "locale": "es_mx",
        "fixed_attachment_url": "https://drive.google.com/uc?export=download&id=1No-1ayfSMeFZ_JcGduygZDxZwcqEeeQy",
        "fixed_attachment_filename": "invitacion_evento.jpg",
    },
    "custom": {
        "label": "Plantilla aprobada personalizada",
        "locale": "es_mx",
    },
}
PROACTIVE_CAMPAIGN_KINDS = {
    "hsm_sequence": "Gancho HSM + mensaje libre + regreso a GUERRERO",
    "hsm_hook": "Gancho HSM",
    "free_followup": "Mensaje libre 24h",
    "return_to_sam": "Regresar a GUERRERO",
}
RECIPIENT_NAME_KEYS = {
    "nombre", "name", "contacto", "nombre_completo", "nombre_del_vecino",
    "vecino", "cliente", "beneficiario", "titular", "persona", "full_name",
}
RECIPIENT_PHONE_KEYS = {
    "numero", "telefono", "telefono_whatsapp", "whatsapp", "celular", "phone",
    "telefono_celular", "numero_telefono", "numero_celular", "movil", "mobile",
    "telefono_movil", "num_telefono", "num_celular", "telefono1", "telefono_1",
    "telefono2", "telefono_2", "whats", "whats_app", "numero_whatsapp",
}
RECIPIENT_CANONICAL_KEY_MAP = {
    "nombre_del_vecino": "nombre",
    "nombre_completo": "nombre",
    "full_name": "nombre",
    "numero_telefono": "telefono",
    "numero_celular": "celular",
    "telefono_celular": "celular",
    "telefono_movil": "celular",
    "movil": "celular",
    "mobile": "celular",
    "num_telefono": "telefono",
    "num_celular": "celular",
    "whats": "whatsapp",
    "whats_app": "whatsapp",
    "numero_whatsapp": "whatsapp",
    "sector_k": "k",
    "k_sector": "k",
    "col": "colonia",
    "fracc": "fraccionamiento",
    "direccion": "calle",
    "domicilio": "calle",
}


class OutgoingDeliveryError(Exception):
    def __init__(self, source: str, message: str, *, payload: dict | None = None, status_code: int | None = None):
        super().__init__(message)
        self.source = source
        self.message = message
        self.payload = payload or {}
        self.status_code = status_code


def _safe_json_response(response):
    try:
        return response.json()
    except Exception:
        return {"raw_text": response.text[:2000] if getattr(response, "text", None) else ""}


def _serialize_delivery_payload(payload) -> str:
    try:
        return json.dumps(payload or {}, ensure_ascii=True)
    except Exception:
        return json.dumps({"raw": str(payload)}, ensure_ascii=True)


def _build_text_preview(text: str, limit: int = 240) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit]}... [truncated {len(cleaned) - limit} chars]"


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _parse_datetime_or_none(raw_value: str) -> datetime | None:
    value = (raw_value or "").strip()
    if not value:
        return None

    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _normalize_bool(raw_value, default: bool = False) -> bool:
    if raw_value is None:
        return default
    if isinstance(raw_value, bool):
        return raw_value
    return str(raw_value).strip().lower() not in {"", "0", "false", "off", "no"}


def _normalize_delay_minutes(raw_value) -> int:
    value = str(raw_value or "").strip()
    if not value:
        return 15
    try:
        minutes = int(value)
    except ValueError as e:
        raise ValueError("El temporizador para abrir la ventana debe ser un número entero de minutos.") from e
    if minutes < 0:
        raise ValueError("El temporizador para abrir la ventana no puede ser negativo.")
    if minutes > 24 * 60:
        raise ValueError("El temporizador para abrir la ventana no puede exceder 1440 minutos.")
    return minutes


def _build_hsm_message(template_name: str, locale: str, template_variables: str) -> str:
    body_lines = [line.rstrip() for line in (template_variables or "").splitlines()] if template_variables else []
    hsm_lines = ["@HSM@", f"{template_name}|{locale}"]
    if body_lines:
        hsm_lines.append("")
        hsm_lines.extend(body_lines)
    return "\n".join(hsm_lines).strip()


def _get_fixed_hsm_attachment(template_name: str) -> tuple[str, str]:
    template_config = APPROVED_HSM_TEMPLATES.get((template_name or "").strip(), {}) or {}
    return (
        (template_config.get("fixed_attachment_url") or "").strip(),
        (template_config.get("fixed_attachment_filename") or "").strip(),
    )


def _append_provider_event(existing_payload: str, stage: str, payload: dict) -> str:
    events = []
    try:
        parsed = json.loads(existing_payload or "[]")
        if isinstance(parsed, list):
            events = parsed
        elif parsed:
            events = [parsed]
    except Exception:
        events = [{"raw": existing_payload}]
    events.append({"stage": stage, "payload": payload, "at": _now_str()})
    return _serialize_delivery_payload(events)


def _build_error_type(source: str, message: str, status_code: int | None = None) -> str:
    base = source.upper()
    detail = (message or "").lower()
    if status_code:
        return f"{base}_HTTP_{status_code}"
    if "timeout" in detail:
        return f"{base}_TIMEOUT"
    if "authorization" in detail or "token" in detail:
        return f"{base}_AUTH"
    if "channel" in detail:
        return f"{base}_CHANNEL"
    return f"{base}_ERROR"


def _normalize_saved_label(raw_label: str) -> str:
    label = " ".join((raw_label or "").split()).strip()
    if not label:
        raise ValueError("Debes capturar un nombre para guardar la lista.")
    return label


def _build_audience_storage_name(label: str) -> str:
    return f"{PROACTIVE_AUDIENCE_PREFIX}{label}"


def _decode_json_blob(raw_value) -> dict:
    if isinstance(raw_value, memoryview):
        raw_value = raw_value.tobytes()
    if isinstance(raw_value, bytes):
        raw_value = raw_value.decode("utf-8")
    if isinstance(raw_value, str):
        return json.loads(raw_value)
    raise ValueError(f"Tipo de dato no soportado para blob JSON: {type(raw_value).__name__}")


def _extract_saved_audience_payload(file_record) -> dict:
    raw = getattr(file_record, "data", b"") or b""
    try:
        payload = _decode_json_blob(raw)
    except Exception as e:
        raise ValueError(f"No se pudo leer la lista guardada '{getattr(file_record, 'name', '')}': {e}") from e
    if not isinstance(payload, dict) or not isinstance(payload.get("recipients"), list):
        raise ValueError("La lista guardada no tiene un formato válido.")
    return payload


def _normalize_knowledge_function_name(raw_name: str) -> str:
    normalized = (raw_name or "").strip().lower().replace("-", "_").replace(" ", "_")
    normalized = re.sub(r"^get_", "", normalized)
    normalized = re.sub(r"[^a-z0-9_]", "", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if not normalized or not re.match(r"^[a-z][a-z0-9_]*$", normalized):
        raise ValueError("El nombre de la función debe empezar con letra y solo usar minúsculas, números o guiones bajos.")
    return normalized


def _build_knowledge_module(function_name: str, tc_content: str, function_summary: str) -> str:
    summary = (function_summary or "").strip() or f"Obtener información sobre {function_name.replace('_', ' ')}."
    tc_clean = (tc_content or "").strip().replace('"""', '\\"\\"\\"')
    return (
        'TC = """\n'
        f"{tc_clean}\n"
        '"""\n\n\n'
        f"async def get_{function_name}():\n"
        f'    """{summary}\n\n'
        "    Returns:\n"
        f"        string: {summary}\n"
        '    """\n'
        "    return TC\n"
    )


def _create_knowledge_implementation(function_name: str, tc_content: str, function_summary: str) -> Path:
    module_path = IMPLEMENTATIONS_DIR / f"get_{function_name}.py"
    if module_path.exists():
        raise ValueError(f"Ya existe el archivo {module_path.name}.")
    module_path.write_text(
        _build_knowledge_module(function_name, tc_content, function_summary),
        encoding="utf-8",
    )
    return module_path


def _build_updated_function_registry_text(registry_text: str, function_name: str) -> str:
    import_line = f"from .implementations.get_{function_name} import get_{function_name}"
    function_entry = f"    get_{function_name},"

    if import_line not in registry_text:
        implementation_imports = list(re.finditer(r"^from \.implementations\..+$", registry_text, flags=re.MULTILINE))
        if not implementation_imports:
            raise ValueError("No se encontró un bloque de imports de implementaciones en function_registry.py")
        insert_at = implementation_imports[-1].end()
        registry_text = registry_text[:insert_at] + "\n" + import_line + registry_text[insert_at:]

    if function_entry.strip() not in registry_text:
        list_match = re.search(r"registered_functions = \[\n(?P<body>.*?)(?P<closing>\n\])", registry_text, flags=re.DOTALL)
        if not list_match:
            raise ValueError("No se encontró el arreglo registered_functions en function_registry.py")

        body = list_match.group("body")
        if body.rstrip() and not body.rstrip().endswith(","):
            body = body.rstrip() + ",\n"
        body = body + function_entry + "\n"

        registry_text = (
            registry_text[:list_match.start("body")]
            + body
            + registry_text[list_match.start("closing"):]
        )

    return registry_text


def _restore_trailing_newline(original_text: str, updated_text: str) -> str:
    if original_text.endswith("\n") and not updated_text.endswith("\n"):
        return updated_text + "\n"
    if not original_text.endswith("\n") and updated_text.endswith("\n"):
        return updated_text[:-1]
    return updated_text


def _insert_prompt_line(prompt_text: str, prompt_line: str) -> str:
    if prompt_line in prompt_text:
        return prompt_text

    lines = prompt_text.splitlines()
    start_idx = next((idx for idx, line in enumerate(lines) if line.strip() == PROMPT_DYNAMIC_START), None)
    end_idx = next((idx for idx, line in enumerate(lines) if line.strip() == PROMPT_DYNAMIC_END), None)

    if start_idx is not None and end_idx is not None and start_idx < end_idx:
        lines.insert(end_idx, prompt_line)
        return _restore_trailing_newline(prompt_text, "\n".join(lines))

    insert_idx = None
    for idx, line in enumerate(lines):
        if PROMPT_PRIMARY_ANCHOR in line:
            insert_idx = idx + 1
            break

    if insert_idx is None:
        dynamic_indexes = [idx for idx, line in enumerate(lines) if PROMPT_FALLBACK_PATTERN.match(line)]
        if dynamic_indexes:
            insert_idx = dynamic_indexes[-1] + 1

    block_lines = [PROMPT_DYNAMIC_START, prompt_line, PROMPT_DYNAMIC_END]

    if insert_idx is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(block_lines)
        return _restore_trailing_newline(prompt_text, "\n".join(lines))

    lines[insert_idx:insert_idx] = block_lines
    return _restore_trailing_newline(prompt_text, "\n".join(lines))


def _update_prompt_config(local_storage: LocalStorage, function_name: str, prompt_topic: str) -> None:
    config = local_storage.Search(Config(name="prompt"), True, False)
    if not config:
        raise ValueError("No existe el config 'prompt' en la base de datos.")

    topic_clean = (prompt_topic or "").strip()
    if not topic_clean:
        raise ValueError("Debes indicar el texto descriptivo que se inyectará al prompt.")

    prompt_line = f'- consultas sobre "{topic_clean}" Utiliza get_{function_name}()'
    config.value = _insert_prompt_line(config.value or "", prompt_line)
    local_storage.Update(config)


def _load_runtime_knowledge_function(function_name: str):
    module_name = f"app.services.functions.implementations.get_{function_name}"
    module = importlib.import_module(module_name)
    runtime_function = getattr(module, f"get_{function_name}", None)
    if runtime_function is None:
        raise ValueError(f"No se pudo cargar get_{function_name} en runtime.")
    return module_name, runtime_function


def _register_runtime_knowledge_function(function_name: str):
    module_name, runtime_function = _load_runtime_knowledge_function(function_name)
    if not any(getattr(func, "__name__", "") == runtime_function.__name__ for func in function_registry_module.registered_functions):
        function_registry_module.registered_functions.append(runtime_function)
    return module_name, runtime_function


def create_knowledge_function(local_storage: LocalStorage, payload: dict) -> dict:
    function_name = _normalize_knowledge_function_name(payload.get("function_name", ""))
    tc_content = (payload.get("tc_content") or "").strip()
    prompt_topic = (payload.get("prompt_topic") or "").strip()
    function_summary = (payload.get("function_summary") or "").strip()

    if not tc_content:
        raise ValueError("Debes capturar el contenido del documento para TC.")

    original_registry_text = FUNCTION_REGISTRY_PATH.read_text(encoding="utf-8")
    prompt_config = local_storage.Search(Config(name="prompt"), True, False)
    if not prompt_config:
        raise ValueError("No existe el config 'prompt' en la base de datos.")
    original_prompt_text = prompt_config.value or ""

    created_module = _create_knowledge_implementation(function_name, tc_content, function_summary)
    runtime_module_name = ""
    runtime_function = None
    try:
        updated_registry_text = _build_updated_function_registry_text(original_registry_text, function_name)
        FUNCTION_REGISTRY_PATH.write_text(updated_registry_text, encoding="utf-8")
        runtime_module_name, runtime_function = _register_runtime_knowledge_function(function_name)
        _update_prompt_config(local_storage, function_name, prompt_topic)
    except Exception:
        if runtime_function and runtime_function in function_registry_module.registered_functions:
            function_registry_module.registered_functions.remove(runtime_function)
        if runtime_module_name:
            sys.modules.pop(runtime_module_name, None)
        if created_module.exists():
            created_module.unlink()
        FUNCTION_REGISTRY_PATH.write_text(original_registry_text, encoding="utf-8")
        prompt_config.value = original_prompt_text
        local_storage.Update(prompt_config)
        raise

    logger.info("Knowledge function created successfully: get_%s", function_name)
    return {
        "status": True,
        "message": f"Función get_{function_name} creada y prompt actualizado.",
        "function_name": f"get_{function_name}",
        "module_path": str(created_module.relative_to(REPO_ROOT)),
    }


def _normalize_phone_number(raw_phone: str) -> str:
    digits = "".join(ch for ch in (raw_phone or "") if ch.isdigit())
    if not digits:
        raise ValueError("Cada destinatario debe incluir un número telefónico.")
    if len(digits) == 10:
        return f"+52{digits}"
    if len(digits) == 12 and digits.startswith("52"):
        return f"+{digits}"
    if len(digits) == 13 and digits.startswith("521"):
        return f"+{digits}"
    if raw_phone.strip().startswith("+"):
        return "+" + digits
    return f"+{digits}"


def _normalize_recipient_key(raw_key: str) -> str:
    key = (raw_key or "").strip().lower()
    key = re.sub(r"\s+", "_", key)
    key = (
        key.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ñ", "n")
    )
    return re.sub(r"[^a-z0-9_]", "", key)


def _canonicalize_recipient_key(raw_key: str) -> str:
    normalized_key = _normalize_recipient_key(raw_key)
    return RECIPIENT_CANONICAL_KEY_MAP.get(normalized_key, normalized_key)


def _find_first_present_value(parsed: dict, valid_keys: set[str]) -> str:
    for key in valid_keys:
        value = (parsed.get(key) or "").strip()
        if value:
            return value
    return ""


def _parse_recipient_line(line: str, line_number: int) -> dict:
    line = line.strip()
    matches = list(RECIPIENT_FIELD_PATTERN.finditer(line))
    if not matches:
        raise ValueError(f"Línea {line_number}: no se pudo leer el formato del destinatario.")

    parsed = {}
    for idx, match in enumerate(matches):
        raw_key = match.group(1)
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(line)
        raw_value = line[start:end]
        key = _canonicalize_recipient_key(raw_key)
        value = raw_value.strip().strip(",;")
        if key and value:
            parsed[key] = value

    name = _find_first_present_value(parsed, RECIPIENT_NAME_KEYS)
    phone = _find_first_present_value(parsed, RECIPIENT_PHONE_KEYS)

    if not phone:
        phone_match = re.search(
            r"(?:n[uú]mero|tel[eé]fono(?:_whatsapp)?|whatsapp|celular|phone)\s*:\s*([+\d][\d\s-]*)",
            line,
            flags=re.IGNORECASE,
        )
        if phone_match:
            phone = phone_match.group(1).strip()

    if not name:
        name_match = re.search(
            r"nombre\s*:\s*(.*?)(?=\s+(?:n[uú]mero|tel[eé]fono(?:_whatsapp)?|whatsapp|celular|phone|k)\s*:|$)",
            line,
            flags=re.IGNORECASE,
        )
        if name_match:
            name = name_match.group(1).strip()

    if not phone:
        raise ValueError(f"Línea {line_number}: falta el número telefónico.")

    metadata = {
        key: value
        for key, value in parsed.items()
        if key not in RECIPIENT_NAME_KEYS and key not in RECIPIENT_PHONE_KEYS
    }

    return {
        "name": name or "Sin nombre",
        "phone": _normalize_phone_number(phone),
        "metadata": metadata,
    }


def _dedupe_recipients(recipients: list[dict]) -> list[dict]:
    unique = []
    seen = set()
    for recipient in recipients:
        phone = recipient.get("phone", "")
        if phone in seen:
            continue
        seen.add(phone)
        unique.append(recipient)
    return unique


def parse_outgoing_recipients(recipients_text: str) -> list[dict]:
    recipients = []
    seen_phones = set()

    for idx, raw_line in enumerate((recipients_text or "").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        recipient = _parse_recipient_line(line, idx)
        if recipient["phone"] in seen_phones:
            continue
        seen_phones.add(recipient["phone"])
        recipients.append(recipient)

    if not recipients:
        raise ValueError("Debes capturar al menos un destinatario válido.")

    return recipients


def _parse_csv_recipients(file_bytes: bytes) -> list[dict]:
    try:
        decoded = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        decoded = file_bytes.decode("latin-1")

    reader = csv.DictReader(StringIO(decoded))
    if not reader.fieldnames:
        raise ValueError("El archivo CSV no contiene encabezados.")

    recipients = []
    for idx, row in enumerate(reader, start=2):
        parsed = {}
        for raw_key, raw_value in (row or {}).items():
            key = _canonicalize_recipient_key(raw_key or "")
            value = str(raw_value or "").strip()
            if key and value:
                parsed[key] = value

        if not parsed:
            continue

        name = _find_first_present_value(parsed, RECIPIENT_NAME_KEYS)
        phone = _find_first_present_value(parsed, RECIPIENT_PHONE_KEYS)
        if not phone:
            raise ValueError(f"Fila {idx}: falta el número telefónico.")

        metadata = {
            key: value
            for key, value in parsed.items()
            if key not in RECIPIENT_NAME_KEYS and key not in RECIPIENT_PHONE_KEYS
        }
        recipients.append(
            {
                "name": name or "Sin nombre",
                "phone": _normalize_phone_number(phone),
                "metadata": metadata,
            }
        )

    if not recipients:
        raise ValueError("El archivo CSV no contiene destinatarios válidos.")
    return _dedupe_recipients(recipients)


def _parse_xlsx_recipients(file_bytes: bytes) -> list[dict]:
    workbook = openpyxl.load_workbook(BytesIO(file_bytes), data_only=True)
    worksheet = workbook.active
    rows = list(worksheet.iter_rows(values_only=True))
    if not rows:
        raise ValueError("El archivo XLSX está vacío.")

    headers = [str(cell or "").strip() for cell in rows[0]]
    if not any(headers):
        raise ValueError("El archivo XLSX no contiene encabezados.")

    recipients = []
    for idx, row in enumerate(rows[1:], start=2):
        parsed = {}
        for raw_key, raw_value in zip(headers, row):
            key = _canonicalize_recipient_key(raw_key)
            value = str(raw_value or "").strip()
            if key and value:
                parsed[key] = value

        if not parsed:
            continue

        name = _find_first_present_value(parsed, RECIPIENT_NAME_KEYS)
        phone = _find_first_present_value(parsed, RECIPIENT_PHONE_KEYS)
        if not phone:
            raise ValueError(f"Fila {idx}: falta el número telefónico.")

        metadata = {
            key: value
            for key, value in parsed.items()
            if key not in RECIPIENT_NAME_KEYS and key not in RECIPIENT_PHONE_KEYS
        }
        recipients.append(
            {
                "name": name or "Sin nombre",
                "phone": _normalize_phone_number(phone),
                "metadata": metadata,
            }
        )

    if not recipients:
        raise ValueError("El archivo XLSX no contiene destinatarios válidos.")
    return _dedupe_recipients(recipients)


def _normalize_drive_download_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise ValueError("Debes capturar una URL de Drive.")
    file_match = re.search(r"/d/([a-zA-Z0-9_-]+)", url)
    if not file_match:
        file_match = re.search(r"id=([a-zA-Z0-9_-]+)", url)
    if not file_match:
        raise ValueError("No se pudo extraer el id del archivo de Google Drive.")
    file_id = file_match.group(1)
    return f"https://drive.google.com/uc?export=download&id={file_id}"


def _download_audience_source(source_url: str) -> tuple[bytes, str]:
    normalized_url = _normalize_drive_download_url(source_url)
    response = requests.get(normalized_url, timeout=60)
    response.raise_for_status()
    content_type = (response.headers.get("Content-Type") or "").lower()
    if "sheet" in content_type or "excel" in content_type or normalized_url.lower().endswith(".xlsx"):
        extension = "xlsx"
    else:
        extension = "csv"
    return response.content, extension


def _parse_recipients_from_file(file_bytes: bytes, extension: str) -> list[dict]:
    ext = (extension or "").strip().lower().lstrip(".")
    if ext == "csv":
        return _parse_csv_recipients(file_bytes)
    if ext in {"xlsx", "xlsm", "xltx", "xltm"}:
        return _parse_xlsx_recipients(file_bytes)
    raise ValueError("Solo se soportan archivos .csv y .xlsx para listas de destinatarios.")


def list_saved_audience_files(local_storage: LocalStorage) -> list[dict]:
    files = local_storage.Search(File(ftype=PROACTIVE_AUDIENCE_FTYPE), json=True, order="asc") or []
    result = []
    for file_record in files:
        try:
            payload = _decode_json_blob(file_record.get("data") or b"")
        except Exception:
            continue
        result.append(
            {
                "id": file_record["id"],
                "name": file_record["name"].replace(PROACTIVE_AUDIENCE_PREFIX, "", 1),
                "recipient_count": len(payload.get("recipients") or []),
                "source_name": payload.get("source_name") or "",
                "source_url": payload.get("source_url") or "",
                "created_at": payload.get("created_at") or "",
            }
        )
    return result


def create_saved_audience_file(
    local_storage: LocalStorage,
    *,
    audience_label: str,
    file_bytes: bytes,
    extension: str,
    source_name: str = "",
    source_url: str = "",
) -> dict:
    label = _normalize_saved_label(audience_label)
    storage_name = _build_audience_storage_name(label)
    existing = local_storage.Search(File(name=storage_name, ftype=PROACTIVE_AUDIENCE_FTYPE), True, False)
    if existing:
        raise ValueError("Ya existe una lista guardada con ese nombre.")

    recipients = _parse_recipients_from_file(file_bytes, extension)
    payload = {
        "label": label,
        "source_name": source_name,
        "source_url": source_url,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "recipients": recipients,
    }
    saved = local_storage.Insert(
        File(
            name=storage_name,
            ftype=PROACTIVE_AUDIENCE_FTYPE,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )
    )
    if not saved or not hasattr(saved, "id"):
        raise ValueError("No se pudo guardar la lista de destinatarios.")
    return {
        "status": True,
        "message": f"Lista '{label}' guardada con {len(recipients)} destinatarios.",
        "file_id": saved.id,
        "recipient_count": len(recipients),
    }


def delete_saved_audience_file(local_storage: LocalStorage, file_id: int) -> dict:
    file_record = local_storage.GetByPK(File, file_id)
    if not file_record or getattr(file_record, "ftype", "") != PROACTIVE_AUDIENCE_FTYPE:
        raise ValueError("No se encontró la lista guardada solicitada.")
    label = getattr(file_record, "name", "").replace(PROACTIVE_AUDIENCE_PREFIX, "", 1)
    local_storage.Remove(file_record)
    return {
        "status": True,
        "message": f"Lista '{label}' eliminada correctamente.",
        "file_id": file_id,
    }


def _get_saved_audience_recipients(local_storage: LocalStorage, file_id: int) -> tuple[list[dict], str]:
    file_record = local_storage.GetByPK(File, file_id)
    if not file_record or getattr(file_record, "ftype", "") != PROACTIVE_AUDIENCE_FTYPE:
        raise ValueError("No se encontró la lista guardada seleccionada.")
    payload = _extract_saved_audience_payload(file_record)
    return _dedupe_recipients(payload.get("recipients") or []), payload.get("label") or getattr(file_record, "name", "")


def list_outgoing_campaigns(local_storage: LocalStorage) -> list[dict]:
    campaigns = local_storage.GetAll(OutgoingCampaign, json=True) or []
    campaigns = [campaign for campaign in campaigns if (campaign.get("status") or "").lower() != "deleted"]
    campaigns = list(reversed(campaigns))
    enriched = []
    for campaign in campaigns:
        recipients = local_storage.Search(OutgoingRecipient(campaign_id=campaign["id"]), json=True, order="asc") or []
        sent_count = sum(1 for recipient in recipients if (recipient.get("status") or "").lower() == "sent")
        failed_count = sum(1 for recipient in recipients if (recipient.get("status") or "").lower() == "failed")
        pending_count = sum(1 for recipient in recipients if (recipient.get("status") or "pending").lower() in {"pending", "processing"})
        replied_count = sum(1 for recipient in recipients if (recipient.get("repliedAt") or "").strip())
        seen_count = sum(1 for recipient in recipients if (recipient.get("seenAt") or "").strip())
        left_on_seen_count = sum(
            1
            for recipient in recipients
            if (recipient.get("seenAt") or "").strip() and not (recipient.get("repliedAt") or "").strip()
        )
        hook_sent_count = sum(1 for recipient in recipients if (recipient.get("hookSentAt") or "").strip())
        free_sent_count = sum(1 for recipient in recipients if (recipient.get("freeMessageSentAt") or "").strip())
        returned_to_sam_count = sum(1 for recipient in recipients if (recipient.get("returnToSamSentAt") or "").strip())
        waiting_window_count = sum(1 for recipient in recipients if (recipient.get("deliveryStage") or "pending_hook") == "waiting_window")
        ks = sorted(
            {
                json.loads(recipient.get("metadata") or "{}").get("k")
                for recipient in recipients
                if json.loads(recipient.get("metadata") or "{}").get("k")
            }
        )
        enriched.append(
            {
                **campaign,
                "recipientCount": len(recipients),
                "sentCount": sent_count,
                "failedCount": failed_count,
                "pendingCount": pending_count,
                "hookSentCount": hook_sent_count,
                "freeSentCount": free_sent_count,
                "returnedToSamCount": returned_to_sam_count,
                "waitingWindowCount": waiting_window_count,
                "repliedCount": replied_count,
                "seenCount": seen_count,
                "leftOnSeenCount": left_on_seen_count,
                "ks": ks,
                "recipients": [
                    {
                        **recipient,
                        "metadataParsed": json.loads(recipient.get("metadata") or "{}"),
                        "providerPayloadParsed": json.loads(recipient.get("providerPayload") or "{}"),
                    }
                    for recipient in recipients
                ],
            }
        )
    return enriched


def create_outgoing_campaign(local_storage: LocalStorage, payload: dict) -> dict:
    campaign_name = (payload.get("campaign_name") or "").strip()
    audience_name = (payload.get("audience_name") or "").strip()
    campaign_kind = (payload.get("campaign_kind") or "hsm_sequence").strip() or "hsm_sequence"
    message_body = (payload.get("message_body") or "").strip()
    message_mode = "free_text"
    attachment_url = (payload.get("attachment_url") or "").strip()
    attachment_filename = (payload.get("attachment_filename") or "").strip()
    scheduled_at = (payload.get("scheduled_at") or "").strip()
    created_by = (payload.get("created_by") or "").strip() or "colegio_militarizado"
    transport = (payload.get("transport") or "wa_direct").strip() or "wa_direct"
    recipients_text = payload.get("recipients_text") or ""
    audience_file_id_raw = (payload.get("audience_file_id") or "").strip()
    approved_template_name = (payload.get("approved_template_name") or "").strip()
    approved_template_locale = (payload.get("approved_template_locale") or "es_mx").strip() or "es_mx"
    approved_template_custom_name = (payload.get("approved_template_custom_name") or "").strip()
    template_variables = (payload.get("template_variables") or "").strip()
    followup_delay_minutes = _normalize_delay_minutes(payload.get("followup_delay_minutes"))
    return_to_sam_enabled = _normalize_bool(payload.get("return_to_sam_enabled"), default=True)
    return_to_sam_message = (payload.get("return_to_sam_message") or DEFAULT_RETURN_TO_SAM_MESSAGE).strip() or DEFAULT_RETURN_TO_SAM_MESSAGE

    if not campaign_name:
        raise ValueError("Debes indicar un nombre para la campaña.")
    if campaign_kind not in PROACTIVE_CAMPAIGN_KINDS:
        raise ValueError("El tipo de campaña seleccionado no es válido.")
    if attachment_url and not attachment_filename:
        raise ValueError("Si capturas una URL de adjunto, también debes indicar el nombre del archivo.")

    audience_file_id = 0
    recipients = []
    if audience_file_id_raw:
        if not audience_file_id_raw.isdigit():
            raise ValueError("La lista guardada seleccionada no es válida.")
        audience_file_id = int(audience_file_id_raw)
        recipients, stored_audience_label = _get_saved_audience_recipients(local_storage, audience_file_id)
        if not audience_name:
            audience_name = stored_audience_label
    else:
        recipients = parse_outgoing_recipients(recipients_text)

    if not audience_name:
        raise ValueError("Debes indicar un nombre para la lista o segmento.")

    template_name = approved_template_name
    if template_name == "custom":
        template_name = approved_template_custom_name
    if not template_name:
        raise ValueError("Debes seleccionar o capturar el nombre de la plantilla aprobada.")
    approved_template_name = template_name
    if not message_body:
        raise ValueError("Debes escribir el mensaje libre principal que recibirán los destinatarios.")

    normalized_scheduled_at = ""
    if scheduled_at:
        scheduled_dt = parse_scheduled_datetime(scheduled_at)
        if not scheduled_dt:
            raise ValueError("La fecha programada no tiene un formato válido.")
        normalized_scheduled_at = scheduled_dt.strftime("%Y-%m-%d %H:%M:%S")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "scheduled" if normalized_scheduled_at else "draft"

    campaign = local_storage.Insert(
        OutgoingCampaign(
            name=campaign_name,
            audienceName=audience_name,
            audienceFileId=audience_file_id,
            message=message_body,
            messageMode=message_mode,
            campaignKind=campaign_kind,
            approvedTemplateName=approved_template_name,
            approvedTemplateLocale=approved_template_locale,
            approvedTemplateVariables=template_variables,
            followupDelayMinutes=followup_delay_minutes,
            attachmentUrl=attachment_url,
            attachmentFilename=attachment_filename,
            returnToSamEnabled=return_to_sam_enabled,
            returnToSamMessage=return_to_sam_message,
            status=status,
            transport=transport,
            scheduledAt=normalized_scheduled_at,
            createdAt=now,
            createdBy=created_by,
            lastRunAt="",
            lastError="",
        )
    )

    if not campaign or not hasattr(campaign, "id"):
        raise ValueError("No se pudo guardar la campaña.")

    recipient_models = []
    for recipient in recipients:
        recipient_models.append(
            OutgoingRecipient(
                campaign_id=campaign.id,
                name=recipient["name"],
                phone=recipient["phone"],
                status="pending",
                deliveryStage="pending_hook",
                sentAt="",
                lastAttemptAt="",
                errorType="",
                providerStatus="pending",
                providerMessageId="",
                providerPayload="",
                errorMessage="",
                hookSentAt="",
                freeMessageSentAt="",
                returnToSamSentAt="",
                seenAt="",
                repliedAt="",
                replyText="",
                metadata=json.dumps(recipient["metadata"], ensure_ascii=True),
            )
        )

    insert_result = local_storage.Insert(recipient_models)
    if not insert_result:
        local_storage.Remove(campaign)
        raise ValueError("No se pudieron guardar los destinatarios de la campaña.")

    return {
        "status": True,
        "message": f"Campaña '{campaign_name}' guardada con {len(recipients)} destinatarios.",
        "campaign_id": campaign.id,
        "recipient_count": len(recipients),
    }


def delete_outgoing_campaign(local_storage: LocalStorage, campaign_id: int) -> dict:
    campaign = local_storage.GetByPK(OutgoingCampaign, campaign_id)
    if not campaign:
        raise ValueError("No se encontró la campaña solicitada.")

    campaign.status = "deleted"
    if not local_storage.Update(campaign):
        raise ValueError("No se pudo ocultar la campaña.")

    return {
        "status": True,
        "message": f"Campaña '{campaign.name}' ocultada correctamente.",
        "campaign_id": campaign_id,
    }


def _get_chat2desk_headers() -> dict:
    api_token = os.getenv("CHAT2DESK_API_TOKEN")
    if not api_token:
        raise OutgoingDeliveryError("config", "No existe CHAT2DESK_API_TOKEN en el entorno.")
    return {
        "Authorization": api_token.strip(),
        "Content-Type": "application/json",
    }


def _format_phone_for_chat2desk(phone: str) -> str:
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if len(digits) == 10:
        return f"521{digits}"
    if len(digits) == 12 and digits.startswith("52"):
        return f"521{digits[2:]}"
    if len(digits) == 13 and digits.startswith("521"):
        return digits
    return digits


def _resolve_chat2desk_client_id(phone: str, transport: str = "wa_direct") -> int:
    base_url = "https://api.chat2desk.com.mx/v1"
    headers = _get_chat2desk_headers()
    formatted_phone = _format_phone_for_chat2desk(phone)

    search_response = requests.get(
        f"{base_url}/clients",
        params={"phone": formatted_phone},
        headers=headers,
        timeout=30,
    )
    try:
        search_response.raise_for_status()
    except requests.HTTPError as e:
        raise OutgoingDeliveryError(
            "chat2desk_search",
            f"Chat2Desk devolvió HTTP {search_response.status_code} al buscar el cliente.",
            payload=_safe_json_response(search_response),
            status_code=search_response.status_code,
        ) from e
    search_payload = search_response.json()
    data = search_payload.get("data") or []
    if search_payload.get("status") == "success" and data:
        return int(data[0]["id"])

    create_response = requests.post(
        f"{base_url}/clients",
        json={"phone": formatted_phone, "transport": transport},
        headers=headers,
        timeout=30,
    )
    try:
        create_response.raise_for_status()
    except requests.HTTPError as e:
        raise OutgoingDeliveryError(
            "chat2desk_create_client",
            f"Chat2Desk devolvió HTTP {create_response.status_code} al crear el cliente.",
            payload=_safe_json_response(create_response),
            status_code=create_response.status_code,
        ) from e
    create_payload = create_response.json()
    if create_payload.get("status") != "success":
        raise OutgoingDeliveryError(
            "chat2desk_create_client",
            f"No se pudo crear cliente en Chat2Desk para {formatted_phone}.",
            payload=create_payload,
        )

    created = create_payload.get("data") or {}
    if not created.get("id"):
        raise OutgoingDeliveryError(
            "chat2desk_create_client",
            f"Chat2Desk no devolvió client_id para {formatted_phone}.",
            payload=create_payload,
        )
    return int(created["id"])


def _send_chat2desk_outgoing_message(
    client_id: int,
    channel_id: int,
    transport: str,
    text: str,
    attachment_url: str = "",
    attachment_filename: str = "",
) -> dict:
    request_payload = {
        "client_id": client_id,
        "channel_id": channel_id,
        "transport": transport,
        "text": text,
    }
    if attachment_url:
        request_payload["attachment"] = attachment_url
        request_payload["attachment_filename"] = attachment_filename or "attachment"
    logger.critical(
        "📤 [OUTGOING CAMPAIGN] attempt client_id=%s channel_id=%s transport=%s text_preview=%s attachment=%s attachment_filename=%s",
        client_id,
        channel_id,
        transport,
        _build_text_preview(text),
        attachment_url,
        attachment_filename,
    )
    try:
        response = requests.post(
            "https://api.chat2desk.com.mx/v1/messages",
            headers=_get_chat2desk_headers(),
            json=request_payload,
            timeout=30,
        )
    except requests.Timeout as e:
        raise OutgoingDeliveryError(
            "chat2desk_send",
            "Timeout al enviar el mensaje a Chat2Desk.",
            payload={"request": request_payload},
        ) from e
    except requests.RequestException as e:
        raise OutgoingDeliveryError(
            "render_or_network",
            f"Error de red al comunicarse con Chat2Desk: {e}",
            payload={"request": request_payload},
        ) from e

    try:
        response.raise_for_status()
    except requests.HTTPError as e:
        raise OutgoingDeliveryError(
            "chat2desk_send",
            f"Chat2Desk devolvió HTTP {response.status_code} al enviar el mensaje.",
            payload={"request": request_payload, "response": _safe_json_response(response)},
            status_code=response.status_code,
        ) from e

    payload = _safe_json_response(response)
    if payload.get("status") != "success":
        raise OutgoingDeliveryError(
            "chat2desk_send",
            "Chat2Desk rechazó el envío.",
            payload={"request": request_payload, "response": payload},
        )
    provider_data = payload.get("data") or {}
    logger.critical(
        "📥 [OUTGOING CAMPAIGN] accepted client_id=%s channel_id=%s provider_message_id=%s request_id=%s dialog_id=%s status=%s",
        client_id,
        channel_id,
        provider_data.get("message_id") or provider_data.get("id") or "",
        provider_data.get("request_id") or "",
        provider_data.get("dialog_id") or "",
        payload.get("status"),
    )
    return {"request": request_payload, "response": payload}


def _resolve_recipient_stage(recipient) -> str:
    stage = getattr(recipient, "deliveryStage", "") or ""
    if stage:
        return stage
    if getattr(recipient, "status", "") == "failed":
        return "failed"
    if getattr(recipient, "sentAt", ""):
        return "completed"
    return "pending_hook"


def _resolve_campaign_delivery_status(recipients) -> str:
    if not recipients:
        return "failed"

    stages = [_resolve_recipient_stage(recipient) for recipient in recipients]
    failed_count = sum(1 for stage in stages if stage == "failed")
    completed_count = sum(1 for stage in stages if stage == "completed")
    in_flight_count = sum(1 for stage in stages if stage in {"pending_hook", "waiting_window", "pending_free_message", "pending_return_to_sam"})

    if in_flight_count > 0:
        return "processing"
    if completed_count > 0 and failed_count > 0:
        return "completed_with_errors"
    if completed_count > 0:
        return "completed"
    return "failed"


def _get_campaign_channel_id() -> int:
    raw_channel_id = os.getenv("CHAT2DESK_CHANNEL_ID") or str(DEFAULT_CHAT2DESK_CHANNEL_ID)
    try:
        return int(raw_channel_id)
    except ValueError as e:
        raise OutgoingDeliveryError("config", f"CHAT2DESK_CHANNEL_ID inválido: {raw_channel_id}") from e


def _send_campaign_stage_message(
    campaign_id: int,
    campaign,
    recipient,
    *,
    channel_id: int,
    stage: str,
    text: str,
    attachment_url: str = "",
    attachment_filename: str = "",
) -> dict:
    client_id = _resolve_chat2desk_client_id(recipient.phone, campaign.transport or "wa_direct")
    provider_payload = _send_chat2desk_outgoing_message(
        client_id=client_id,
        channel_id=channel_id,
        transport=campaign.transport or "wa_direct",
        text=text,
        attachment_url=attachment_url,
        attachment_filename=attachment_filename,
    )
    provider_data = (provider_payload.get("response") or {}).get("data") or {}
    logger.critical(
        "📨 [OUTGOING CAMPAIGN] campaign_id=%s phone=%s stage=%s client_id=%s channel_id=%s provider_message_id=%s request_id=%s text_preview=%s",
        campaign_id,
        recipient.phone,
        stage,
        client_id,
        channel_id,
        provider_data.get("message_id") or provider_data.get("id") or "",
        provider_data.get("request_id") or "",
        _build_text_preview(text),
    )
    logger.info(
        "Outgoing campaign %s stage %s sent to %s via Chat2Desk. client_id=%s channel_id=%s",
        campaign_id,
        stage,
        recipient.phone,
        client_id,
        channel_id,
    )
    return provider_payload


def _is_followup_due(recipient, delay_minutes: int, now: datetime) -> bool:
    hook_sent_at = _parse_datetime_or_none(getattr(recipient, "hookSentAt", "") or "")
    if not hook_sent_at:
        return False
    return now >= (hook_sent_at + timedelta(minutes=delay_minutes))


def send_outgoing_campaign(local_storage: LocalStorage, campaign_id: int, *, now: datetime | None = None) -> dict:
    campaign = local_storage.GetByPK(OutgoingCampaign, campaign_id)
    if not campaign:
        raise ValueError("No se encontró la campaña solicitada.")
    if (campaign.status or "").lower() == "deleted":
        raise ValueError("La campaña fue ocultada y ya no puede enviarse.")

    recipients = local_storage.Search(OutgoingRecipient(campaign_id=campaign_id), order="asc") or []
    if not recipients:
        raise ValueError("La campaña no tiene destinatarios para enviar.")
    actionable_recipients = [
        recipient for recipient in recipients
        if _resolve_recipient_stage(recipient) in {"pending_hook", "waiting_window", "pending_free_message", "pending_return_to_sam"}
    ]
    if not actionable_recipients:
        raise ValueError("La campaña ya no tiene destinatarios pendientes por procesar.")

    campaign.status = "processing"
    local_storage.Update(campaign)

    now = now or datetime.now()
    hook_sent_count = 0
    free_sent_count = 0
    return_sent_count = 0
    failed_count = 0
    waiting_window_count = 0
    campaign.lastRunAt = now.strftime("%Y-%m-%d %H:%M:%S")
    campaign.lastError = ""
    try:
        channel_id = _get_campaign_channel_id()
    except OutgoingDeliveryError as e:
        campaign.status = "failed"
        campaign.lastError = e.message
        local_storage.Update(campaign)
        raise e

    for recipient in actionable_recipients:
        recipient.lastAttemptAt = now.strftime("%Y-%m-%d %H:%M:%S")
        stage = _resolve_recipient_stage(recipient)
        try:
            if stage == "pending_hook":
                delay_minutes = int(getattr(campaign, "followupDelayMinutes", 15) or 15)
                hook_attachment_url, hook_attachment_filename = _get_fixed_hsm_attachment(
                    getattr(campaign, "approvedTemplateName", "") or ""
                )
                provider_payload = _send_campaign_stage_message(
                    campaign_id,
                    campaign,
                    recipient,
                    channel_id=channel_id,
                    stage="hook",
                    text=_build_hsm_message(
                        getattr(campaign, "approvedTemplateName", "") or "",
                        getattr(campaign, "approvedTemplateLocale", "es_mx") or "es_mx",
                        getattr(campaign, "approvedTemplateVariables", "") or "",
                    ),
                    attachment_url=hook_attachment_url,
                    attachment_filename=hook_attachment_filename,
                )
                provider_data = (provider_payload.get("response") or {}).get("data") or {}
                recipient.deliveryStage = "pending_free_message" if delay_minutes == 0 else "waiting_window"
                recipient.status = "processing"
                recipient.hookSentAt = now.strftime("%Y-%m-%d %H:%M:%S")
                recipient.providerStatus = "hook_sent"
                recipient.providerMessageId = str(provider_data.get("message_id") or provider_data.get("id") or "")
                recipient.providerPayload = _append_provider_event(recipient.providerPayload, "hook", provider_payload)
                recipient.errorType = ""
                recipient.errorMessage = ""
                local_storage.Update(recipient)
                hook_sent_count += 1
                stage = recipient.deliveryStage

            delay_minutes = int(getattr(campaign, "followupDelayMinutes", 15) or 15)
            if stage == "waiting_window" and not _is_followup_due(recipient, delay_minutes, now):
                waiting_window_count += 1
                continue

            if stage in {"waiting_window", "pending_free_message"}:
                provider_payload = _send_campaign_stage_message(
                    campaign_id,
                    campaign,
                    recipient,
                    channel_id=channel_id,
                    stage="free_message",
                    text=campaign.message,
                    attachment_url=getattr(campaign, "attachmentUrl", "") or "",
                    attachment_filename=getattr(campaign, "attachmentFilename", "") or "",
                )
                provider_data = (provider_payload.get("response") or {}).get("data") or {}
                recipient.freeMessageSentAt = now.strftime("%Y-%m-%d %H:%M:%S")
                recipient.sentAt = recipient.freeMessageSentAt
                recipient.providerStatus = "free_message_sent"
                recipient.providerMessageId = str(provider_data.get("message_id") or provider_data.get("id") or "")
                recipient.providerPayload = _append_provider_event(recipient.providerPayload, "free_message", provider_payload)
                recipient.errorType = ""
                recipient.errorMessage = ""
                free_sent_count += 1
                if _normalize_bool(getattr(campaign, "returnToSamEnabled", False), default=False):
                    recipient.deliveryStage = "pending_return_to_sam"
                else:
                    recipient.deliveryStage = "completed"
                    recipient.status = "sent"
                local_storage.Update(recipient)
                stage = recipient.deliveryStage

            if stage == "pending_return_to_sam":
                provider_payload = _send_campaign_stage_message(
                    campaign_id,
                    campaign,
                    recipient,
                    channel_id=channel_id,
                    stage="return_to_sam",
                    text=(getattr(campaign, "returnToSamMessage", "") or DEFAULT_RETURN_TO_SAM_MESSAGE),
                )
                provider_data = (provider_payload.get("response") or {}).get("data") or {}
                recipient.returnToSamSentAt = now.strftime("%Y-%m-%d %H:%M:%S")
                recipient.deliveryStage = "completed"
                recipient.status = "sent"
                recipient.providerStatus = "return_to_sam_sent"
                recipient.providerMessageId = str(provider_data.get("message_id") or provider_data.get("id") or "")
                recipient.providerPayload = _append_provider_event(recipient.providerPayload, "return_to_sam", provider_payload)
                recipient.errorType = ""
                recipient.errorMessage = ""
                local_storage.Update(recipient)
                return_sent_count += 1
                continue
        except OutgoingDeliveryError as e:
            recipient.status = "failed"
            recipient.deliveryStage = "failed"
            recipient.errorType = _build_error_type(e.source, e.message, e.status_code)
            recipient.providerStatus = e.source
            recipient.providerMessageId = ""
            recipient.providerPayload = _append_provider_event(recipient.providerPayload, "error", e.payload)
            recipient.errorMessage = e.message
            local_storage.Update(recipient)
            failed_count += 1
            logger.error(
                "Outgoing campaign %s failed for %s. stage=%s type=%s source=%s detail=%s payload=%s",
                campaign_id,
                recipient.phone,
                stage,
                recipient.errorType,
                e.source,
                e.message,
                recipient.providerPayload,
            )
        except Exception as e:
            recipient.status = "failed"
            recipient.deliveryStage = "failed"
            recipient.errorType = _build_error_type("app", str(e))
            recipient.providerStatus = "app"
            recipient.providerMessageId = ""
            recipient.providerPayload = _append_provider_event(recipient.providerPayload, "exception", {"exception": str(e)})
            recipient.errorMessage = str(e)
            local_storage.Update(recipient)
            failed_count += 1
            logger.exception("Unexpected error sending campaign %s to %s", campaign_id, recipient.phone)

    campaign.status = _resolve_campaign_delivery_status(local_storage.Search(OutgoingRecipient(campaign_id=campaign_id), order="asc") or [])
    if failed_count:
        campaign.lastError = (
            f"Proceso con errores. Ganchos: {hook_sent_count}. "
            f"Mensajes libres: {free_sent_count}. Regresos a GUERRERO: {return_sent_count}. Fallidos: {failed_count}."
        )
    local_storage.Update(campaign)

    return {
        "status": True,
        "message": (
            f"Proceso terminado. Ganchos enviados: {hook_sent_count}. "
            f"Mensajes libres enviados: {free_sent_count}. "
            f"Regresos a GUERRERO: {return_sent_count}. "
            f"Esperando ventana: {waiting_window_count}. Fallidos: {failed_count}."
        ),
        "hook_sent_count": hook_sent_count,
        "free_sent_count": free_sent_count,
        "return_sent_count": return_sent_count,
        "waiting_window_count": waiting_window_count,
        "failed_count": failed_count,
    }


def parse_scheduled_datetime(raw_value: str) -> datetime | None:
    return _parse_datetime_or_none(raw_value)


def process_due_outgoing_campaigns(local_storage: LocalStorage) -> list[dict]:
    campaigns = local_storage.GetAll(OutgoingCampaign) or []
    now = datetime.now()
    processed = []

    for campaign in campaigns:
        campaign_status = (campaign.status or "").lower()
        if campaign_status not in {"scheduled", "processing"}:
            continue
        scheduled_dt = parse_scheduled_datetime(campaign.scheduledAt)
        if campaign_status == "scheduled" and (not scheduled_dt or scheduled_dt > now):
            continue
        recipients = local_storage.Search(OutgoingRecipient(campaign_id=campaign.id), order="asc") or []
        if not recipients:
            campaign.status = "failed"
            local_storage.Update(campaign)
            processed.append({"campaign_id": campaign.id, "error": "La campaña no tiene destinatarios."})
            continue
        if campaign_status == "processing" and not any(
            _resolve_recipient_stage(recipient) in {"pending_hook", "waiting_window", "pending_free_message", "pending_return_to_sam"}
            for recipient in recipients
        ):
            campaign.status = _resolve_campaign_delivery_status(recipients)
            local_storage.Update(campaign)
            processed.append({"campaign_id": campaign.id, "status": campaign.status})
            continue
        try:
            result = send_outgoing_campaign(local_storage, campaign.id, now=now)
            processed.append({"campaign_id": campaign.id, "result": result})
        except Exception as e:
            logger.error("Error processing scheduled campaign %s: %s", getattr(campaign, "id", "unknown"), e)
            campaign.status = "failed"
            campaign.lastRunAt = now.strftime("%Y-%m-%d %H:%M:%S")
            local_storage.Update(campaign)
            processed.append({"campaign_id": campaign.id, "error": str(e)})

    return processed

class Context:
    def __init__(self, fragment, method, payload=None):
        self.__fragment = fragment
        self.__ls = LocalStorage()
        self.method = method
        self.payload = payload
        if self.payload and 'file' in self.payload:
            self.payload['file'] = self.payload['file'].filename
    
    def prepare(self, **kwargs):
        configs = { c.name:c.value for c in self.__ls.GetAll(Config) }
        q = "SELECT CASE WHEN EXISTS (SELECT 1 FROM notifications WHERE \"nAck\" = false) THEN 'true' ELSE 'false' END AS \"hasNotifications\""
        response = self.__ls.GetAll(Notification, q, True)[0]
        response["power"] = (configs.get("power") or "false") == "true"

        if hasattr(self, f"_Context__{self.__fragment}"):
            response.update(getattr(self, f"_Context__{self.__fragment}")(**kwargs))
        
        return response
    
    def __dashboard(self, **kwargs):
        q = "SELECT * FROM calls WHERE DATE(\"callTime\") = DATE('now');"
        calls = self.__ls.GetAll(Call, q, True)
        inp = [c for c in calls if 'progress' in c['callStatus'].lower() ]

        for c in inp:
            c['callTime'] = c['callTime'].split(' ')[1] 

        response = {
            "title": "Dashboard",
            "graphs": [],
            "calls": inp,
            "inProgress": len([c for c in calls if 'progress' in c['callStatus'].lower() ]),
            "completed": len([c for c in calls if c['callStatus'] in ['COMPLETED', 'PARTIAL_COMPLETED'] ]),
            "noContact": len([c for c in calls if 'NO_CONTACT' == c['callStatus'] ]),
            "amd": len([c for c in calls if 'AMD' == c['callStatus'] ])
        }

        days = kwargs.get("days") or "15"
        q = "SELECT DATE(\"callTime\") AS callDate, COUNT(*) AS totalCalls FROM calls WHERE \"callStatus\" = '{}' AND DATE(\"callTime\") >= CURRENT_DATE - INTERVAL '{} days' GROUP BY callDate ORDER BY callDate DESC"
        for status in ['COMPLETED', 'NO_CONTACT', 'AMD']:
            response['graphs'].append({ "type": status, "records": self.__ls.GetAll(Call, q.format(status, days), True) })

        return response

    def __logs(self, **kwargs):
        call = self.__ls.GetByPK(Call, kwargs['id'], json=True)
        return { "logs": call['callLogs'] }

    def __audio(self, **kwargs):
        call = self.__ls.GetByPK(Call, kwargs['id'], json=True)
        if call["callPlayback"]:
            return { "audios": json.loads(call['callPlayback']) }
        
        return { "audios": [] }
    
    def __script(self, **kwargs):
        call = self.__ls.GetByPK(Call, kwargs['id'], json=True)
        if call["callScript"]:
            return { "script": json.loads(call['callScript']) }
        
        return { "script": [] }
    
    def __messages(self, **kwargs):
        messages = self.__ls.Search(Message(number=kwargs['id']), json=True, order='asc')
        return { "script": messages }

    def __health(self, **kwargs):
        return { "title": "System Health"}
    
    def __callfiles(self, **kwargs):
        Thread(target=InitOutboundCalls, args=(kwargs['id'], )).start()
        return { "message": "The call initialization process has been started in BACKGROUND!" }
    
    def __remfiles(self, **kwargs):
        file = self.__ls.Search(File(name=kwargs['id']), True)
        
        if file:
            self.__ls.Remove(file)
        
        return {
            "files": self.__ls.GetAll(File, cols=['name', 'ftype'], json=True)
        }

    def __chats(self, **kwargs):
        q = 'SELECT "senderName", number, MAX(time) AS time FROM messages GROUP BY "senderName", number;'
        messages = self.__ls.GetAll(Message, q, json=True)

        return { "title": "Chat Records", "logs": messages }

    def __calls(self, **kwargs):
        excluded = ['callScript', 'callLogs', 'callPlayback']
        logs = self.__ls.GetAll(Call, json=True)

        if "person" in kwargs:
            logs = [ log for log in logs if log["callerName"] == kwargs["person"]]
        
        if "filter" in kwargs:
            logs = [ log for log in logs if log["callStatus"] == kwargs["filter"]]

        for log in logs:
            if log['callDuration'] == None:
                continue

            minutes = log['callDuration'] // 60
            seconds = log['callDuration'] % 60
            log['callDuration'] = f"{minutes:02d}:{seconds:02d}"

            log["hasChat"] = log["callScript"] != None
            log["hasLogs"] = log["callLogs"] != None
            log["hasPlayback"] = log["callPlayback"] != None

            for col in excluded:
                if col in log:
                    del log[col]

        return {
            "title": "Call Logs",
            "logs": reversed(logs)
        }

    def __settings(self, **kwargs):
        configs = { c.name:c.getval() for c in self.__ls.GetAll(Config) }
        configs["datetime"] = datetime.now().strftime('%Y-%m-%dT%H:%M')
        configs["models"] = []

        client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        for model in client.models.list().data:
            model_dict = {
                'id': model.id,
                'created_at': model.created if hasattr(model, 'created') else '',
                'owner': model.owned_by if hasattr(model, 'owned_by') else ''
            }
            configs["models"].append(model_dict)

        prompt = configs.get("prompt", "")
        if "prompt" in configs:
            del configs["prompt"]

        return {
            "title": "Robot Configurations",
            "prompt": prompt,
            "files": self.__ls.GetAll(File, cols=['name', 'ftype'], json=True),
            "configs": configs
        }

    def __notifications(self, **kwargs):
        return {
            "title": "Notifications",
            "notifications": self.__ls.GetAll(Notification, json=True)
        }
    
    def __power(self, **kwargs):
        power = [ c for c in self.__ls.GetAll(Config) if c.name == 'power' ][0]
        power.value = str(kwargs['id'] == '1').lower()
        self.__ls.Update(power)
        return { "status": True }
    
    def __configs(self, **kwargs):
        if self.payload:
            if "datetime" in self.payload:
                datetime_obj = datetime.strptime(self.payload["datetime"], '%Y-%m-%dT%H:%M')
                if platform.system() == 'Windows':
                    formatted_time = datetime_obj.strftime('%m-%d-%Y %H:%M:%S')
                    os.system(f'date {formatted_time.split()[0]}')
                    os.system(f'time {formatted_time.split()[1]}')
                else:
                    formatted_time = datetime_obj.strftime('%Y-%m-%d %H:%M:%S')
                    os.system(f'date -s "{formatted_time}"')
                del self.payload["datetime"]

            for key, value in self.payload.items():
                config = Config(name=key)
                config = self.__ls.Search(config, True, False)
                if config:
                    config.value = value
                    self.__ls.Update(config)
                else:
                    self.__ls.Insert(Config(name=key, value=value))
        return { "status": True }
