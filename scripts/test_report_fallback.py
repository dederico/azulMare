#!/usr/bin/env python3
"""Smoke test seguro para la finalización y clasificación de reportes.

No llama a Chat2Desk ni crea folios en CIAC. Valida la misma política que usa
producción para evitar probar con reportes ciudadanos falsos.
"""

from __future__ import annotations

import argparse
import json
import sys
from urllib.request import urlopen
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.report_submission_policy import (  # noqa: E402
    extract_pending_report_answers,
    fallback_report_category_id,
    infer_high_confidence_report_category,
    next_missing_report_field,
    normalize_reporter_name_input,
    resolve_unambiguous_catalog_category,
    sidewalk_sign_category_options,
)


def check(name: str, actual, expected) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: esperado={expected!r}, obtenido={actual!r}")
    print(f"✅ {name}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        help="URL de Render; agrega una verificación remota de /health",
    )
    parser.add_argument(
        "--expected-sha",
        help="SHA completo o prefijo que debe estar desplegado",
    )
    return parser.parse_args()


def check_deployment(base_url: str, expected_sha: str | None) -> None:
    health_url = f"{base_url.rstrip('/')}/health"
    with urlopen(health_url, timeout=30) as response:  # noqa: S310
        if response.status != 200:
            raise AssertionError(f"{health_url} respondió HTTP {response.status}")
        health = json.load(response)

    deployed_sha = str(health.get("deployment_sha") or "")
    if not deployed_sha:
        raise AssertionError("El health check no devolvió deployment_sha")
    if expected_sha and not deployed_sha.startswith(expected_sha):
        raise AssertionError(
            f"Render tiene {deployed_sha}, se esperaba {expected_sha}"
        )
    print(f"✅ Render saludable; deployment_sha={deployed_sha}")
    print(
        "   métricas: "
        f"CPU={health.get('processor')}% "
        f"memoria={health.get('memory')}% "
        f"storage={health.get('storage')}%"
    )


def main() -> int:
    args = parse_args()
    prompt_path = PROJECT_ROOT / "prompty.py"
    prompt = prompt_path.read_text(encoding="utf-8")

    check("catálogo general CIAC", fallback_report_category_id(prompt), "486")
    check(
        "dirección enviada en un solo mensaje",
        extract_pending_report_answers(
            "selection5", "Encino 113\nFraccionamiento Olinalá"
        ),
        {
            "selection5": "Encino",
            "selection6": "113",
            "selection7": "Olinalá",
        },
    )
    check(
        "domicilio sin numeración",
        extract_pending_report_answers("selection6", "Sin número"),
        {"selection6": "0000"},
    )
    check(
        "FIN no se guarda como respuesta",
        extract_pending_report_answers("selection5", "FIN"),
        {},
    )
    check(
        "Gracias no se guarda como respuesta",
        extract_pending_report_answers("selection4", "Gracias"),
        {},
    )
    check(
        "omitir nombre se convierte en Anónimo",
        normalize_reporter_name_input("No"),
        "Anónimo",
    )

    known = infer_high_confidence_report_category(
        "Hay un bache profundo que obstruye el carril"
    ) or resolve_unambiguous_catalog_category(
        prompt, "Hay un bache profundo que obstruye el carril"
    )
    if known:
        print(f"✅ asunto conocido conserva clasificación especializada ({known})")
    else:
        raise AssertionError("El asunto conocido 'bache' no encontró categoría")

    unknown = resolve_unambiguous_catalog_category(
        prompt, "Un objeto extraño obstruye el acceso y no aparece en el catálogo"
    )
    check("asunto desconocido no inventa categoría", unknown, None)
    check("asunto desconocido usa fallback", fallback_report_category_id(prompt), "486")

    selections = {
        "selection1": "486",
        "selection2": "Anónimo",
        "selection4": "Un objeto extraño obstruye el acceso",
        "selection5": "Vasconcelos",
        "selection6": "0000",
        "selection7": "Centro",
    }
    check(
        "reporte con fallback queda listo para CIAC",
        next_missing_report_field(selections, prompt=prompt),
        None,
    )

    sidewalk = "Un letrero obstruye la banqueta"
    options = sidewalk_sign_category_options(prompt, sidewalk)
    if options:
        print("✅ ambigüedad fijo/móvil conserva pregunta especializada")
    else:
        print("ℹ️  El prompt actual no contiene ambas opciones fijo/móvil")

    if args.base_url:
        check_deployment(args.base_url, args.expected_sha)

    print("\nResultado: parche de reportes verificado correctamente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
