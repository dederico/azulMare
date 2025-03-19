"""
Servicio para la recopilación de métricas y seguimiento de agentes.
Versión simplificada que no depende de OpenAI Agents SDK.
"""

import os
import json
import time
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime
import threading
from app.util.logger import get_logger

logger = get_logger(__name__)

class Span:
    """Clase para representar un span de tracing."""
    
    def __init__(self, name, parent=None):
        self.name = name
        self.id = str(uuid.uuid4())
        self.parent_id = parent.id if parent else None
        self.trace_id = parent.trace_id if parent else str(uuid.uuid4())
        self.start_time = datetime.now()
        self.end_time = None
        self.attributes = {}
        self.events = []
    
    def add_event(self, name, attributes=None):
        """Añade un evento al span."""
        self.events.append({
            "name": name,
            "timestamp": datetime.now(),
            "attributes": attributes or {}
        })
    
    def set_attribute(self, key, value):
        """Establece un atributo en el span."""
        self.attributes[key] = value
    
    def finish(self):
        """Finaliza el span registrando el tiempo de finalización."""
        self.end_time = datetime.now()


class Tracer:
    """Clase para gestionar el tracing de operaciones."""
    
    def __init__(self, service_name):
        self.service_name = service_name
        self.current_spans = {}  # Diccionario thread_id -> span
        
        # Directorio para guardar trazas
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
        self.traces_dir = os.path.join(root_dir, 'logs', 'traces')
        os.makedirs(self.traces_dir, exist_ok=True)
        
        logger.info(f"Tracer inicializado para servicio: {service_name}")
        logger.info(f"Directorio de trazas: {self.traces_dir}")
    
    def start_span(self, name, parent=None):
        """
        Inicia un nuevo span.
        
        Args:
            name: Nombre del span
            parent: Span padre opcional
            
        Returns:
            El span creado
        """
        thread_id = threading.get_ident()
        parent_span = parent or self.current_spans.get(thread_id)
        span = Span(name, parent_span)
        self.current_spans[thread_id] = span
        return span
    
    def end_span(self, span):
        """
        Finaliza un span y guarda sus datos.
        
        Args:
            span: El span a finalizar
        """
        span.finish()
        thread_id = threading.get_ident()
        
        # Si este span es el actual para este thread, eliminarlo
        if thread_id in self.current_spans and self.current_spans[thread_id].id == span.id:
            del self.current_spans[thread_id]
        
        # Guardar datos del span
        self._save_span_data(span)
    
    def _save_span_data(self, span):
        """
        Guarda los datos del span en un archivo JSON.
        
        Args:
            span: El span cuyos datos se guardarán
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.traces_dir}/trace_{span.name}_{timestamp}.json"
        
        try:
            with open(filename, "w") as f:
                span_data = {
                    "name": span.name,
                    "id": span.id,
                    "trace_id": span.trace_id,
                    "parent_id": span.parent_id,
                    "service": self.service_name,
                    "start_time": span.start_time.isoformat(),
                    "end_time": span.end_time.isoformat(),
                    "duration_ms": (span.end_time - span.start_time).total_seconds() * 1000,
                    "attributes": span.attributes,
                    "events": [
                        {
                            "name": event["name"],
                            "timestamp": event["timestamp"].isoformat(),
                            "attributes": event["attributes"]
                        }
                        for event in span.events
                    ]
                }
                json.dump(span_data, f, indent=2)
        except Exception as e:
            logger.error(f"Error guardando datos del span: {str(e)}")


class SpanContextManager:
    """Gestor de contexto para spans."""
    
    def __init__(self, tracer, name, parent=None):
        self.tracer = tracer
        self.name = name
        self.parent = parent
        self.span = None
    
    def __enter__(self):
        self.span = self.tracer.start_span(self.name, self.parent)
        return self.span
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            # Registrar excepción en el span
            self.span.add_event("exception", {
                "exception_type": exc_type.__name__,
                "exception_message": str(exc_val)
            })
        self.tracer.end_span(self.span)


class AgentMetricsService:
    """
    Servicio para recopilar y analizar métricas de los agentes.
    """
    
    def __init__(self):
        """Inicializa el servicio de métricas."""
        self.metrics = {
            "requests_total": 0,
            "requests_success": 0,
            "requests_error": 0,
            "tokens_used": 0,
            "average_response_time": 0,
            "total_response_time": 0,
            "agent_usage": {},
            "function_calls": {},
            "handoffs": {}
        }
        
        # Crear tracer propio
        self.tracer = Tracer(service_name="agent-metrics")
    
    def record_request(self, success: bool, elapsed_time_ms: float, 
                      tokens_used: int, agents_used: List[str], 
                      function_calls: List[str], handoffs: List[Dict[str, str]]):
        """
        Registra métricas de una solicitud procesada.
        
        Args:
            success: Si la solicitud fue exitosa
            elapsed_time_ms: Tiempo de procesamiento en milisegundos
            tokens_used: Número de tokens utilizados
            agents_used: Lista de agentes utilizados
            function_calls: Lista de funciones llamadas
            handoffs: Lista de handoffs realizados
        """
        with SpanContextManager(self.tracer, "record_metrics") as span:
            span.set_attribute("success", success)
            span.set_attribute("elapsed_time_ms", elapsed_time_ms)
            span.set_attribute("tokens_used", tokens_used)
            
            self.metrics["requests_total"] += 1
            
            if success:
                self.metrics["requests_success"] += 1
            else:
                self.metrics["requests_error"] += 1
            
            self.metrics["tokens_used"] += tokens_used
            self.metrics["total_response_time"] += elapsed_time_ms
            self.metrics["average_response_time"] = (
                self.metrics["total_response_time"] / self.metrics["requests_total"]
            )
            
            # Registrar uso de agentes
            for agent in agents_used:
                if agent in self.metrics["agent_usage"]:
                    self.metrics["agent_usage"][agent] += 1
                else:
                    self.metrics["agent_usage"][agent] = 1
            
            # Registrar llamadas a funciones
            for fn in function_calls:
                if fn in self.metrics["function_calls"]:
                    self.metrics["function_calls"][fn] += 1
                else:
                    self.metrics["function_calls"][fn] = 1
            
            # Registrar handoffs
            for handoff in handoffs:
                key = f"{handoff['source']} -> {handoff['target']}"
                if key in self.metrics["handoffs"]:
                    self.metrics["handoffs"][key] += 1
                else:
                    self.metrics["handoffs"][key] = 1
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Obtiene las métricas actuales.
        
        Returns:
            Diccionario con todas las métricas
        """
        return self.metrics
    
    def reset_metrics(self):
        """Reinicia las métricas (útil para mediciones periódicas)."""
        self.__init__()
    
    def export_metrics(self, format: str = "json") -> str:
        """
        Exporta las métricas en el formato especificado.
        
        Args:
            format: Formato de exportación ("json" o "prometheus")
            
        Returns:
            Métricas en el formato solicitado
            
        Raises:
            ValueError: Si el formato no es compatible
        """
        if format.lower() == "json":
            return json.dumps(self.metrics, indent=2)
        elif format.lower() == "prometheus":
            # Formato simple compatible con Prometheus
            lines = []
            lines.append(f"agent_requests_total {self.metrics['requests_total']}")
            lines.append(f"agent_requests_success {self.metrics['requests_success']}")
            lines.append(f"agent_requests_error {self.metrics['requests_error']}")
            lines.append(f"agent_tokens_used {self.metrics['tokens_used']}")
            lines.append(f"agent_average_response_time_ms {self.metrics['average_response_time']}")
            
            # Métricas de agentes
            for agent, count in self.metrics["agent_usage"].items():
                lines.append(f'agent_usage{{agent="{agent}"}} {count}')
            
            # Métricas de funciones
            for fn, count in self.metrics["function_calls"].items():
                lines.append(f'agent_function_calls{{function="{fn}"}} {count}')
            
            return "\n".join(lines)
        else:
            raise ValueError(f"Formato no soportado: {format}")


# Singleton del tracer global
_tracer_instance = None

def get_tracer():
    """
    Obtiene la instancia del tracer global.
    
    Returns:
        Instancia del tracer
    """
    global _tracer_instance
    if _tracer_instance is None:
        _tracer_instance = Tracer(service_name="asistente-ia")
    return _tracer_instance

def setup_tracing():
    """
    Configura el sistema de tracing global.
    
    Returns:
        Instancia del tracer configurado
    """
    tracer = get_tracer()
    logger.info("Sistema de tracing configurado correctamente")
    return tracer