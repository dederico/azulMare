# Handoff operativo de SAM

Última actualización: 2026-11-13, zona horaria `America/Monterrey`.

Este documento conserva el estado técnico y operativo necesario para continuar
el trabajo de SAM sin depender del historial de una conversación. No contiene
tokens, contraseñas ni secretos. Ante una contradicción, el código, las pruebas
y el historial Git son la fuente de verdad.

## Cómo retomar el proyecto

Antes de modificar algo:

1. Leer este documento completo.
2. Ejecutar `git status --short --branch` y `git log -8 --oneline --decorate`.
3. Leer los documentos enlazados en la sección **Fuentes relacionadas**.
4. Confirmar el SHA desplegado en Render antes de diagnosticar producción.
5. Preservar cambios no relacionados y archivos no rastreados del usuario.
6. No usar ni reinstalar el plugin ECC; fue retirado por consumo excesivo de
   contexto.

## Estado al momento del handoff

| Elemento | Estado |
|---|---|
| Repositorio | `https://github.com/dederico/azulMare.git` |
| Rama activa | `temporary-whatsapp-failover` |
| HEAD local y remoto | `2ac9803 fix: prevent repeated report location prompts` |
| Producción | Render, servicio público `https://cfmonterrey.onrender.com` |
| Despliegue | Automático al recibir un push; el despliegue de `2ac9803` debe verificarse por SHA o logs |
| Suite reportada antes del push | `486 passed` |
| Objetivo actual de WhatsApp | Mantener activos e independientes los dos números; no eliminar ninguno |
| Modo deseado | `WHATSAPP_CHANNEL_ROUTING_MODE=parallel` |

El working tree tenía dos archivos no rastreados, deliberadamente excluidos del
commit `2ac9803`:

- `app/services/twilio_chat2desk_bridge.py`
- `tests/test_twilio_chat2desk_bridge.py`

No borrarlos, agregarlos ni modificarlos sin revisar primero su propósito y
confirmar el alcance. Implementan un puente bidireccional Twilio ↔ canal externo
de Chat2Desk, protegido por variables de entorno, pero todavía no forman parte
del commit desplegado.

## Arquitectura vigente

```text
Ciudadano
  └─ WhatsApp / Facebook Messenger / Telegram / widget
       └─ Chat2Desk (bandeja y operación humana)
            └─ POST https://cfmonterrey.onrender.com/whatsapp
                 ├─ cola durable de webhooks
                 ├─ identidad separada por transporte + canal + cliente
                 ├─ control de takeover humano
                 ├─ estado durable del reporte
                 ├─ OpenAI para conversación y herramientas
                 └─ CIAC para creación y seguimiento del folio
```

Chat2Desk es la bandeja central y el sistema donde trabajan los agentes
humanos. Facebook y Telegram se conectan en Chat2Desk, no directamente en
Render. La aplicación responde a todos los transportes por la API de Chat2Desk
con el `client_id`, `channel_id` y `transport` del evento.

El endpoint común de entrada es `/whatsapp` aunque el transporte sea Facebook,
Telegram o widget. El nombre del endpoint es histórico y no implica que solo
acepte WhatsApp.

## Canales conocidos de Chat2Desk

Datos observados mediante `GET /v1/channels` el 2026-11-12:

| Canal | Teléfono | Nombre | Transportes observados |
|---|---|---|---|
| `43906` | `5218112121212` | `BICO-SAMpetrino` | `telegram`, `facebook`, `widget`, `wa_direct` |
| `43943` | `5218135541585` | `SAM 2` | `widget`, `wa_direct` |

El canal `43906` es el original recuperado. El `43943` fue usado como canal
temporal durante la contingencia. La decisión vigente es operar ambos en
paralelo, cada uno con su propia entrada, salida, historial y estado. No se debe
crear un túnel entre ellos mientras el modo sea `parallel`.

## Identidad conversacional

La identidad no debe reducirse al número telefónico:

- WhatsApp paralelo: `chat2desk:wa_direct:channel:<CHANNEL_ID>:client:<CLIENT_ID>`.
- Facebook: `chat2desk:facebook:channel:<CHANNEL_ID>:client:<CLIENT_ID>`.
- Telegram: `chat2desk:telegram:channel:<CHANNEL_ID>:client:<CLIENT_ID>`.
- En modo failover solamente, ambos canales pueden compartir una clave por
  teléfono para conservar la conversación durante el túnel.

Esta separación evita que el canal `43906` responda con el estado del `43943`,
o que Facebook y Telegram mezclen historiales aunque sus identificadores
numéricos coincidan.

