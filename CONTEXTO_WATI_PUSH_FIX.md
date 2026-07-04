# Contexto Operativo: Wati + Push Bloqueado

## Objetivo inmediato

Subir a `origin/colegio-militar` el soporte para:

- detectar webhooks de `Wati`
- normalizarlos al formato interno de `/whatsapp`
- responder por el mismo proveedor:
  - si entra por `Chat2Desk` -> responder por `Chat2Desk`
  - si entra por `Wati` -> responder por `Wati`

## Estado actual

### Ya funciona

- El webhook de `Wati` sí llega a `POST /whatsapp`
- El payload de `Wati` ya se normaliza bien
- El flujo del bot sí entra al LLM
- El bot sí genera respuesta
- Ya se confirmó por `curl` que `Wati` sí acepta `sendSessionMessage` en la API nueva `live-mt-server`

### Problema actual

El clone principal local quedó con git trabado en `git gc` / `reflog expire`, así que se hizo un clone limpio:

- carpeta: `../azulMare-push-fix`

En ese clone se hizo:

- `git checkout colegio-militar`
- `git cherry-pick a968026`

Pero el cherry-pick cayó en conflicto en:

- `app/api/original_routes.py`

## Muy importante

El conflicto está en el clone nuevo:

- `azulMare-push-fix`

No en el workspace original.

## Commit que se quiere rescatar

- `a968026`
- mensaje: `Add dual Wati and Chat2Desk webhook routing`

## Rama

- `colegio-militar`

## Archivo en conflicto

- `app/api/original_routes.py`

## Conflicto detectado

Comando usado:

```bash
grep -nE '<<<<<<<|=======|>>>>>>>' app/api/original_routes.py
```

Salida relevante:

```text
633:<<<<<<< HEAD
678:=======
701:>>>>>>> a968026 (Add dual Wati and Chat2Desk webhook routing)
```

Eso significa que el conflicto real está en el helper:

- `send_wati_message_direct(...)`

## Qué versión conservar en ese conflicto

En el bloque entre `<<<<<<< HEAD` y `>>>>>>> a968026`, **conservar la parte de `HEAD`** y eliminar la parte del commit cherry-pickeado.

### Se debe conservar esta versión

```python
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            request_variants = [
                {
                    "label": "bearer-form",
                    "headers": {"Authorization": f"Bearer {api_token}"},
                    "data": {"messageText": text},
                },
                {
                    "label": "token-form",
                    "headers": {"Authorization": api_token},
                    "data": {"messageText": text},
                },
                {
                    "label": "bearer-urlencoded",
                    "headers": {
                        "Authorization": f"Bearer {api_token}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    "data": {"messageText": text},
                },
                {
                    "label": "token-urlencoded",
                    "headers": {
                        "Authorization": api_token,
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    "data": {"messageText": text},
                },
            ]

            for request_variant in request_variants:
                response = await client.post(
                    endpoint,
                    headers=request_variant["headers"],
                    data=request_variant["data"],
                )
                logger.info(
                    f"📥 [WATI SEND] status={response.status_code} endpoint={endpoint} "
                    f"variant={request_variant['label']} response={response.text[:300]}"
                )
                if 200 <= response.status_code < 300:
                    logger.debug(f"✅ [WATI] Mensaje enviado a {phone_number}: {normalized_text[:50]}...")
                    return True
    except Exception as e:
        logger.error(f"❌ [WATI] Error enviando mensaje directo: {str(e)}")
```

### Se debe eliminar

La versión que empieza con:

```python
    headers_variants = [
```

y también:

```python
    body_variants = [
```

## Ojo: ese conflicto NO es todavía la versión final ideal

Esa versión conservada solo sirve para:

- terminar el cherry-pick
- destrabar el push

Después de subir, el sender Wati debe migrarse a la versión final validada por curl:

- endpoint: `https://live-mt-server.wati.io/{tenantId}/api/v1/sendSessionMessage/{whatsappNumber}`
- método: `POST`
- auth: `Authorization: Bearer <token>`
- body: `multipart/form-data` o equivalente aceptado por Wati
- campos:
  - `messageText`
  - `channelPhoneNumber`
  - opcional `replyContextId`

## Validación manual ya confirmada por curl

Este curl sí funcionó:

```bash
curl -i -X POST "https://live-mt-server.wati.io/10183370/api/v1/sendSessionMessage/5218181850026" \
  -H "accept: */*" \
  -H "Authorization: Bearer ${WATI_API_TOKEN}" \
  -F "messageText=Prueba por session message" \
  -F "channelPhoneNumber=15559412894" \
  -F "replyContextId=wamid.HBgNNTIxODE4MTg1MDAyNhUCABIYFDNCQTUxMTRCRDZCM0U1ODI4RUVEAA=="
```

Respuesta:

```json
{
  "ok": true,
  "result": "success",
  "message": {
    "text": "Prueba por session message",
    "replyContextId": "wamid.HBgNNTIxODE4MTg1MDAyNhUCABIYFDNCQTUxMTRCRDZCM0U1ODI4RUVEAA=="
  }
}
```

## Conclusión técnica importante

Para `Wati`:

- `sendSessionMessage` sí funciona
- pero debe ir contra `live-mt-server.wati.io`
- no contra `app-server.wati.io`
- no contra `live.wati.io`
- y no debe ir en JSON

## Variables de entorno relevantes

Ya probadas:

- `WATI_API_TOKEN`
- `WATI_TENANT_ID=10183370`

El campo del número emisor es:

- `channelPhoneNumber = 15559412894`

En el webhook entrante viene como:

- `channelPhoneNumber`

Y el id del mensaje entrante para reply threading viene como:

- `whatsappMessageId`

## Flujo recomendado para la sesión nueva

### 1. En el clone `azulMare-push-fix`

```bash
cd ../azulMare-push-fix
```

### 2. Resolver conflicto

Editar:

- `app/api/original_routes.py`

Quitar marcadores:

- `<<<<<<< HEAD`
- `=======`
- `>>>>>>> a968026 ...`

Conservar la versión indicada arriba.

### 3. Validar sintaxis

```bash
python3 -m py_compile app/api/original_routes.py
```

### 4. Continuar cherry-pick

```bash
git add app/api/original_routes.py
git cherry-pick --continue
```

### 5. Subir

```bash
git push --progress origin colegio-militar
```

## Qué hacer después del push

Una vez subido el cherry-pick, en otra iteración se debe hacer un commit nuevo para dejar `send_wati_message_direct()` en su forma final:

- usar `live-mt-server`
- usar `sendSessionMessage`
- mandar `messageText`
- mandar `channelPhoneNumber`
- mandar `replyContextId` opcional

## Resumen corto para otra sesión

- el parser Wati ya funciona
- el conflicto de cherry-pick está solo en un bloque del helper Wati
- en ese conflicto se debe conservar `HEAD`
- el push está bloqueado por conflicto, no por auth
- luego hay que hacer un commit nuevo con el sender Wati final basado en curl exitoso
