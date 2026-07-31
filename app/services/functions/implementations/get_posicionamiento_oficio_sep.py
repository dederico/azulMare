from .get_comunicado_oficio_sep_2026 import get_comunicado_oficio_sep_2026


async def get_posicionamiento_oficio_sep():
    """Compat wrapper for the official SEP oficio positioning function.

    Returns:
        string: El posicionamiento oficial del Colegio Militarizado sobre el oficio UR-100/OCSEP/0180/2026.
    """
    return await get_comunicado_oficio_sep_2026()
