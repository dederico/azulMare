# SAM en Facebook Messenger y Telegram mediante Chat2Desk

SAM conserva a Chat2Desk como bandeja única. Facebook Messenger y Telegram se
conectan de forma nativa en Chat2Desk y envían sus eventos al mismo webhook que
ya procesa WhatsApp: `/whatsapp`.

No se requieren tokens de Facebook o Telegram en Render. Esos tokens pertenecen
a la configuración del canal en Chat2Desk. La aplicación utiliza únicamente el
token existente `CHAT2DESK_API_TOKEN` para responder mediante
`POST /v1/messages` con el `client_id`, `channel_id` y `transport` recibidos.

## Identidad conversacional

WhatsApp identifica al ciudadano mediante su teléfono. En los mensajeros API,
Chat2Desk puede enviar identificadores como `[tg] 734937551`; ese valor no es un
número telefónico.

SAM mantiene por separado:

- la identidad interna de la conversación: transporte + canal + cliente;
- el teléfono real de contacto, únicamente cuando el ciudadano lo comparte.

Las consultas informativas no requieren teléfono. Para crear un reporte de CIAC
desde Facebook o Telegram, SAM solicita un teléfono real y lo registra antes de
enviar el reporte. El identificador interno del mensajero nunca se envía como
`telefonoReportante`.

## Activación en Chat2Desk

1. Conectar el bot de Telegram en **Settings → Channels and messengers** con el
   token generado por BotFather.
2. Conectar la página pública de Facebook en la misma sección, autorizando a
   Chat2Desk con una cuenta administradora de la página.
3. Anotar los `channel_id` asignados a ambos canales.
4. Consultar `GET /v1/webhooks`:
   - si el webhook de SAM no contiene el campo `channels`, recibirá todos los
     canales y no requiere cambios;
   - si contiene una lista `channels`, agregar los `channel_id` de Facebook y
     Telegram sin retirar los canales actuales.
5. Conservar los eventos `inbox`, `outbox` y `dialog_transferred` que ya utiliza
   la operación de SAM y la toma humana.

Los nombres oficiales de transporte documentados por Chat2Desk son `facebook`
y `telegram`.

## Prueba de aceptación

Ejecutar por separado desde Facebook y Telegram:

1. Enviar un saludo y verificar una sola bienvenida.
2. Hacer una consulta informativa; no debe solicitar teléfono.
3. Solicitar una acción municipal para iniciar un reporte.
4. Confirmar que SAM solicita teléfono solamente antes de crear el reporte.
5. Proporcionar un teléfono válido y completar calle, número, colonia e imagen
   opcional.
6. Verificar en CIAC que `telefonoReportante` contiene el número compartido, no
   el ID de Facebook o Telegram.
7. Tomar el chat con un agente humano y comprobar que SAM deja de contestar.
8. Devolver el chat a SAM y comprobar que continúa la misma conversación.
9. Usar IDs de cliente iguales simulados en ambos transportes y comprobar que
   los historiales no se mezclan.

Según el contrato de transportes de Chat2Desk, Facebook y Telegram soportan
texto e imágenes de entrada y salida. Los documentos entrantes no están
disponibles para estos dos transportes en el contrato consultado; no deben ser
parte de la prueba inicial.

## Referencia oficial

Colección de API de Chat2Desk:
<https://documenter.getpostman.com/view/8899980/UVC8BRBo>
