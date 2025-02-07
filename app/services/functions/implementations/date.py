from datetime import datetime
from zoneinfo import ZoneInfo
import asyncio

async def get_current_date():
    """
    Get the current date in Mexico timezone.

    Returns:
        str: The current date in YYYY-MM-DD format (Mexico Timezone).
    """
    await asyncio.sleep(1)  # Simula una operación asíncrona
    now_mexico = datetime.now(ZoneInfo("America/Mexico_City"))
    return now_mexico.strftime("%Y-%m-%d")