async def get_emergencia():
    """Obtener información del protocolo para atender emergencias ciudadanas en San Pedro Garza García.

    Returns:
        string: Información sobre el protocolo de emergencias con formato institucional.
    """
    PROTOCOLO_EMERGENCIAS = """
🚨 *PROTOCOLO DE ATENCIÓN A EMERGENCIAS* 🚨
*Municipio de San Pedro Garza García*

*TIPOS DE EMERGENCIAS:*

🔴 *RIESGO INMEDIATO*
Si tu vida o la de alguien más corre riesgo:
  → Comunicate de inmediato al C4
  → Télefono: *81 89 88 2000*

🟣 *VIOLENCIA DOMÉSTICA*

- *Sí eres mujer, y sufriste violencia*:
  → Comunícate al Centro Integral de Atención a la Mujer (CIAM)
  → Télefono: *81 8242 5022*

- *Sí eres hombre, y sufriste violencia*:
  → Comunicate al Centro de Atención Psicológica (CAP)
  → Télefono: *81 8242 5018*

- *Grupo de Reflexion para hombres*:
  → Comunicate a CESADE (Centro de Salud y Desarrollo - UDEM)
  → Télefono: *818 215 4917*
  → Whatsapp: *813 609 1757*

- *Para menores de edad que sufren violencia*:
  → Comunicate al Sistema Integral de Protección A Niñas, Niños, y Adolescentes (SIPINNA)
  → Télefono: *81 8400 2789*

- *Para adolescentes con problemas de conducta*:
  → Comunicate al Centro de Atención Integral para Adolescentes (CAIPA)
  → Télefono: *81 8478 2092*

🆘 *IDEACIÓN SUICIDA*
Si alguien amenaza con hacerse daño:
- Comunicate inmediatamente al C4 🚔 🚨

📞 *TELÉFONOS DE AYUDA*:
- C4 (emergencias): *81 89 88 2000*
- Centro Integral de Atención a la Mujer (CIAM): *81 8242 5022*
- Centro de Atención Psicológica (CAP): *81 8400 5018*
- Sistema Integral de Protección A Niñas, Niños, y Adolescentes (SIPINNA): *81 8400 2789*
- Centro de Atención Integral para Adolescentes (CAIPA): *81 8478 2092*

🔹 *MUNICIPIO DE SAN PEDRO GARZA GARCÍA* 🔹
*Trabajando por tu seguridad*
"""
    return PROTOCOLO_EMERGENCIAS