En WhatsApp existe un teléfono real. En Facebook y Telegram el identificador de
plataforma, por ejemplo `[tg] 1411252494`, no es un teléfono y nunca debe
enviarse a CIAC como `telefonoReportante`.

Regla de contacto para Facebook y Telegram:

- Una consulta informativa no solicita teléfono.
- Al levantar un reporte que será enviado a CIAC, SAM solicita un teléfono real
  una sola vez y lo guarda mediante `record_report_contact_phone`.
- Sin teléfono real, la frontera de CIAC bloquea la creación del folio.

## Enrutamiento de los dos WhatsApp

La implementación acepta dos modos:

```text
WHATSAPP_CHANNEL_ROUTING_MODE=parallel
WHATSAPP_CHANNEL_ROUTING_MODE=failover
```

`parallel` mantiene ambos canales independientes. `failover` conserva el túnel
reversible creado durante la contingencia. Si no existe la variable explícita,
la bandera histórica `WHATSAPP_FAILOVER_ENABLED=true` activa el túnel; en caso
contrario se usa `parallel`. Un valor explícito inválido falla de forma segura a
`parallel`.

Configuración esperada para la operación actual:

```text
WHATSAPP_CHANNEL_ROUTING_MODE=parallel
WHATSAPP_FAILOVER_ENABLED=false
WHATSAPP_PRIMARY_CHANNEL_ID=43906
WHATSAPP_FAILOVER_CHANNEL_ID=43943
```

Las variables del HSM `CONTINUAR` solo son relevantes en modo `failover`.

## Flujo de reportes

Campos principales de CIAC:

- `selection1`: ID oficial del asunto.
- `selection2`: nombre confiable recibido de Chat2Desk.
- `selection3`: cadena vacía.
- `selection4`: descripción concreta del problema, sin dirección.
- `selection5`: calle o referencia.
- `selection6`: número exterior; `0000` solo cuando no existe o no se conoce.
- `selection7`: colonia; obligatoria en reportes normales.
- Imágenes: opcionales en reportes normales y no solicitadas en emergencias.

La decisión `declared_emergency` tiene tres estados relevantes:

- `None`: todavía no se ha contestado la pregunta.
- `False`: el ciudadano negó que sea emergencia; debe continuar el flujo normal.
- `True`: usar el flujo simplificado de emergencia.

Una respuesta negativa no debe dejar el reporte detenido. Después de identificar
el problema, el flujo normal pregunta únicamente el siguiente campo faltante.

El parser debe aprovechar datos entregados en una sola oración. Ejemplo cubierto
por el fix actual:

```text
Quiero reportar un bache en Vasconcelos 333, colonia Centro, sin imagen.
```

Debe capturar problema, calle, número, colonia y rechazo de imagen sin volver a
preguntar esos datos. Si el ciudadano no menciona imagen, SAM debe preguntarla
una sola vez después de completar ubicación.

## Incidentes importantes y correcciones

### Mezcla de canales y salidas bloqueadas

Síntomas observados:

- El número original `1212` no respondía o recibía estado del temporal.
- Eventos de salida del bot podían interpretarse como takeover humano.
- Facebook generaba respuesta, pero el envío se cancelaba por un epoch obsoleto.

Correcciones relevantes:

- Identidad por transporte, canal y cliente.
- Verificación explícita de eco del bot (`BOT OUTBOX VERIFIED`).
- Takeover persistido solo para salida humana confirmada
  (`CONFIRMED OPERATOR OUTBOX`).
- Límites de conversación durables para descartar eventos realmente antiguos
  sin bloquear la respuesta vigente.

### Loop de Lety: dirección e imágenes repetidas

La conversación de Lety Maldonado expuso que SAM preguntaba repetidamente
número, calle, colonia e imágenes aun después de recibirlos y aun después de
crear el folio `482932`.

Causas combinadas:

- Respuestas cortas como `2` no siempre se aplicaban al campo pendiente.
- El estado durable, la memoria y el historial visible podían divergir.
- Mensajes concurrentes y respuestas posteriores al folio reabrían intake.
- Las imágenes y la ubicación completadas no siempre se reconciliaban antes de
  decidir la siguiente pregunta.

El commit `4a66dca` añadió continuidad post-folio, límites de intentos y pruebas
de regresión del caso Lety.

### Loop de colonia observado el 2026-11-13

Casos reportados:

- `En el casco de San Pedro` / `En el centro de San Pedro` / `En el CASCO`.
- `Residencial Chipinque` seguido de la misma pregunta.
- Una dirección completa: `Av. Roberto Garza Sada 900, Zona Residencial
  Chipinque...` seguida repetidamente por “¿En qué colonia se encuentra el
  problema?”.

