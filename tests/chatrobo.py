import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
from datetime import datetime
from app.models.Config import Config
from app.util.database import LocalStorage
from app.services.llm.config.system import system_message
from app.services.llm.openai_service import OpenAIService
from app.services.functions.function_manager import FunctionManager
from app.services.functions.function_registry import registered_functions

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
now = datetime.now()

ls = LocalStorage()
config = { conf.name: conf.getval() for conf in ls.GetAll(Config) }

function_manager = FunctionManager(registered_functions)
llm_service = OpenAIService(
    config=config,
    api_key=OPENAI_API_KEY,
    system=system_message.format(customer_name="Fede", call_sid="54363", date2=now.strftime("%d-%m-%Y"), now=now, date=now.date),
    function_manager=function_manager
)

async def Run():
    while True:
        query = input("Enter Query (or nothing to exit): ") or "exit"
        if query == "exit":
            break

        response = llm_service.generate_response(query)
        response = "".join([token async for token in response])

        print(response)

if __name__ == "__main__":
    asyncio.run(Run())