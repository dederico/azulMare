import re
import unicodedata


# Catálogo preliminar construido con las acciones descritas en prompty.py y los
# contactos institucionales publicados en get_directorio.py. No contiene nombres
# de funcionarios ni expone identificadores internos del CIAC.
CONTACTOS = {
    "limpia": {
        "area": "Dirección de Arbolado, Limpia y Cultura Ambiental",
        "telefono": "81 8400 4400",
        "extension": "4208",
    },
    "pavimentacion": {
        "area": "Dirección de Pavimentación",
        "telefono": "81 8400 4400",
        "extension": "2749",
    },
    "parques": {
        "area": "Dirección de Parques de Colonia e Imagen Urbana",
        "telefono": "81 1052 4228",
        "extension": "",
    },
    "infraestructura_urbana": {
        "area": "Dirección de Infraestructura Urbana",
        "telefono": "81 8400 4400",
        "extension": "4336",
    },
    "infraestructura_hidrica": {
        "area": "Dirección de Infraestructura Hídrica",
        "telefono": "81 8400 4400",
        "extension": "4221",
    },
    "movilidad": {
        "area": "Dirección de Movilidad",
        "telefono": "81 8400 4400",
        "extension": "2150",
    },
}


SERVICIOS = (
    {
        "servicio": "Recolección de cacharros",
        "sinonimos": ("cacharros", "descacharrización", "muebles viejos", "enseres"),
        "contacto": CONTACTOS["limpia"],
    },
    {
        "servicio": "Recolección de ramas",
        "sinonimos": ("ramas", "residuo vegetal", "retiro de ramas"),
        "contacto": CONTACTOS["limpia"],
    },
    {
        "servicio": "Recolección de basura doméstica",
        "sinonimos": ("basura doméstica", "basura ordinaria", "red ambiental"),
        "contacto": CONTACTOS["limpia"],
    },
    {
        "servicio": "Retiro de escombro abandonado",
        "sinonimos": ("escombro", "retiro de escombro"),
        "contacto": CONTACTOS["limpia"],
    },
    {
        "servicio": "Deshierbe en vías públicas",
        "sinonimos": ("deshierbe", "hierba en vía pública", "maleza"),
        "contacto": CONTACTOS["limpia"],
    },
    {
        "servicio": "Barrido de calles",
        "sinonimos": ("barrido", "limpieza de calles"),
        "contacto": CONTACTOS["limpia"],
    },
    {
        "servicio": "Limpieza de banquetas y áreas municipales",
        "sinonimos": ("limpieza de banquetas", "puntos muertos", "áreas municipales"),
        "contacto": CONTACTOS["limpia"],
    },
    {
        "servicio": "Baches",
        "sinonimos": ("bache", "baches", "pavimento dañado"),
        "contacto": CONTACTOS["pavimentacion"],
    },
    {
        "servicio": "Postes ladeados o caídos",
        "sinonimos": ("poste ladeado", "poste caído", "poste por caer"),
        "contacto": CONTACTOS["infraestructura_urbana"],
    },
    {
        "servicio": "Mantenimiento correctivo de semáforos",
        "sinonimos": ("semáforo dañado", "semáforo descompuesto", "mantenimiento de semáforo"),
        "contacto": CONTACTOS["movilidad"],
    },
    {
        "servicio": "Semáforo apagado",
        "sinonimos": ("semáforo apagado", "semáforo sin funcionar"),
        "contacto": CONTACTOS["movilidad"],
    },
    {
        "servicio": "Sincronización de semáforos",
        "sinonimos": ("sincronizar semáforos", "semáforos descoordinados"),
        "contacto": CONTACTOS["movilidad"],
    },
    {
        "servicio": "Instalación de semáforo nuevo",
        "sinonimos": ("semáforo nuevo", "instalar semáforo"),
        "contacto": CONTACTOS["movilidad"],
    },
    {
        "servicio": "Poda de árbol en cables de CFE",
        "sinonimos": ("árbol en cables", "ramas en cables de luz", "poda en cables cfe"),
        "contacto": CONTACTOS["limpia"],
    },
    {
        "servicio": "Poda de árboles en parques y camellones",
        "sinonimos": ("poda en parque", "poda en camellón", "poda de árboles"),
        "contacto": CONTACTOS["limpia"],
    },
    {
        "servicio": "Tala o retiro de árbol seco o caído en área municipal",
        "sinonimos": ("árbol seco", "árbol caído", "retiro de árbol"),
        "contacto": CONTACTOS["limpia"],
    },
    {
        "servicio": "Mantenimiento menor en parques",
        "sinonimos": ("juegos dañados", "mallas de parque", "puertas de parque", "bebederos de parque"),
        "contacto": CONTACTOS["parques"],
    },
    {
        "servicio": "Drenaje pluvial",
        "sinonimos": ("drenaje pluvial", "pluvial sin tapa", "desazolve de pluviales"),
        "contacto": CONTACTOS["infraestructura_hidrica"],
    },
)


