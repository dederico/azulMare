"""
Definiciones de agentes específicos para el sistema.
"""

from app.services.agents.agent_definitions.input_agent import create_input_agent
from app.services.agents.agent_definitions.context_agent import create_context_agent
from app.services.agents.agent_definitions.output_agent import create_output_agent

__all__ = ['create_input_agent', 'create_context_agent', 'create_output_agent']