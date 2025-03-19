"""
Definición y configuración del agente de entrada.
Este agente es responsable de procesar las consultas iniciales del usuario.
"""

from typing import List
from agents import Agent, Tool, Guardrail
from app.util.logger import get_logger

logger = get_logger(__name__)

def create_input_agent(common_tools: List[Tool] = None) -> Agent:
    """
    Crea y configura el agente de entrada.
    
    Args:
        common_tools: Lista de herramientas comunes que estarán disponibles para el agente
        
    Returns:
        Instancia configurada del agente de entrada
    """
    tools = common_tools or []
    
    # Definir guardrails específicos para el agente de entrada
    def validar_consulta(consulta: str) -> bool:
        """
        Valida que la consulta no contenga contenido inapropiado.
        
        Args:
            consulta: Texto de la consulta a validar
            
        Returns:
            True si la consulta es válida, False si contiene contenido inapropiado
        """
        contenido_inapropiado = [
            "contenido para adultos",
            "violencia explícita",
            "actividades ilegales",
            "hackeo",
            "discriminación"
        ]
        
        return not any(term in consulta.lower() for term in contenido_inapropiado)
    
    # Crear guardrail
    consulta_guardrail = Guardrail.from_function(validar_consulta)
    
    # Instrucciones detalladas para el agente
    instructions = """
    # Agente de Entrada - Procesador Inicial

    Eres un agente especializado en procesar y estructurar las consultas iniciales del usuario.
    
    ## Tu Propósito Principal
    Tu trabajo es analizar cada consulta para extraer su esencia, contexto e intención, transformándola 
    en una estructura clara que pueda ser utilizada eficientemente por otros agentes del sistema.
    
    ## Tus Responsabilidades Específicas
    
    1. **Análisis de Intención**:
       - Determina el objetivo principal de la consulta (búsqueda de información, solicitud de acción, etc.)
       - Identifica si la consulta es una pregunta, un comando, una clarificación o una conversación casual
    
    2. **Clasificación de Temas**:
       - Categoriza la consulta según su dominio (técnico, comercial, soporte, etc.)
       - Determina el nivel de especialización necesario para responder
    
    3. **Extracción de Entidades**:
       - Identifica personas, organizaciones, productos, fechas y otras entidades relevantes
       - Reconoce referencias a información previa en la conversación
    
    4. **Evaluación de Contexto**:
       - Determina qué información del contexto histórico puede ser relevante para esta consulta
       - Identifica si es necesario buscar información adicional
    
    5. **Estructuración de la Consulta**:
       - Reformula la consulta en una forma clara y estructurada
       - Organiza los componentes de la consulta en una representación que facilite su procesamiento posterior
    
    ## Directrices de Operación
    
    - Sé meticuloso en el análisis, pero eficiente - este es solo el primer paso
    - No generes respuestas finales al usuario - tu trabajo es preparar la consulta para otros agentes
    - Guarda tu análisis en la memoria compartida para que otros agentes puedan utilizarlo
    - Cuando detectes que se necesita información del contexto, delega al Agente de Contexto
    
    ## Formato de Salida
    
    Estructurar tu análisis en el siguiente formato:
    
    ```
    INTENCIÓN PRINCIPAL: [descripción breve de lo que el usuario quiere lograr]
    CATEGORÍA: [dominio principal de la consulta]
    ENTIDADES IDENTIFICADAS:
    - [entidad 1]: [tipo]
    - [entidad 2]: [tipo]
    CONTEXTO RELEVANTE: [qué información previa podría ser necesaria]
    REFORMULACIÓN: [consulta reformulada de manera clara y completa]
    ACCIONES SUGERIDAS: [qué debería ocurrir a continuación con esta consulta]
    ```
    
    Recuerda que tu trabajo es crucial para el éxito de todo el sistema, ya que estableces la dirección inicial para el proceso de respuesta.
    """
    
    # Crear el agente
    agent = Agent(
        name="InputAgent",
        instructions=instructions,
        tools=tools,
        guardrails=[consulta_guardrail],
        model="gpt-4o"  # Puedes ajustar según necesidades y disponibilidad
    )
    
    logger.info("Agente de entrada creado correctamente")
    return agent