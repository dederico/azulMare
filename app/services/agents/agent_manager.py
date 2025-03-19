"""
Gestor principal de agentes que coordina la creación y comunicación entre agentes.
"""

import os
from typing import Dict, List, Any, Optional
import time
from datetime import datetime

# Importaciones de OpenAI Agents SDK
from agents import Agent, Runner, Tool, Handoff, RunContext, Guardrail

# Importaciones de la aplicación
from app.models.Message import Message
from app.models.Call import Call
from app.services.llm.llm_service import LLMService
from app.util.logger import get_logger
from app.util.vectorizer import VectorStore  # Ajustado para usar tu sistema de vectores

# Importaciones de agentes específicos
from app.services.agents.agent_definitions.input_agent import create_input_agent
from app.services.agents.agent_definitions.context_agent import create_context_agent
from app.services.agents.agent_definitions.output_agent import create_output_agent
from app.services.agents.tracing_service import setup_tracing, AgentMetricsService

logger = get_logger(__name__)

class AgentManager:
    """
    Clase para gestionar los agentes utilizando OpenAI Agents SDK,
    integrándose con la arquitectura existente.
    """
    
    def __init__(self, api_key: str = None):
        """
        Inicializa el gestor de agentes.
        
        Args:
            api_key: API key de OpenAI. Si no se proporciona, intentará usar
                    la variable de entorno OPENAI_API_KEY.
        """
        # Configurar API key
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key
        elif not os.environ.get("OPENAI_API_KEY"):
            logger.warning("No se ha configurado OPENAI_API_KEY. Los agentes pueden fallar.")
        
        # Configurar tracing
        self.tracer = setup_tracing()
        
        # Servicios existentes que pueden ser necesarios
        self.llm_service = LLMService()
        
        # Sistema de almacenamiento vectorial (adaptado a tu estructura)
        self.vector_store = VectorStore()
        
        # Métricas
        self.metrics_service = AgentMetricsService()
        
        # Inicializar agentes
        self._initialize_agents()
        
        logger.info("AgentManager inicializado correctamente")
    
    def _initialize_agents(self):
        """Inicializa los agentes con sus respectivos contextos y herramientas."""
        # Definir herramientas comunes para los agentes
        
        # Herramienta para buscar en vectores
        def buscar_vectores(query: str, collection: str, contexto: RunContext) -> Dict[str, Any]:
            """
            Busca información en el almacenamiento vectorial.
            
            Args:
                query: Consulta para buscar
                collection: Colección donde buscar
                contexto: Contexto de ejecución compartido entre agentes
                
            Returns:
                Resultados de la búsqueda
            """
            logger.debug(f"Buscando en vectores: {query}")
            result = self.vector_store.search(query, collection)
            contexto.memory["ultimo_resultado_vectores"] = result
            return result
        
        # Herramienta para procesar funciones
        def ejecutar_funcion(fn_name: str, params: Dict[str, Any], contexto: RunContext) -> Any:
            """
            Ejecuta una función del sistema existente.
            
            Args:
                fn_name: Nombre de la función a ejecutar
                params: Parámetros para la función
                contexto: Contexto de ejecución compartido entre agentes
                
            Returns:
                Resultado de la función
            """
            logger.debug(f"Ejecutando función: {fn_name}")
            from app.services.functions.function_manager import FunctionManager
            fn_manager = FunctionManager()
            result = fn_manager.execute_function(fn_name, params)
            contexto.memory[f"resultado_{fn_name}"] = result
            return result
        
        # Herramienta para guardar en contexto
        def guardar_en_contexto(key: str, value: Any, contexto: RunContext) -> bool:
            """
            Guarda información en el contexto compartido.
            
            Args:
                key: Clave para almacenar
                value: Valor a almacenar
                contexto: Contexto de ejecución compartido entre agentes
                
            Returns:
                True si se guardó correctamente
            """
            contexto.memory[key] = value
            return True
        
        # Convertir funciones en herramientas
        buscar_vectores_tool = Tool.from_function(buscar_vectores)
        ejecutar_funcion_tool = Tool.from_function(ejecutar_funcion)
        guardar_en_contexto_tool = Tool.from_function(guardar_en_contexto)
        
        # Definir herramientas comunes
        common_tools = [buscar_vectores_tool, ejecutar_funcion_tool, guardar_en_contexto_tool]
        
        # Crear agentes utilizando las definiciones modulares
        self.input_agent = create_input_agent(common_tools)
        self.context_agent = create_context_agent(common_tools)
        self.output_agent = create_output_agent(common_tools)
        
        # Configurar handoffs entre agentes
        self.input_agent.handoffs = [
            Handoff(target=self.context_agent, description="Enriquecer con contexto"),
        ]
        
        self.context_agent.handoffs = [
            Handoff(target=self.output_agent, description="Generar respuesta final")
        ]
        
        logger.info("Agentes inicializados correctamente")
    
    def process_message(self, message: Message, call_id: Optional[str] = None) -> Message:
        """
        Procesa un mensaje utilizando el sistema de agentes.
        Se integra con tu sistema existente de mensajes.
        
        Args:
            message: Mensaje a procesar
            call_id: ID de la llamada (opcional)
            
        Returns:
            Mensaje de respuesta
        """
        start_time = time.time()
        success = False
        agents_used = []
        function_calls = []
        handoffs_used = []
        total_tokens = 0
        
        with self.tracer.start_as_current_span("procesar_mensaje") as span:
            span.set_attribute("message_id", message.id)
            if call_id:
                span.set_attribute("call_id", call_id)
            
            try:
                # Crear contexto de ejecución
                run_context = RunContext()
                run_context.memory["mensaje_original"] = message.content
                run_context.memory["user_id"] = message.user_id
                
                if call_id:
                    # Obtener información de la llamada si existe
                    call = Call.get_by_id(call_id)
                    run_context.memory["call_info"] = {
                        "id": call.id,
                        "status": call.status,
                        "duration": call.duration
                    }
                
                # Ejecutar agente de entrada
                logger.info(f"Procesando mensaje con agente de entrada: {message.id}")
                agents_used.append("input_agent")
                entrada_result = Runner.run_sync(
                    self.input_agent,
                    message.content,
                    context=run_context
                )
                total_tokens += entrada_result.usage.total_tokens
                
                # Si hay llamadas a funciones en el resultado, registrarlas
                if hasattr(entrada_result, 'function_calls') and entrada_result.function_calls:
                    for fn_call in entrada_result.function_calls:
                        function_calls.append(fn_call.name)
                
                # Si hay handoffs en el resultado, registrarlos y usarlos
                if hasattr(entrada_result, 'handoffs') and entrada_result.handoffs:
                    for handoff in entrada_result.handoffs:
                        handoffs_used.append({
                            "source": "input_agent",
                            "target": handoff.target.name
                        })
                    # El agente ya decidió hacer handoff, no necesitamos dirigir manualmente
                else:
                    # Dirigir manualmente el flujo
                    # Paso 2: Contexto
                    agents_used.append("context_agent")
                    contexto_result = Runner.run_sync(
                        self.context_agent,
                        f"Enriquece esta consulta con contexto relevante: {entrada_result.final_output}",
                        context=run_context
                    )
                    total_tokens += contexto_result.usage.total_tokens
                    
                    # Registrar cualquier función o handoff
                    if hasattr(contexto_result, 'function_calls') and contexto_result.function_calls:
                        for fn_call in contexto_result.function_calls:
                            function_calls.append(fn_call.name)
                    
                    if hasattr(contexto_result, 'handoffs') and contexto_result.handoffs:
                        for handoff in contexto_result.handoffs:
                            handoffs_used.append({
                                "source": "context_agent",
                                "target": handoff.target.name
                            })
                    else:
                        # Paso 3: Respuesta
                        agents_used.append("output_agent")
                        respuesta_result = Runner.run_sync(
                            self.output_agent,
                            f"""
                            Genera una respuesta final para el usuario:
                            - Consulta original: {message.content}
                            - Análisis inicial: {entrada_result.final_output}
                            - Contexto enriquecido: {contexto_result.final_output}
                            """,
                            context=run_context
                        )
                        total_tokens += respuesta_result.usage.total_tokens
                
                # Obtener el resultado final después de todos los handoffs
                final_content = None
                if "respuesta_final" in run_context.memory:
                    final_content = run_context.memory["respuesta_final"]
                else:
                    # Tomar el último resultado disponible
                    if 'respuesta_result' in locals():
                        final_content = respuesta_result.final_output
                    elif 'contexto_result' in locals():
                        final_content = contexto_result.final_output
                    else:
                        final_content = entrada_result.final_output
                
                # Crear mensaje de respuesta
                response_message = Message(
                    content=final_content,
                    user_id=None,  # Mensaje del sistema
                    call_id=call_id,
                    metadata={
                        "tokens_utilizados": total_tokens,
                        "tiempo_procesamiento": (time.time() - start_time),
                        "agentes_utilizados": agents_used,
                        "funciones_ejecutadas": function_calls,
                        "handoffs": handoffs_used
                    }
                )
                
                success = True
                logger.info(f"Mensaje procesado correctamente: {response_message.id}")
                return response_message
                
            except Exception as e:
                logger.error(f"Error procesando mensaje con agentes: {str(e)}")
                # Crear mensaje de error
                error_message = Message(
                    content="Lo siento, ocurrió un error al procesar tu mensaje. Por favor, intenta nuevamente.",
                    user_id=None,
                    call_id=call_id,
                    metadata={"error": str(e)}
                )
                return error_message
            
            finally:
                # Registrar métricas
                elapsed_time_ms = (time.time() - start_time) * 1000
                self.metrics_service.record_request(
                    success=success,
                    elapsed_time_ms=elapsed_time_ms,
                    tokens_used=total_tokens,
                    agents_used=agents_used,
                    function_calls=function_calls,
                    handoffs=handoffs_used
                )