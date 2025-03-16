from app.services.llm.llm_service import LLMService
from app.services.llm.openai_service import OpenAIService
from app.services.llm.reasoning_service import ReasoningService
from app.services.functions.function_manager import FunctionManager
from typing import Dict, Any


class LLMFactory:
    @staticmethod
    def create_llm_service(
        service_type: str,
        config: Dict[str, Any],
        api_key: str,
        function_manager: FunctionManager,
        system: str = ""
    ) -> LLMService:
        """
        Factory method to create appropriate LLM service based on configuration
        
        Args:
            service_type: Type of LLM service ('openai', 'reasoning')
            config: Configuration dictionary
            api_key: API key for the service
            function_manager: FunctionManager instance
            system_prompt: Optional system prompt
            
        Returns:
            An instance of LLMService
        """
        if service_type.lower() == "openai":
            return OpenAIService(
                config=config,
                api_key=api_key,
                function_manager=function_manager,
                system=system
            )
        elif service_type.lower() == "reasoning":
            return ReasoningService(
                config=config,
                api_key=api_key,
                function_manager=function_manager,
                system=system
            )
        else:
            raise ValueError(f"Unknown LLM service type: {service_type}")