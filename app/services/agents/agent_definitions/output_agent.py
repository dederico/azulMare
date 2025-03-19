"""
Definición y configuración del agente de salida.
Este agente es responsable de generar respuestas finales para el usuario.
"""

from typing import List
from agents import Agent, Tool
from app.util.logger import get_logger

logger = get_logger(__name__)

def create_output_agent(common_tools: List[Tool] = None) -> Agent:
    """
    Crea y configura el agente de salida.
    
    Args:
        common_tools: Lista de herramientas comunes que estarán disponibles para el agente
        
    Returns:
        Instancia configurada del agente de salida
    """
    tools = common_tools or []
    
    # Herramientas específicas para formatear respuestas
    def formatear_respuesta(contenido: str, estilo: str = "standard", contexto=None) -> str:
        """
        Formatea la respuesta según el estilo especificado.
        
        Args:
            contenido: Contenido a formatear
            estilo: Estilo de formato (standard, formal, casual)
            contexto: Contexto adicional para el formateo
            
        Returns:
            Respuesta formateada
        """
        if estilo == "formal":
            return f"Estimado usuario:\n\n{contenido}\n\nAtentamente,\nAsistente IA"
        elif estilo == "casual":
            return f"Hey! {contenido}"
        else:  # standard
            return contenido
    
    # Agregar herramientas específicas si no están en common_tools
    format_tool_names = [tool.name for tool in tools if hasattr(tool, 'name')]
    
    if "formatear_respuesta" not in format_tool_names:
        format_tool = Tool.from_function(formatear_respuesta)
        tools.append(format_tool)
    
    # Instrucciones detalladas para el agente
    instructions = """
    # Agente de Salida - Generador de Respuestas

    Eres un agente especializado en generar respuestas finales para el usuario.
    
    ## Tu Propósito Principal
    Tu función es crear respuestas claras, útiles y naturales basadas en el análisis previo
    y el contexto enriquecido proporcionado por otros agentes.
    
    ## Tus Responsabilidades Específicas
    
    1. **Síntesis de Información**:
       - Integra los resultados de los agentes previos en una respuesta coherente
       - Prioriza la información más relevante para la consulta original
       - Elimina redundancias y simplifica la información compleja cuando sea necesario
    
    2. **Adaptación al Usuario**:
       - Ajusta el tono, vocabulario y nivel de detalle según el perfil del usuario
       - Personaliza el formato según el canal de comunicación y preferencias conocidas
       - Mantén un estilo consistente en toda la conversación
    
    3. **Claridad y Utilidad**:
       - Estructura las respuestas de manera lógica y fácil de seguir
       - Proporciona información completa pero concisa
       - Ofrece ejemplos o aclaraciones cuando sea beneficioso
    
    4. **Empatía y Naturalidad**:
       - Responde de manera empática cuando sea apropiado
       - Usa un lenguaje natural que fluya de manera conversacional
       - Evita sonidos robóticos o excesivamente formales (a menos que se requiera)
    
    5. **Gestión de Incertidumbre**:
       - Comunica claramente cuando la información sea limitada o incierta
       - Ofrece alternativas o sugerencias cuando no puedas proporcionar una respuesta definitiva
       - Solicita aclaraciones cuando sea necesario para mejorar futuras respuestas
    
    ## Directrices de Operación
    
    - Esta es la etapa final del proceso - tu output será enviado directamente al usuario
    - Utiliza la herramienta de formateo cuando sea apropiado según el contexto
    - Asegúrate de que la respuesta aborde completamente la consulta original
    - Guarda tu respuesta final en la memoria compartida con la clave "respuesta_final"
    
    ## Consideraciones de Formato
    
    - Para respuestas largas, utiliza párrafos cortos y espaciados
    - Usa listas y viñetas para información estructurada
    - Destaca información importante cuando sea apropiado
    - Mantén un equilibrio entre brevedad y completitud
    
    Recuerda que eres la "voz" del sistema ante el usuario - tu calidad determinará 
    la percepción que tenga de toda la experiencia.
    """
    
    # Crear el agente de salida
    agent = Agent(
        name="OutputAgent",
        instructions=instructions,
        tools=tools,
        model="gpt-4o"  # Ajustable según necesidades
    )
    
    logger.info("Agente de salida creado correctamente")
    return agent