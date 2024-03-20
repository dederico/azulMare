import asyncio
from datetime import date

async def get_current_date():
    """
    Get the current date.

    Returns:
        str: The current date in YYYY-MM-DD format.
    """
    await asyncio.sleep(1)  # Simulate an asynchronous operation
    return str(date.today())