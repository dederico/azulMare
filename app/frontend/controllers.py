import json
import os
import platform
import re
import sys
import importlib
import requests
from pathlib import Path
from openai import OpenAI
from datetime import datetime
from threading import Thread
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
# Recipient field keys must be a single token like Nombre, Numero, K, Colonia or Calle.
# Allowing spaces here caused values such as "Maria Felix Numero" to be parsed as a key.
RECIPIENT_FIELD_PATTERN = re.compile(
    r"([A-Za-zÁÉÍÓÚÑáéíóúñ0-9_]+)\s*:\s*",
    re.UNICODE,
)
DEFAULT_CHAT2DESK_CHANNEL_ID = 43906


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
        key = _normalize_recipient_key(raw_key)
        value = raw_value.strip().strip(",;")
        if key and value:
            parsed[key] = value

    name = parsed.get("nombre") or parsed.get("name") or parsed.get("contacto") or ""
    phone = (
        parsed.get("numero")
        or parsed.get("telefono")
        or parsed.get("telefono_whatsapp")
        or parsed.get("whatsapp")
        or parsed.get("celular")
        or parsed.get("phone")
    )

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
        if key not in {"nombre", "name", "contacto", "numero", "telefono", "telefono_whatsapp", "whatsapp", "celular", "phone"}
    }

    return {
        "name": name or "Sin nombre",
        "phone": _normalize_phone_number(phone),
        "metadata": metadata,
    }


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


def list_outgoing_campaigns(local_storage: LocalStorage) -> list[dict]:
    campaigns = local_storage.GetAll(OutgoingCampaign, json=True) or []
    campaigns = [campaign for campaign in campaigns if (campaign.get("status") or "").lower() != "deleted"]
    campaigns = list(reversed(campaigns))
    enriched = []
    for campaign in campaigns:
        recipients = local_storage.Search(OutgoingRecipient(campaign_id=campaign["id"]), json=True, order="asc") or []
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
                "ks": ks,
                "recipients": [
                    {
                        **recipient,
                        "metadataParsed": json.loads(recipient.get("metadata") or "{}"),
                    }
                    for recipient in recipients
                ],
            }
        )
    return enriched


