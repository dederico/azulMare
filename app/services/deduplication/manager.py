# app/services/deduplication/manager.py
"""
Sistema Anti-Duplicación para Reportes Ciudadanos
Evita la creación de reportes duplicados por múltiples vías.
"""

import threading
import time
import hashlib
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional, List, Any

logger = logging.getLogger(__name__)

class ReportDeduplicationManager:
    """
    Gestor centralizado para evitar reportes duplicados.
    Maneja TODAS las vías de creación de reportes.
    """
    
    def __init__(self):
        self.lock = threading.RLock()
        
        # Almacén centralizado de reportes recientes (30 min)
        self.recent_reports = {}  # {phone: {folio, timestamp, hash}}
        
        # Reportes en proceso de creación (evita condiciones de carrera)
        self.creating_reports = {}  # {phone: {timestamp, request_id}}
        
        # Cache de hashes de contenido para detectar duplicados exactos
        self.content_hashes = {}  # {hash: {phone, folio, timestamp}}
        
        # Protección post-reporte (bloquea nuevos reportes por 10 min)
        self.post_report_protection = {}  # {phone: expiry_timestamp}
        
        logger.info("🛡️ [DEDUP] Sistema Anti-Duplicación inicializado")
    
    def generate_content_hash(self, phone: str, selection_data: Dict[str, str], images: Optional[List[str]] = None) -> str:
        """Genera hash único basado en el contenido del reporte"""
        
        # Crear string con datos clave del reporte
        content_parts = [
            phone,
            selection_data.get('selection1', ''),  # Tipo de reporte
            selection_data.get('selection4', ''),  # Descripción
            selection_data.get('selection5', ''),  # Calle
            selection_data.get('selection7', '')   # Colonia
        ]
        
        # Incluir URLs de imágenes si existen
        if images:
            sorted_images = sorted([img for img in images if img and isinstance(img, str)])
            content_parts.extend(sorted_images)
        
        content = "|".join(content_parts)
        return hashlib.md5(content.encode()).hexdigest()
    
    def can_create_report(self, phone_number: str, selection_data: Dict[str, str], images: Optional[List[str]] = None) -> Tuple[bool, str, Optional[str]]:
        """
        Verifica si se puede crear un reporte nuevo.
        
        Args:
            phone_number: Número de teléfono del usuario
            selection_data: Datos del reporte (selection1, selection2, etc.)
            images: Lista de URLs de imágenes
            
        Returns:
            Tuple[can_create, reason, existing_folio]
        """
        with self.lock:
            current_time = time.time()
            
            # 1. VERIFICAR PROTECCIÓN POST-REPORTE
            if phone_number in self.post_report_protection:
                if current_time < self.post_report_protection[phone_number]:
                    remaining = int(self.post_report_protection[phone_number] - current_time)
                    recent_report = self.recent_reports.get(phone_number)
                    existing_folio = recent_report.get('folio') if recent_report else None
                    return (
                        False,
                        f"Protección post-reporte activa ({remaining}s restantes)",
                        existing_folio,
                    )
                else:
                    # Protección expirada, limpiar
                    del self.post_report_protection[phone_number]
                    logger.debug(f"🧹 [DEDUP] Protección post-reporte expirada para {phone_number}")
            
            # 2. VERIFICAR SI YA ESTÁ CREANDO UN REPORTE
            if phone_number in self.creating_reports:
                creation_time = self.creating_reports[phone_number]['timestamp']
                if current_time - creation_time < 300:  # 5 minutos
                    return False, "Reporte en proceso de creación", None
                else:
                    # Proceso colgado, limpiar
                    del self.creating_reports[phone_number]
                    logger.warning(f"🧹 [DEDUP] Proceso de creación colgado limpiado para {phone_number}")
            
            # 3. VERIFICAR REPORTES RECIENTES POR TELÉFONO
            if phone_number in self.recent_reports:
                report_info = self.recent_reports[phone_number]
                elapsed = current_time - report_info['timestamp']
                
                if elapsed < 1800:  # 30 minutos
                    return False, f"Reporte reciente encontrado ({int(elapsed/60)} min ago)", report_info['folio']
                else:
                    # Reporte antiguo, limpiar
                    del self.recent_reports[phone_number]
                    logger.debug(f"🧹 [DEDUP] Reporte reciente expirado para {phone_number}")
            
            # 4. VERIFICAR DUPLICADOS POR CONTENIDO
            content_hash = self.generate_content_hash(phone_number, selection_data, images)
            
            if content_hash in self.content_hashes:
                hash_info = self.content_hashes[content_hash]
                elapsed = current_time - hash_info['timestamp']
                
                if elapsed < 3600:  # 1 hora para duplicados de contenido
                    return False, f"Contenido duplicado detectado", hash_info['folio']
                else:
                    # Hash antiguo, limpiar
                    del self.content_hashes[content_hash]
                    logger.debug(f"🧹 [DEDUP] Hash de contenido expirado: {content_hash[:8]}...")
            
            return True, "OK", None
    
    def mark_report_creation_start(self, phone_number: str) -> str:
        """Marca el inicio de creación de reporte"""
        with self.lock:
            request_id = f"{phone_number}-{int(time.time())}"
            self.creating_reports[phone_number] = {
                'timestamp': time.time(),
                'request_id': request_id
            }
            logger.debug(f"🚀 [DEDUP] Iniciando creación de reporte: {request_id}")
            return request_id
    
    def mark_report_creation_success(self, phone_number: str, folio: str, selection_data: Dict[str, str], images: Optional[List[str]] = None):
        """Marca un reporte como creado exitosamente"""
        with self.lock:
            current_time = time.time()
            
            # Limpiar "Folio: " del folio si existe
            clean_folio = folio.replace("Folio: ", "") if folio.startswith("Folio: ") else folio
            
            # Registrar reporte reciente
            self.recent_reports[phone_number] = {
                'folio': clean_folio,
                'timestamp': current_time
            }
            
            # Registrar hash de contenido
            content_hash = self.generate_content_hash(phone_number, selection_data, images)
            self.content_hashes[content_hash] = {
                'phone': phone_number,
                'folio': clean_folio,
                'timestamp': current_time
            }
            
            # Activar protección post-reporte (10 minutos)
            self.post_report_protection[phone_number] = current_time + 600
            
            # Limpiar estado de "creando"
            if phone_number in self.creating_reports:
                del self.creating_reports[phone_number]
            
            logger.critical(f"✅ [DEDUP] Reporte {clean_folio} registrado para {phone_number}")
    
    def mark_report_creation_failure(self, phone_number: str):
        """Marca un intento de reporte como fallido"""
        with self.lock:
            if phone_number in self.creating_reports:
                request_id = self.creating_reports[phone_number]['request_id']
                del self.creating_reports[phone_number]
                logger.warning(f"❌ [DEDUP] Creación fallida: {request_id}")
    
    def force_clear_protection(self, phone_number: str) -> List[str]:
        """
        Limpia toda la protección para un número (usar con cuidado)
        
        Returns:
            Lista de items eliminados
        """
        with self.lock:
            items_cleared = []
            
            if phone_number in self.recent_reports:
                del self.recent_reports[phone_number]
                items_cleared.append("recent_reports")
            
            if phone_number in self.creating_reports:
                del self.creating_reports[phone_number]
                items_cleared.append("creating_reports")
            
            if phone_number in self.post_report_protection:
                del self.post_report_protection[phone_number]
                items_cleared.append("post_report_protection")
            
            # Limpiar hashes relacionados con este teléfono
            hashes_to_remove = []
            for hash_val, info in self.content_hashes.items():
                if info.get('phone') == phone_number:
                    hashes_to_remove.append(hash_val)
            
            for hash_val in hashes_to_remove:
                del self.content_hashes[hash_val]
                
            if hashes_to_remove:
                items_cleared.append(f"content_hashes({len(hashes_to_remove)})")
            
            logger.warning(f"🧹 [FORCE CLEAR] Protecciones eliminadas para {phone_number}: {items_cleared}")
            return items_cleared
    
    def cleanup_expired_entries(self) -> Dict[str, int]:
        """
        Limpia entradas expiradas (llamar periódicamente)
        
        Returns:
            Diccionario con conteos de items eliminados
        """
        with self.lock:
            current_time = time.time()
            
            # Limpiar reportes recientes expirados (30 min)
            expired_recent = [phone for phone, info in self.recent_reports.items() 
                            if current_time - info['timestamp'] > 1800]
            for phone in expired_recent:
                del self.recent_reports[phone]
            
            # Limpiar hashes de contenido expirados (1 hora)
            expired_hashes = [hash_val for hash_val, info in self.content_hashes.items() 
                            if current_time - info['timestamp'] > 3600]
            for hash_val in expired_hashes:
                del self.content_hashes[hash_val]
            
            # Limpiar protecciones post-reporte expiradas
            expired_protection = [phone for phone, expiry in self.post_report_protection.items() 
                                if current_time > expiry]
            for phone in expired_protection:
                del self.post_report_protection[phone]
            
            # Limpiar procesos de creación colgados (5 min)
            expired_creating = [phone for phone, info in self.creating_reports.items() 
                              if current_time - info['timestamp'] > 300]
            for phone in expired_creating:
                del self.creating_reports[phone]
            
            cleanup_stats = {
                'recent_reports': len(expired_recent),
                'content_hashes': len(expired_hashes),
                'post_protection': len(expired_protection),
                'creating_reports': len(expired_creating)
            }
            
            total_cleaned = sum(cleanup_stats.values())
            if total_cleaned > 0:
                logger.info(f"🧹 [CLEANUP] Eliminados: {cleanup_stats}")
            
            return cleanup_stats
    
    def get_status(self, phone_number: Optional[str] = None) -> Dict[str, Any]:
        """Obtiene estado actual del sistema"""
        with self.lock:
            if phone_number:
                # Estado específico de un teléfono
                current_time = time.time()
                
                # Buscar hashes relacionados
                related_hashes = []
                for hash_val, info in self.content_hashes.items():
                    if info.get('phone') == phone_number:
                        related_hashes.append({
                            'hash': hash_val[:8] + '...',
                            'folio': info.get('folio'),
                            'age_minutes': (current_time - info['timestamp']) / 60
                        })
                
                protection_info = None
                if phone_number in self.post_report_protection:
                    expiry = self.post_report_protection[phone_number]
                    protection_info = {
                        'expires_in_seconds': max(0, expiry - current_time),
                        'expires_at': datetime.fromtimestamp(expiry).isoformat()
                    }
                
                return {
                    'phone': phone_number,
                    'recent_report': self.recent_reports.get(phone_number),
                    'creating': self.creating_reports.get(phone_number),
                    'protection': protection_info,
                    'related_hashes': related_hashes,
                    'current_time': current_time,
                    'current_time_iso': datetime.fromtimestamp(current_time).isoformat()
                }
            else:
                # Estado general del sistema
                return {
                    'total_recent_reports': len(self.recent_reports),
                    'total_creating': len(self.creating_reports),
                    'total_protected': len(self.post_report_protection),
                    'total_content_hashes': len(self.content_hashes),
                    'uptime_info': {
                        'current_time': time.time(),
                        'current_time_iso': datetime.now().isoformat()
                    }
                }

# ===============================================
# FUNCIÓN ASYNC PARA LIMPIEZA AUTOMÁTICA
# ===============================================

async def dedup_cleanup_task(manager: ReportDeduplicationManager):
    """Tarea que limpia entradas expiradas cada 5 minutos"""
    while True:
        try:
            await asyncio.sleep(300)  # 5 minutos
            stats = manager.cleanup_expired_entries()
            
            # Log solo si se limpiaron items
            total_cleaned = sum(stats.values())
            if total_cleaned > 0:
                logger.info(f"🧹 [AUTO-CLEANUP] Limpieza automática completada: {stats}")
                
        except Exception as e:
            logger.error(f"💥 [CLEANUP ERROR] Error en tarea de limpieza automática: {str(e)}")
            # Continuar ejecutándose incluso si hay errores
