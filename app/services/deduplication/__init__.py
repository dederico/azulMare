# app/services/deduplication/__init__.py
"""
Servicio de Anti-Duplicación para Reportes Ciudadanos

Este módulo proporciona funcionalidades para evitar la creación de reportes duplicados
a través de múltiples vías (manual, timeout, finalization, etc.).

Uso:
    from app.services.deduplication import dedup_manager
    
    # Verificar si se puede crear un reporte
    can_create, reason, existing_folio = dedup_manager.can_create_report(
        phone_number, selection_data, images
    )
    
    if can_create:
        # Proceder con creación
        request_id = dedup_manager.mark_report_creation_start(phone_number)
        # ... crear reporte ...
        dedup_manager.mark_report_creation_success(phone_number, folio, selection_data, images)
    else:
        # Manejar duplicado
        print(f"Reporte bloqueado: {reason}")
"""

from .manager import ReportDeduplicationManager, dedup_cleanup_task

# Instancia global del gestor
dedup_manager = ReportDeduplicationManager()

# Exportar lo que necesite el resto de la aplicación
__all__ = [
    'dedup_manager',
    'ReportDeduplicationManager', 
    'dedup_cleanup_task'
]