El commit `2ac9803` flexibiliza y reconcilia calle, número y colonia escritos de
forma natural; consume respuestas al campo pendiente; evita volver a preguntar
datos ya presentes; y agrega la regresión `tests/test_colony_loop_regression.py`.

### Reanudación después de negar emergencia

El commit `3457ca1` corrige el caso donde el ciudadano decía “No es una
emergencia” y el flujo quedaba detenido. Una decisión `False` debe reanudar el
reporte normal y preguntar el dato faltante.

## Historial Git que explica el estado actual

Orden descendente al crear este handoff:

```text
2ac9803 fix: prevent repeated report location prompts
3457ca1 fix: resume reports after emergency answer
028a754 fix: isolate Chat2Desk conversations by channel
b977804 feat: support parallel WhatsApp channels
4a66dca fix: prevent report intake loops and preserve completed context
28f9a68 fix(chat2desk): preserve multichannel conversation identity
843f997 feat(chat2desk): support facebook and telegram conversations
f6f7a8f fix: reuse existing Chat2Desk failover clients
```

Usar `git show <SHA>` para recuperar el razonamiento implementado y las pruebas
asociadas; no intentar reconstruir esos cambios desde memoria.

## Pruebas

Comando general:

```bash
python -m pytest -q
```

La ejecución previa al commit `2ac9803` reportó `486 passed`. Para cambios en
conversaciones o reportes, ejecutar como mínimo:

```bash
python -m pytest -q \
  tests/test_colony_loop_regression.py \
  tests/test_lety_loop_regression.py \
  tests/test_conversation_policy.py \
  tests/test_report_submission_policy.py \
  tests/test_report_state.py \
  tests/test_chat2desk_channel_identity.py \
  tests/test_whatsapp_failover.py
```

Después ejecutar la suite completa antes de hacer push.

## Operación de Chat2Desk

No colocar el token en comandos versionados. Usar una variable de shell:

```bash
export CHAT2DESK_API_TOKEN='<TOKEN>'
```

Consultar canales:

```bash
curl --location 'https://api.chat2desk.com.mx/v1/channels' \
  --header "Authorization: ${CHAT2DESK_API_TOKEN}"
```

Consultar webhooks con `GET` —no agregar `--data`, porque eso cambia la petición
a `POST`—:

```bash
curl --location 'https://api.chat2desk.com.mx/v1/webhooks' \
  --header "Authorization: ${CHAT2DESK_API_TOKEN}"
```

El webhook esperado apunta a:

```text
https://cfmonterrey.onrender.com/whatsapp
```

Debe recibir `inbox`, `outbox` y los eventos de control requeridos por la
operación humana. Si el webhook tiene una lista `channels`, debe incluir ambos
canales y los canales de Facebook/Telegram que correspondan. Si no tiene ese
campo, Chat2Desk puede entregarle todos los canales.

## Hard reset de una conversación

Endpoint implementado:

```text
POST /admin/reset-conversation/{conversation_key}
```

El reset borra historial, estado de reporte, conclusión/evaluación, takeover,
protecciones anti-duplicado y memoria asociada, y escribe un límite durable para
que un webhook atrasado no reinstale el estado anterior.

Usar la clave exacta mostrada en logs; no adivinarla. Ejemplo:

```bash
export SAM_BASE_URL='https://cfmonterrey.onrender.com'

curl --request POST \
  "${SAM_BASE_URL}/admin/reset-conversation/chat2desk%3Awa_direct%3Achannel%3A43906%3Aclient%3A<CLIENT_ID>"

curl --request POST \
  "${SAM_BASE_URL}/admin/reset-conversation/chat2desk%3Awa_direct%3Achannel%3A43943%3Aclient%3A<CLIENT_ID>"
```

En modo paralelo los dos canales tienen claves distintas y deben resetearse por
separado. Para Facebook o Telegram usar su transporte y su `client_id`. Si hay
estado legado anterior a la separación por canal, puede requerirse además un
reset del teléfono normalizado, pero primero se debe comprobar en logs y BD.

El endpoint administrativo no muestra autenticación en la ruta actual. Esto es
un riesgo pendiente: debe protegerse antes de exponerlo a terceros.

## Takeover humano

Los agentes trabajan en Chat2Desk. Mientras exista takeover humano activo, SAM
debe guardar silencio y no crear folios. El takeover solo se confirma mediante
una señal local autorizada o una salida humana fresca; un eco del propio bot no
debe activarlo.

Logs útiles:

