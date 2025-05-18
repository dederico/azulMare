# app/services/llm/deepseek_service.py
import requests
import json
import os
import asyncio
from app.services.llm.llm_service import LLMService
from app.util.logger import logger

class DeepSeekService(LLMService):
    def __init__(self, config, api_key, system, function_manager=None):
        super().__init__()
        self.config = config
        self.api_key = api_key
        self.system = system
        self.function_manager = function_manager
        self.api_base = "https://api.deepseek.com/v1"  # Adjust if their API URL is different
        self.model = config.get("deepseek_model", "deepseek-chat")  # Default model

    async def generate_response(self, user_input):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system},
                {"role": "user", "content": user_input}
            ],
            "temperature": 0.7,
            "max_tokens": 1000
        }
        
        # Add functions if available
        if self.function_manager:
            functions = self.function_manager.get_functions_schema()
            if functions:
                payload["functions"] = functions
        
        try:
            response = requests.post(
                f"{self.api_base}/chat/completions", 
                headers=headers,
                json=payload
            )
            
            if response.status_code != 200:
                logger.error(f"DeepSeek API error: {response.status_code}, {response.text}")
                yield f"Error: Unable to get response from DeepSeek API (Status {response.status_code})"
                return
                
            response_data = response.json()
            
            # Handle function calls if present
            if "function_call" in response_data.get("choices", [{}])[0].get("message", {}):
                function_call = response_data["choices"][0]["message"]["function_call"]
                if self.function_manager:
                    result = await self.function_manager.execute_function(
                        function_call["name"],
                        json.loads(function_call["arguments"])
                    )
                    yield f"\nFunction result: {result}\n"
            
            # Return the content
            yield response_data["choices"][0]["message"]["content"]
            
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            yield f"Error generating response: {str(e)}"