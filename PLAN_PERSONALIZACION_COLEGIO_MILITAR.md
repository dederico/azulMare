# Plan De Personalizacion Del Esqueleto Hacia Colegio Militar

## Objetivo

Usar la rama `colegio-militar` como base limpia para convertir el proyecto actual, hoy orientado a San Pedro / SPPG, en una version nueva enfocada completamente a Colegio Militar.

La idea no es solo cambiar textos visibles. Hay que revisar:

- branding
- variables de entorno
- base de datos
- prompts
- funciones registradas
- integraciones externas
- catálogos duros como calles, colonias y directorios
- rutas administrativas
- templates y contenido visual

Este documento sirve como guia operativa para hacer la migracion de forma ordenada, sin romper el esqueleto.

## Regla General

No conviene hacer un reemplazo masivo ciego de `San Pedro`, `spgg`, `sam`, `ciac` o strings relacionados. El proyecto tiene:

- referencias cosméticas
- referencias funcionales
- referencias a APIs
- referencias a base de datos
- referencias a funciones concretas del dominio actual

Cada capa se debe revisar por separado.

## Estrategia Recomendada

La migracion debe hacerse en este orden:

1. entorno y seguridad
2. branding y textos visibles
3. prompts y comportamiento del agente
4. funciones e integraciones especificas de San Pedro
5. datos duros del municipio actual
6. rutas y modulos administrativos
7. despliegue aislado
8. validacion funcional completa

## Fase 0. Congelar La Base De Trabajo

### Objetivo

Partir de una rama limpia y no mezclar cambios viejos de `spgg-demo-2025`.

### Estado esperado

- rama activa: `colegio-militar`
- working tree limpio

### Comandos sugeridos

```bash
git branch --show-current
git status
```

Si no esta limpio, no seguir hasta entender por que.

## Fase 1. Preparar Entorno Aislado

### Objetivo

No reutilizar credenciales, base de datos ni despliegue de San Pedro.

### Que hay que hacer

1. Crear una nueva base de datos para Colegio Militar.
2. Crear un nuevo servicio en Render.
3. Preparar un nuevo `.env` o variables separadas para ese servicio.
4. No compartir secretos con SPPG si no es intencional.

### Variables que se deben revisar

- `DATABASE`
- `DB_HOST`
- `DB_PORT`
- `DB_USERNAME`
- `DB_PASSWORD`
- `PORT`
- `SECRET`
- `OPENAI_API_KEY`
- `CHAT2DESK_API_TOKEN`
- `CHAT2DESK_CHANNEL_ID`
- cualquier URL de APIs municipales actuales

### Nota importante sobre base de datos

Hoy el proyecto apunta por variables a una base tipo `spgg-c2d`. Eso debe cambiar a una base nueva dedicada para Colegio Militar.

No es una tabla. Es la base completa. Dentro de esa base, el servicio crea tablas como:

- `calls`
- `users`
- `configs`
- `messages`
- `notifications`
- `outgoingcampaigns`
- `outgoingrecipients`

### Criterio

No seguir con branding ni prompts hasta tener claro a que base y a que despliegue se conectara esta nueva instancia.

## Fase 2. Inventario De Referencias A San Pedro

### Objetivo

Identificar todo lo que sigue amarrado al dominio anterior.

### Busquedas recomendadas

```bash
grep -RniE "san pedro|sanpedro|spgg|ciac|sam_|sam-" app .env* *.md
```

```bash
grep -RniE "San Pedro|SPGG|CIAC|SAM" app
```

### Clasificacion obligatoria

Cada hallazgo debe clasificarse como:

- visual
- configuracion
- prompt
- integracion
- dato duro
- logica de negocio

### Resultado esperado

Un listado de referencias separadas por categoria, no un reemplazo directo.

## Fase 3. Branding Y Textos Visibles

### Objetivo

Que el sistema deje de verse como SPPG / San Pedro / SAM.

### Archivos a revisar primero

- `app/frontend/pages/`
- `app/frontend/static/`
- `app/frontend/routes.py`
- `app/main.py`
- documentos `.md`

### Que cambiar

- nombre del proyecto
- titulos HTML
- encabezados de formularios
- nombres de modulos
- textos de acceso
- mensajes de exito/error donde aparezca San Pedro o SAM
- logos, fondos y assets

### Casos concretos actuales

1. El modulo de base de conocimiento dice `SAM Base de Conocimiento`.
2. Hay credenciales y rutas con prefijo `ciac` y `sam`.
3. Existen templates y previews con naming del modulo actual.

### Decision que hay que tomar

Definir si:

- se conserva la idea de modulo de base de conocimiento pero con otro nombre
- o se renombra completo a otra nomenclatura institucional

## Fase 4. Rutas Y Modulos Administrativos

### Objetivo

Revisar si las rutas actuales siguen teniendo sentido en Colegio Militar.

### Rutas nuevas actuales

- `/admin/ciac/sam-base-de-conocimiento`
- `/admin/ciac/mensajes-proactivos`

### Preguntas a resolver

