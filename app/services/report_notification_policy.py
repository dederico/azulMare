import mimetypes
import unicodedata
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import unquote, urlparse


@dataclass(frozen=True)
class ReportStatusNotification:
    status: str
    text: str
    is_hsm: bool = False


@dataclass(frozen=True)
class OutboundAttachment:
    url: str
    filename: str
    content_type: str


def _normalize(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.casefold().split())


def normalize_report_status(value: str | None) -> str | None:
    normalized = _normalize(value)
    aliases = {
        "en progreso": "en_progreso",
        "en proceso": "en_progreso",
        "concluido": "concluido",
        "concluida": "concluido",
        "reactivado": "reactivado",
        "reactivada": "reactivado",
        "reactivacion": "reactivado",
        "reabierto": "reactivado",
        "reabierta": "reactivado",
        "reapertura": "reactivado",
    }
    return aliases.get(normalized)


def build_report_status_notification(
    report_id,
    report_status: str | None,
    additional_info: str | None = None,
) -> ReportStatusNotification | None:
    """Build the provider message for one explicit CIAC lifecycle event."""
    status = normalize_report_status(report_status)
    clean_report_id = str(report_id or "").strip()
    if not status or not clean_report_id:
        return None

    if status == "reactivado":
        # Chat2Desk's approved-template transport.  The citizen-facing template
        # renders: "Tu reporte con folio … ha sido reactivado …".
        return ReportStatusNotification(
            status=status,
            text=f"@HSM@\nnotifica_reactivacion|es_mx\n\n{clean_report_id}",
            is_hsm=True,
        )

    if status == "en_progreso":
        text = (
            f"Su reporte #{clean_report_id} ya se encuentra en proceso de atención. "
            "Un técnico está trabajando para resolver su solicitud lo antes posible."
        )
    else:
        text = (
            f"¡Buenas noticias! Su reporte #{clean_report_id} ha sido concluido "
            "satisfactoriamente. Gracias por su paciencia."
        )

    clean_additional_info = " ".join(str(additional_info or "").split()).strip()
    if clean_additional_info:
        text += f"\n\nInformación adicional: {clean_additional_info}"
    return ReportStatusNotification(status=status, text=text)


def _attachment_from_value(value, *, default_name: str) -> OutboundAttachment | None:
    if isinstance(value, str):
        url = value.strip()
        explicit_filename = ""
        explicit_content_type = ""
    elif isinstance(value, dict):
        nested_file = value.get("file") if isinstance(value.get("file"), dict) else {}
        url = str(
            value.get("url")
            or value.get("attachment")
            or nested_file.get("url")
            or ""
        ).strip()
        explicit_filename = str(
            value.get("filename")
            or value.get("original_file_name")
            or nested_file.get("filename")
            or ""
        ).strip()
        explicit_content_type = str(
            value.get("content_type")
            or value.get("mime_type")
            or nested_file.get("content_type")
            or ""
        ).strip().casefold()
    else:
        return None

    if not url.startswith(("http://", "https://")):
        return None

    url_name = unquote(PurePosixPath(urlparse(url).path).name).strip()
    filename = explicit_filename or url_name or default_name
    guessed_type, _ = mimetypes.guess_type(filename)
    content_type = explicit_content_type or guessed_type or "application/octet-stream"
    return OutboundAttachment(
        url=url,
        filename=filename,
        content_type=content_type,
    )


def extract_ciac_conclusion_attachments(data) -> list[OutboundAttachment]:
    """Read legacy ``imagen`` and future typed attachment collections.

    CIAC currently returns an array whose rows expose one ``imagen`` URL.  The
    collector also accepts typed ``attachments``/``archivos``/``documentos``
    fields so the boundary can carry PDFs without adding another special case.
    """
    records = data if isinstance(data, list) else [data]
    attachments: list[OutboundAttachment] = []
    seen_urls: set[str] = set()

    for record_index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            continue
        candidates = []
        for key in ("attachments", "adjuntos", "archivos", "documentos", "fotos"):
            value = record.get(key)
            if isinstance(value, list):
                candidates.extend(value)
            elif value:
                candidates.append(value)
        for key in ("imagen", "archivo", "documento"):
            if record.get(key):
                candidates.append(record[key])

        for candidate_index, candidate in enumerate(candidates, start=1):
            attachment = _attachment_from_value(
                candidate,
                default_name=f"evidencia-{record_index}-{candidate_index}",
            )
            if not attachment or attachment.url in seen_urls:
                continue
            seen_urls.add(attachment.url)
            attachments.append(attachment)

    return attachments
