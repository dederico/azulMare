# Failover temporal de WhatsApp

Este mecanismo recibe los mensajes del canal original de SAM y continúa la
conversación desde `SAM 2` mientras la cuenta principal permanezca bloqueada.
Está desactivado por defecto y no modifica el widget web.

## Flujo

1. El webhook recibe el mensaje dirigido al canal original `43906`.
2. SAM guarda durablemente el payload completo, incluidos texto, imágenes y
   ubicación.
3. `SAM 2` (`43943`) envía el HSM aprobado de continuidad.
4. Cuando el ciudadano responde al HSM, SAM activa la ruta temporal y reprocesa
   el mensaje original desde `SAM 2`.
5. La respuesta que confirma el cambio de canal no se entrega al modelo ni se
   usa como dato del reporte.
6. Los mensajes, folios, documentos y notificaciones posteriores se resuelven
   por el canal temporal mientras su ventana esté activa.

## Variables de Render

```text
WHATSAPP_FAILOVER_ENABLED=false
WHATSAPP_PRIMARY_CHANNEL_ID=43906
WHATSAPP_FAILOVER_CHANNEL_ID=43943
WHATSAPP_FAILOVER_TEMPLATE=continuidad_canal_temporal
WHATSAPP_FAILOVER_TEMPLATE_LANGUAGE=es_mx
WHATSAPP_FAILOVER_ACTIVE_TTL_SECONDS=82800
```

Desplegar primero con `WHATSAPP_FAILOVER_ENABLED=false`. Cambiarla a `true`
únicamente después de confirmar que el HSM aprobado aparece sincronizado en el
canal `SAM 2` y que el webhook temporal está habilitado.

## Webhook temporal de Chat2Desk

Crear un webhook adicional hacia el mismo endpoint de producción, sin modificar
el webhook original:

```json
{
  "name": "SAM 2 - failover temporal",
  "url": "https://cfmonterrey.onrender.com/whatsapp",
  "events": ["inbox", "outbox", "outbox_status", "dialog_transferred"],
  "channels": [43943]
}
```

## Prueba controlada

1. Enviar desde un número de prueba un mensaje al WhatsApp original.
2. Confirmar que no se produce respuesta conversacional desde el canal original.
3. Confirmar la recepción del HSM desde `SAM 2`.
4. Pulsar `CONTINUAR`.
5. Confirmar que SAM responde al mensaje original desde `SAM 2`.
6. Continuar un reporte con texto, ubicación e imagen y verificar que el folio
   también llegue por `SAM 2`.
7. Verificar que el widget web continúe respondiendo sin cambios.

## Reversión

1. Cambiar `WHATSAPP_FAILOVER_ENABLED=false` en Render.
2. Deshabilitar el webhook temporal de `SAM 2`.
3. No eliminar las tablas de failover: conservan el rastro de auditoría de los
   mensajes procesados durante la contingencia.

El código deja de redirigir inmediatamente al desactivar la bandera; no requiere
revertir commits ni modificar el flujo conversacional.
