import os
import unicodedata
from pathlib import Path


GRADE_SHEET_ID = os.getenv("COLEGIO_GRADES_SPREADSHEET_ID") or os.getenv("SPREADSHEET_ID")
GRADE_SHEET_RANGE = os.getenv("COLEGIO_GRADES_SHEET_RANGE", "Calificaciones!A:Z")

_HEADER_ALIASES = {
    "matricula": {"matricula", "matrícula", "mat", "id", "id alumno", "id_alumno", "codigo", "codigo alumno"},
    "nombre": {"nombre", "nombre completo", "alumno", "estudiante", "nombre del alumno"},
    "calificacion": {
        "calificacion",
        "calificación",
        "promedio",
        "resultado",
        "calif",
        "final",
        "calificacion final",
        "calificación final",
    },
}


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).strip().lower()


def _get_credentials_file() -> str:
    env_path = os.getenv("COLEGIO_GRADES_CREDENTIALS_FILE")
    candidates = [
        env_path,
        str(Path(__file__).with_name("credentials.json")),
        str(Path(__file__).with_name("service_account_credentials.json")),
        str(Path(__file__).parents[1] / "credentials.json"),
        str(Path(__file__).parents[1] / "service_account_credentials.json"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise FileNotFoundError(
        "No se encontró archivo de credenciales para Google Sheets. "
        "Configura COLEGIO_GRADES_CREDENTIALS_FILE o coloca credentials.json en app/services/functions/implementations/."
    )


def _get_sheet_values():
    if not GRADE_SHEET_ID:
        raise ValueError("Falta configurar COLEGIO_GRADES_SPREADSHEET_ID o SPREADSHEET_ID.")

    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    credentials = service_account.Credentials.from_service_account_file(
        _get_credentials_file(),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    service = build("sheets", "v4", credentials=credentials)
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=GRADE_SHEET_ID, range=GRADE_SHEET_RANGE)
        .execute()
    )
    return result.get("values", [])


def _find_column_index(headers: list[str], logical_name: str) -> int | None:
    aliases = _HEADER_ALIASES[logical_name]
    for index, header in enumerate(headers):
        if _normalize_text(header) in aliases:
            return index
    return None


def _get_cell(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return str(row[index]).strip()


async def get_calificacion_alumno(nombre_alumno: str = "", matricula: str = ""):
    """Consultar la calificación de un alumno del Colegio Ciudadano de Excelencia y Disciplina en Nuevo León.

    nombre_alumno (string, optional): Nombre completo o parcial del alumno para buscar en la hoja.
    matricula (string, optional): Matrícula del alumno para buscar coincidencia exacta.

    Returns:
        string: Resultado con la calificación encontrada o un mensaje claro si no existe coincidencia.
    """
    nombre_alumno = (nombre_alumno or "").strip()
    matricula = (matricula or "").strip()

    if not nombre_alumno and not matricula:
        return "Necesito el nombre del alumno o su matrícula para consultar la calificación."

    try:
        values = _get_sheet_values()
    except Exception as exc:
        return f"No pude consultar la hoja de calificaciones: {exc}"

    if len(values) < 2:
        return "La hoja de calificaciones no tiene datos disponibles."

    headers = [str(cell).strip() for cell in values[0]]
    matricula_index = _find_column_index(headers, "matricula")
    nombre_index = _find_column_index(headers, "nombre")
    calificacion_index = _find_column_index(headers, "calificacion")

    if calificacion_index is None:
        return "No encontré una columna de calificación en la hoja."

    normalized_name = _normalize_text(nombre_alumno)
    normalized_matricula = _normalize_text(matricula)
    matches = []

    for row in values[1:]:
        row_matricula = _get_cell(row, matricula_index)
        row_nombre = _get_cell(row, nombre_index)
        row_calificacion = _get_cell(row, calificacion_index)

        if not row_calificacion:
            continue

        if normalized_matricula and _normalize_text(row_matricula) == normalized_matricula:
            matches.append((row_nombre, row_matricula, row_calificacion))
            continue

        if normalized_name and normalized_name in _normalize_text(row_nombre):
            matches.append((row_nombre, row_matricula, row_calificacion))

    if not matches:
        return "No encontré una calificación para el alumno indicado."

    if len(matches) > 1 and not normalized_matricula:
        preview = ", ".join(name or f"matrícula {mat}" for name, mat, _ in matches[:3])
        return (
            "Encontré varios alumnos con ese nombre. "
            f"Coincidencias: {preview}. Compárteme la matrícula para darte la calificación correcta."
        )

    alumno_nombre, alumno_matricula, alumno_calificacion = matches[0]
    parts = []
    if alumno_nombre:
        parts.append(f"Alumno: {alumno_nombre}")
    if alumno_matricula:
        parts.append(f"Matrícula: {alumno_matricula}")
    parts.append(f"Calificación: {alumno_calificacion}")
    return "\n".join(parts)
