async def get_emergencia():
    """Obtener información del protocolo para atender emergencias ciudadanas en San Pedro Garza García.

    Returns:
        string: Información sobre el protocolo de emergencias con formato institucional.
    """
    PROTOCOLO_EMERGENCIAS = """
🚨 *PROTOCOLO DE ATENCIÓN A EMERGENCIAS* 🚨
*Municipio de San Pedro Garza García*

⚠️ *IMPORTANTE*: Para emergencias que requieren atención inmediata, siempre canalizamos al C4 (Centro de Control, Comando, Comunicaciones y Cómputo) al teléfono *81 89 88 2000*.

*TIPOS DE EMERGENCIAS:*

🔴 *RIESGO INMEDIATO*
Si tu vida o la de alguien más corre riesgo:
- Te solicitaremos la ubicación exacta
- Te canalizaremos inmediatamente al C4
- *Muy pronto llegará contigo una unidad de policía. Si es posible, busca un lugar seguro para ti y/o quienes estén en riesgo o ve a casa de una vecina o vecino en lo que llega la patrulla.*

🟣 *VIOLENCIA DOMÉSTICA*
Según la situación:

- *Para mujeres que sufren violencia*:
  → Canalización a Puerta Violeta
  → *Próximamente, una persona de Puerta Violeta se pondrá en contacto contigo. Si estás en riesgo, busca un lugar seguro en casa de algún familiar o vecino(a) en lo que atendemos el reporte.*

- *Para hombres que sufren violencia*:
  → Canalización al Centro de Atención Psicológica (CAP)
  → *Próximamente, una persona del Centro de Atención Psicológica se pondrá en contacto contigo. Si estás en riesgo, busca un lugar seguro en casa de algún familiar o vecino(a) en lo que atendemos el reporte.*

- *Para hombres que ejercen violencia y desean cambiar*:
  → Canalización a CESADE
  → *Próximamente, una persona del Centro de Salud y Desarrollo (CESADE) se pondrá en contacto contigo.*

- *Para menores de edad que sufren violencia*:
  → Canalización a SIPINNA
  → *Próximamente, una autoridad del Sistema Municipal de Protección de Niñas, Niños y Adolescentes atenderá el reporte.*

- *Para adolescentes con problemas de conducta*:
  → Canalización a CAIPA
  → *Próximamente, una persona del Centro de Atención Integral para Adolescentes atenderá el reporte.*

🆘 *IDEACIÓN SUICIDA*
Si alguien amenaza con hacerse daño:
- Canalización inmediata al C4
- *Muy pronto una unidad de policía atenderá el reporte.*

📞 *TELÉFONOS DE AYUDA*:
- C4 (emergencias): *81 89 88 2000*
- Puerta Violeta: *81 4040 4737*
- Centro de Atención Psicológica (CAP): *81 8400 4598*
- SIPINNA: *81 8124 6100*
- CAIPA: *81 2723 3001*

🔹 *MUNICIPIO DE SAN PEDRO GARZA GARCÍA* 🔹
*Trabajando por tu seguridad*
"""
    return PROTOCOLO_EMERGENCIAS