- `BOT OUTBOX VERIFIED`: la salida pertenece a SAM; no activar takeover.
- `CONFIRMED OPERATOR OUTBOX`: salida humana; persistir takeover.
- `WHATSAPP_MAIN BLOCKED` o `FINAL BLOCKED`: salida cancelada por takeover.
- `STALE OPERATOR OUTBOX`: evento anterior al límite vigente; ignorarlo.

Al devolver explícitamente la conversación a SAM, el control se consume una
sola vez y el flujo continúa con el contexto autorizado.

## Render y despliegue

La rama se despliega automáticamente cuando recibe un push. Después de cada
push:

1. Confirmar que Render está desplegando el SHA esperado.
2. Consultar `GET https://cfmonterrey.onrender.com/health`.
3. Revisar logs de arranque y workers.
4. Probar cada canal por separado con un usuario controlado.
5. No hacer hard reset hasta confirmar que el nuevo SHA está activo.

El saldo de OpenAI no requiere un nuevo despliegue por sí mismo: al reponerlo,
las llamadas nuevas usan la misma variable configurada. Solo se redespliega si
cambió código o configuración que Render necesite recargar.

## Matriz mínima de aceptación

Para `43906` y `43943`, probar por separado:

1. `Hola` produce una sola bienvenida.
2. Negar emergencia continúa el flujo normal.
3. Un reporte solicita únicamente campos faltantes.
4. Una dirección completa en una oración no se vuelve a preguntar.
5. Una imagen se conserva y no se vuelve a solicitar.
6. `FIN` crea como máximo un folio.
7. Un mensaje después del folio no reabre el mismo intake.
8. Una salida de SAM no activa takeover humano.
9. Una salida real del operador sí silencia a SAM.
10. El historial de un canal no aparece en el otro.

Para Facebook y Telegram:

1. Una consulta informativa no solicita teléfono.
2. Un reporte solicita teléfono real solo antes de enviarlo a CIAC.
3. El ID de plataforma no llega a `telefonoReportante`.
4. Los historiales de Facebook y Telegram permanecen aislados.

## Pendientes y decisiones abiertas

- Verificar en Render que `2ac9803` esté activo y registrar el resultado.
- Confirmar que el entorno use `WHATSAPP_CHANNEL_ROUTING_MODE=parallel`.
- Ejecutar la matriz controlada completa en ambos WhatsApp después del
  despliegue y de resets separados.
- Decidir si los dos archivos no rastreados del puente Twilio se descartan, se
  terminan o se versionan. No están desplegados.
- No hay evidencia en el código actual de prefijos de prefolio `MESS-`, `WHP-`
  o `TEL-`; fueron una idea discutida, no debe asumirse implementada.
- Proteger los endpoints `/admin/*`, especialmente el hard reset.
- Rotar el token de Chat2Desk que fue pegado en una conversación y mantener el
  reemplazo exclusivamente en secretos de Render/entorno.
- No eliminar ninguno de los dos números o canales hasta una decisión explícita
  posterior.

## ECC y consumo de contexto

El 2026-11-13 se desinstaló `ecc@ecc` y se retiró el marketplace `ecc` de la
configuración local de Codex. El catálogo de ECC ya cargado permanece visible
solo durante la sesión en la que se desinstaló. En sesiones futuras no debe
reinstalarse ni utilizarse. El mensaje `Exceeded skills context budget` era
causado principalmente por el catálogo masivo de habilidades de ECC.

## Fuentes relacionadas

- [`docs/chat2desk-facebook-telegram.md`](chat2desk-facebook-telegram.md)
- [`docs/whatsapp-temporary-failover.md`](whatsapp-temporary-failover.md)
- [`docs/control-danos-whatsapp-meta-2026-10-29.md`](control-danos-whatsapp-meta-2026-10-29.md)
- [`docs/tdd/handoff-intent.tdd.md`](tdd/handoff-intent.tdd.md)
- [`docs/tdd/image-report-context.tdd.md`](tdd/image-report-context.tdd.md)
- [`docs/tdd/report-description-field-ownership.tdd.md`](tdd/report-description-field-ownership.tdd.md)
- `app/api/original_routes.py`
- `app/services/chat2desk_channel_identity.py`
- `app/services/whatsapp_failover.py`
- `app/services/conversation_policy.py`
- `app/services/report_intake_policy.py`
- `app/services/report_submission_policy.py`
- `app/services/report_state.py`
- `app/services/conversation_lifecycle.py`

## Regla final para futuros cambios

No resolver problemas conversacionales únicamente agregando instrucciones al
prompt. Primero identificar el estado durable, el campo pendiente, la identidad
del canal y el evento concurrente; después escribir una prueba de regresión que
reproduzca la conversación real, implementar la corrección determinista y
ejecutar la suite completa.