def _normalizar(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", str(texto or ""))
    sin_acentos = "".join(caracter for caracter in descompuesto if not unicodedata.combining(caracter))
    return " ".join(re.findall(r"[a-z0-9]+", sin_acentos.lower()))


def _puntaje(consulta: str, candidato: str) -> float:
    if not consulta or not candidato:
        return 0.0
    if consulta == candidato:
        return 3.0
    if candidato in consulta or consulta in candidato:
        return 2.0
    consulta_tokens = set(consulta.split())
    candidato_tokens = set(candidato.split())
    if not consulta_tokens or not candidato_tokens:
        return 0.0
    return len(consulta_tokens & candidato_tokens) / len(consulta_tokens | candidato_tokens)


async def get_catalogo_servicios_municipales(servicio: str):
    """Consultar el área y teléfono verificados para un servicio municipal.

    Usa esta función cuando el ciudadano pregunte qué área, teléfono, extensión o canal
    atiende un servicio municipal. No uses el directorio de funcionarios para inferir
    responsabilidades. Si el resultado indica que el contacto no está documentado,
    informa esa limitación o transfiere; nunca sustituyas otro teléfono municipal.

    Args:
        servicio (string): Servicio municipal que desea consultar el ciudadano.

    Returns:
        string: Área responsable y teléfono institucional del servicio.
    """
    consulta = _normalizar(servicio)
    coincidencias = []

    for entrada in SERVICIOS:
        candidatos = (entrada["servicio"], *entrada["sinonimos"])
        puntaje = max(_puntaje(consulta, _normalizar(candidato)) for candidato in candidatos)
        if puntaje >= 0.34:
            coincidencias.append((puntaje, entrada))

    coincidencias.sort(key=lambda item: (-item[0], item[1]["servicio"]))
    if not coincidencias:
        return (
            f"No existe una entrada verificada para el servicio '{servicio}'. "
            "No infieras el área ni el teléfono desde el directorio de funcionarios. "
            "Si el ciudadano necesita un contacto, transfiere por falta de contexto verificada."
        )

    mejor_puntaje = coincidencias[0][0]
    coincidencias_especificas = [
        item for item in coincidencias if item[0] >= max(0.34, mejor_puntaje - 0.25)
    ]

    bloques = []
    for _, entrada in coincidencias_especificas[:5]:
        contacto = entrada["contacto"]
        telefono = contacto["telefono"]
        if contacto["extension"]:
            telefono += f" extensión {contacto['extension']}"
        bloques.append(
            "\n".join(
                (
                    f"Acción o servicio: {entrada['servicio']}",
                    f"Área responsable: {contacto['area']}",
                    f"Teléfono: {telefono}",
                )
            )
        )

    return (
        "DIRECTORIO PRELIMINAR DE SERVICIOS MUNICIPALES\n\n"
        + "\n\n".join(bloques)
        + "\n\nResponde al ciudadano con el área y teléfono indicados. "
        "No menciones identificadores internos ni nombres personales."
    )