def create_outgoing_campaign(local_storage: LocalStorage, payload: dict) -> dict:
    campaign_name = (payload.get("campaign_name") or "").strip()
    audience_name = (payload.get("audience_name") or "").strip()
    message_body = (payload.get("message_body") or "").strip()
    scheduled_at = (payload.get("scheduled_at") or "").strip()
    created_by = (payload.get("created_by") or "").strip() or "atencion_ciudadana"
    transport = (payload.get("transport") or "wa_direct").strip() or "wa_direct"
    recipients_text = payload.get("recipients_text") or ""

    if not campaign_name:
        raise ValueError("Debes indicar un nombre para la campaña.")
    if not audience_name:
        raise ValueError("Debes indicar un nombre para la lista o segmento.")
    if not message_body:
        raise ValueError("Debes escribir el mensaje que recibirán los destinatarios.")

    normalized_scheduled_at = ""
    if scheduled_at:
        scheduled_dt = parse_scheduled_datetime(scheduled_at)
        if not scheduled_dt:
            raise ValueError("La fecha programada no tiene un formato válido.")
        normalized_scheduled_at = scheduled_dt.strftime("%Y-%m-%d %H:%M:%S")

    recipients = parse_outgoing_recipients(recipients_text)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "scheduled" if normalized_scheduled_at else "draft"

    campaign = local_storage.Insert(
        OutgoingCampaign(
            name=campaign_name,
            audienceName=audience_name,
            message=message_body,
            status=status,
            transport=transport,
            scheduledAt=normalized_scheduled_at,
            createdAt=now,
            createdBy=created_by,
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
                sentAt="",
                errorMessage="",
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
        raise ValueError("No existe CHAT2DESK_API_TOKEN en el entorno.")
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
    search_response.raise_for_status()
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
    create_response.raise_for_status()
    create_payload = create_response.json()
    if create_payload.get("status") != "success":
        raise ValueError(f"No se pudo crear cliente en Chat2Desk para {formatted_phone}.")

    created = create_payload.get("data") or {}
    if not created.get("id"):
        raise ValueError(f"Chat2Desk no devolvió client_id para {formatted_phone}.")
    return int(created["id"])


def _send_chat2desk_outgoing_message(client_id: int, channel_id: int, transport: str, text: str) -> None:
    response = requests.post(
        "https://api.chat2desk.com.mx/v1/messages",
        headers=_get_chat2desk_headers(),
        json={
            "client_id": client_id,
            "channel_id": channel_id,
            "transport": transport,
            "text": text,
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "success":
        raise ValueError(f"Chat2Desk rechazó el envío: {payload}")


def _resolve_campaign_delivery_status(recipients) -> str:
    if not recipients:
        return "failed"

    sent_count = sum(1 for recipient in recipients if (recipient.status or "").lower() == "sent")
    failed_count = sum(1 for recipient in recipients if (recipient.status or "").lower() == "failed")
    pending_count = sum(1 for recipient in recipients if (recipient.status or "pending").lower() == "pending")

    if pending_count > 0:
        return "processing"
    if sent_count > 0 and failed_count > 0:
        return "completed_with_errors"
    if sent_count > 0:
        return "completed"
    return "failed"


def send_outgoing_campaign(local_storage: LocalStorage, campaign_id: int) -> dict:
    campaign = local_storage.GetByPK(OutgoingCampaign, campaign_id)
    if not campaign:
        raise ValueError("No se encontró la campaña solicitada.")
    if (campaign.status or "").lower() == "deleted":
        raise ValueError("La campaña fue ocultada y ya no puede enviarse.")

    recipients = local_storage.Search(OutgoingRecipient(campaign_id=campaign_id), order="asc") or []
    pending_recipients = [recipient for recipient in recipients if (recipient.status or "pending") == "pending"]
    if not recipients:
        raise ValueError("La campaña no tiene destinatarios para enviar.")
    if not pending_recipients:
        raise ValueError("La campaña ya no tiene destinatarios pendientes por enviar.")

    campaign.status = "processing"
    local_storage.Update(campaign)

    sent_count = 0
    failed_count = 0
    channel_id = int(os.getenv("CHAT2DESK_CHANNEL_ID") or DEFAULT_CHAT2DESK_CHANNEL_ID)

    for recipient in pending_recipients:
        try:
            client_id = _resolve_chat2desk_client_id(recipient.phone, campaign.transport or "wa_direct")
            _send_chat2desk_outgoing_message(
                client_id=client_id,
                channel_id=channel_id,
                transport=campaign.transport or "wa_direct",
                text=campaign.message,
            )
            recipient.status = "sent"
            recipient.sentAt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            recipient.errorMessage = ""
            local_storage.Update(recipient)
            sent_count += 1
        except Exception as e:
            recipient.status = "failed"
            recipient.errorMessage = str(e)
            local_storage.Update(recipient)
            failed_count += 1
            logger.error("Error sending campaign %s to %s: %s", campaign_id, recipient.phone, e)

    campaign.status = _resolve_campaign_delivery_status(local_storage.Search(OutgoingRecipient(campaign_id=campaign_id), order="asc") or [])
    local_storage.Update(campaign)

    return {
        "status": True,
        "message": f"Envío terminado. Enviados: {sent_count}. Fallidos: {failed_count}.",
        "sent_count": sent_count,
        "failed_count": failed_count,
    }


def parse_scheduled_datetime(raw_value: str) -> datetime | None:
    value = (raw_value or "").strip()
    if not value:
        return None

    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def process_due_outgoing_campaigns(local_storage: LocalStorage) -> list[dict]:
    campaigns = local_storage.GetAll(OutgoingCampaign) or []
    now = datetime.now()
    processed = []

    for campaign in campaigns:
        campaign_status = (campaign.status or "").lower()
        if campaign_status not in {"scheduled", "processing"}:
            continue
        scheduled_dt = parse_scheduled_datetime(campaign.scheduledAt)
        if not scheduled_dt or scheduled_dt > now:
            continue
        recipients = local_storage.Search(OutgoingRecipient(campaign_id=campaign.id), order="asc") or []
        if not recipients:
            campaign.status = "failed"
            local_storage.Update(campaign)
            processed.append({"campaign_id": campaign.id, "error": "La campaña no tiene destinatarios."})
            continue
        if campaign_status == "processing" and not any((recipient.status or "pending").lower() == "pending" for recipient in recipients):
            campaign.status = _resolve_campaign_delivery_status(recipients)
            local_storage.Update(campaign)
            processed.append({"campaign_id": campaign.id, "status": campaign.status})
            continue
        try:
            result = send_outgoing_campaign(local_storage, campaign.id)
            processed.append({"campaign_id": campaign.id, "result": result})
        except Exception as e:
            logger.error("Error processing scheduled campaign %s: %s", getattr(campaign, "id", "unknown"), e)
            campaign.status = "failed"
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