1. ¿`ciac` sigue teniendo sentido?
2. ¿`sam` sigue siendo el nombre del agente?
3. ¿`mensajes-proactivos` se queda igual?
4. ¿las credenciales hardcodeadas deben sobrevivir o pasar a env vars?

### Recomendacion

Mover credenciales fijas a variables de entorno antes de salir a un despliegue serio.

### Archivo principal

- `app/frontend/routes.py`

## Fase 5. Prompt Principal Y Configuracion Del Agente

### Objetivo

Cambiar el comportamiento del asistente para Colegio Militar.

### Que revisar

- `configs.prompt` en base de datos
- archivos de prompt en repo
- instrucciones del agente
- alta dinamica de funciones KB

### Riesgo

Aunque cambies branding, si el prompt sigue hablando de San Pedro o instruyendo funciones del municipio actual, el bot seguirá comportándose como SPPG.

### Que hay que hacer

1. Exportar o inspeccionar el prompt actual.
2. Identificar referencias al municipio anterior.
3. Definir el nuevo rol del agente.
4. Reescribir intenciones, alcance y tono.
5. Validar el bloque dinamico de funciones KB.

### Archivos relacionados

- `app/frontend/controllers.py`
- `app/services/functions/function_registry.py`
- `prompt_actual.txt`
- cualquier config persistida en `configs`

## Fase 6. Base De Conocimiento

### Objetivo

Reemplazar el contenido KB dependiente de San Pedro por contenido real de Colegio Militar.

### Lo que existe hoy

Hay un modulo administrativo capaz de:

- crear nuevas funciones `get_*`
- registrarlas en `function_registry.py`
- inyectarlas en el prompt

### Que hay que revisar

1. Si la estructura actual de autogestion sigue siendo útil.
2. Si los documentos TC actuales son reutilizables o no.
3. Si se deben eliminar funciones `get_*` que solo aplican a San Pedro.

### Recomendacion operativa

No borrar primero. Mejor clasificar:

- funciones que se pueden conservar como esqueleto
- funciones que deben desactivarse
- funciones que deben reescribirse
- funciones nuevas que habrá que crear para Colegio Militar

### Archivos clave

- `app/services/functions/implementations/`
- `app/services/functions/function_registry.py`
- `app/frontend/controllers.py`

## Fase 7. Funciones E Integraciones Especificas De San Pedro

### Objetivo

Detectar todo lo que pega a APIs, directorios y procesos específicos del municipio actual.

### Tipos de funciones a revisar

- directorios
- ubicaciones
- colonias
- parques
- movilidad
- reportes
- pagos
- servicios ciudadanos
- actividades o eventos

### Indicadores de acoplamiento

- nombres `get_san_pedro_*`
- nombres `spgg`
- URLs a sistemas del municipio actual
- catálogos incrustados
- prompts que llaman funciones de dominio antiguo

### Ejemplos evidentes

- `get_actividades_san_pedro_parques`
- arrays de calles y colonias
- integraciones CIAC
- status/reportes municipales

### Criterio

Cada funcion debe terminar en una de estas tres canastas:

1. conservar como plantilla
2. adaptar a Colegio Militar
3. eliminar/desregistrar

## Fase 8. Arrays, Catalogos Y Datos Duros

### Objetivo

Eliminar o sustituir datos fijos del municipio anterior.

### Mencion especial

Ya identificaste correctamente que:

- arrays de calles
- arrays de colonias

probablemente ya no serán necesarios o deberán cambiar radicalmente.

### Archivos y zonas a revisar

- `app/api/streets_array.py`
- `app/api/colonies_array.py`
- variantes duplicadas o archivos similares
- cualquier lista fija en `app/api/`
- funciones que dependan de esos arrays

### Posibles decisiones

1. eliminarlos si el nuevo cliente no los necesita
2. sustituirlos por catálogos propios
3. moverlos a base de datos o a archivos configurables

### Recomendacion

No portar arrays de San Pedro a Colegio Militar “por si acaso”. Si no se necesitan, mejor quitarlos del flujo.

## Fase 9. WhatsApp, Chat2Desk Y Mensajeria

### Objetivo

Verificar si el canal y la operación de mensajería siguen siendo los mismos.

### Lo que existe hoy

El modulo de mensajes proactivos usa:

- `CHAT2DESK_API_TOKEN`
- `CHAT2DESK_CHANNEL_ID`
- transporte tipo `wa_direct`

### Preguntas a resolver

1. ¿Colegio Militar usará Chat2Desk?
2. ¿será el mismo canal?
3. ¿la lógica de client lookup sigue siendo válida?
4. ¿los templates de campaña tienen el tono correcto?

### Archivos clave

- `app/frontend/controllers.py`
- `app/frontend/pages/outgoing_messages.html`
- `app/main.py`

## Fase 10. Modulo De Mensajes Proactivos

### Objetivo

Validar si este modulo se reutiliza tal cual o si cambia de objetivo.

### Elementos a revisar

- naming de campañas
- responsable de campaña
- formato de destinatarios
- metadata como `K`
- lógica de programación y envío

### Decision importante

