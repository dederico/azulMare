import asyncio
from app.models.Call import Call
from app.util.logger import logger
from app.util.database import LocalStorage

async def get_customer_identity(call_sid):
    """Obtener la identidad a traves del call_sid

    Args:
        call_sid (string): Indicador unico de la llamada. Proporcionado en mensaje del sistema.

    Returns:
        string: Mensaje de confirmacion.
    """
    
    try:
        ls = LocalStorage()
        call = ls.Search(Call(callUid = call_sid), True)
        if call:
            return call.callerName
        
        return "Unknown"
    except Exception as e:
        logger.exception(e)
        return "Unknown"