El campo `K` puede ser específico de la operación actual. Si Colegio Militar no usa ese criterio, no conviene dejarlo como supuesto implícito.

### Recomendacion

Volver la UI y los ejemplos neutrales si `K` ya no aplica.

## Fase 11. Autenticacion Y Seguridad

### Objetivo

No salir a otro despliegue con credenciales duras heredadas.

### Riesgos actuales

- usuario hardcodeado: `atencion_ciudadana`
- password hardcodeado: `sam_2026`

### Recomendacion

Migrar estas credenciales a variables de entorno antes de usar el sistema fuera de pruebas internas.

### Archivos clave

- `app/frontend/routes.py`

## Fase 12. Admin General Y Setup Inicial

### Objetivo

Validar el comportamiento de:

- `/admin/`
- `/auth/signup/`
- `/auth/login/`

### Preguntas

1. ¿Quieres seguir teniendo signup inicial?
2. ¿quieres un solo admin general?
3. ¿o habrá accesos separados por modulo?

### Riesgo

Si el flujo de auth queda igual pero el despliegue usa otra base vacía, el primer arranque puede comportarse distinto en `signup/login`.

## Fase 13. Integraciones Externas

### Objetivo

Reemplazar o apagar todo lo que pegue a APIs del ecosistema actual.

### Revisar específicamente

- APIs municipales
- endpoints de reportes
- pagos
- directorios
- imágenes/fotos de reportes
- webhooks
- Twilio / STT / TTS / OpenAI

### Criterio

Separar claramente:

- integraciones que siguen vivas en Colegio Militar
- integraciones que cambian de endpoint o credenciales
- integraciones que ya no existen

## Fase 14. Limpieza De Archivos Sueltos

### Objetivo

No arrastrar al nuevo proyecto basura histórica o archivos duplicados.

### Archivos sospechosos

Hay varios archivos con patrones como:

- `* 2.py`
- previews
- imágenes sueltas
- documentos temporales
- scripts de prueba

### Regla

Antes de preparar el despliegue de Colegio Militar, decidir qué:

- se conserva
- se documenta
- se mueve a archivo de trabajo
- se elimina

## Fase 15. Deploy Nuevo En Render

### Objetivo

Levantar Colegio Militar como instancia separada.

### Que hay que hacer

1. Crear servicio nuevo, no reciclar el de SPPG.
2. Configurar rama correcta.
3. Configurar variables nuevas.
4. Configurar base nueva.
5. Confirmar comando de arranque.

### Recordatorio

El entorno local puede fallar por dependencias, pero Render puede comportarse distinto si el build usa el stack correcto. Aun así, no hay que asumir éxito sin validar.

## Fase 16. Checklist De Validacion

### Validacion minima de infraestructura

1. el servicio arranca
2. conecta a la base correcta
3. ejecuta migraciones
4. responde `/health` si aplica
5. carga `/admin/`

### Validacion minima de branding

1. no aparece San Pedro en UI
2. no aparece SAM si ya no aplica
3. no aparecen logos o fondos heredados

### Validacion minima del agente

1. no responde con contexto de SPPG
2. no invoca funciones irrelevantes
3. usa el prompt correcto

### Validacion minima de KB

1. el modulo abre
2. login correcto
3. puede crear función KB si seguirá existiendo
4. `function_registry.py` queda consistente
5. el prompt se actualiza correctamente

### Validacion minima de mensajes proactivos

1. abre el modulo
2. login correcto
3. guarda campaña
4. guarda destinatarios
5. envía manualmente si aplica
6. scheduler funciona si se mantiene

## Fase 17. Orden Real De Trabajo Recomendado

### Sprint 1. Base e identidad

1. nueva rama
2. nueva base
3. nuevo servicio Render
4. branding base
5. nombre del agente

### Sprint 2. Limpieza funcional

1. inventario de referencias San Pedro
2. clasificar funciones
3. apagar o quitar dependencias irrelevantes
4. revisar arrays y catálogos

### Sprint 3. Prompt y KB

1. redefinir prompt principal
2. redefinir catálogo de funciones
3. decidir si el modulo KB se conserva

### Sprint 4. Operación

1. revisar mensajería proactiva
2. revisar integraciones activas
3. revisar auth y seguridad

### Sprint 5. Deploy y QA

1. deploy de prueba
2. smoke test
3. ajuste fino
4. validación funcional con casos reales

## Primera Tarea Recomendada Inmediata

Antes de empezar a tocar archivos, hacer este inventario:

```bash
grep -RniE "san pedro|sanpedro|spgg|ciac|sam_|sam-" app .env* *.md
```

Y de ahi separar el resultado en:

- branding
- prompts
- integraciones
- funciones
- arrays/catálogos
- admin

## Resultado Esperado Final

Al terminar, `colegio-militar` debe quedar como una instancia nueva que:

- no depende conceptualmente de San Pedro
- no reutiliza base de datos de SPPG
- no conserva branding heredado
- no llama funciones irrelevantes
- no usa arrays/catálogos viejos si ya no aplican
- puede desplegarse como producto independiente

