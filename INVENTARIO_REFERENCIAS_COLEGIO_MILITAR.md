# Inventario Inicial De Referencias Heredadas

## Objetivo

Este inventario documenta los acoplamientos heredados detectados en la rama `colegio-militar` antes de empezar la personalización real hacia Colegio Militar.

Se separa por:

- branding
- prompts
- funciones
- integraciones
- catálogos/datos duros
- admin/operación

## Resumen Ejecutivo

El proyecto no está en un estado “casi neutro”. Sigue cargado fuertemente hacia la operación anterior.

Hallazgos principales:

1. El backend principal sigue orientado a Atención Ciudadana / SPGG / CIAC.
2. El registro de funciones sigue exponiendo 70 funciones del dominio anterior.
3. Los catálogos de calles y colonias de San Pedro siguen conectados al flujo principal de WhatsApp.
4. El módulo admin nuevo sigue nombrado como `SAM` y usa rutas `ciac`.
5. El prompt cargado por defecto ya no es San Pedro, pero tampoco es Colegio Militar: hoy habla de `Lucia`, `BLACKBERRY MEXICO` y soporte comercial.

## 1. Branding

### Referencias visibles heredadas

- [app/main.py](/Users/federicogonzalez/Desktop/Desktop%20-%20MacBook%20Air%20de%20Federico/Beholder-Skeleton-SaaS/azulMare/app/main.py:24)
  `APP_NAME = "spgg-gpt"`
- [app/frontend/pages/sam_base_conocimiento.html](/Users/federicogonzalez/Desktop/Desktop%20-%20MacBook%20Air%20de%20Federico/Beholder-Skeleton-SaaS/azulMare/app/frontend/pages/sam_base_conocimiento.html:6)
  título `SAM Base de Conocimiento`
- [app/frontend/pages/sam_base_conocimiento.html](/Users/federicogonzalez/Desktop/Desktop%20-%20MacBook%20Air%20de%20Federico/Beholder-Skeleton-SaaS/azulMare/app/frontend/pages/sam_base_conocimiento.html:117)
  texto “para SAM”
- [app/api/original_routes.py](/Users/federicogonzalez/Desktop/Desktop%20-%20MacBook%20Air%20de%20Federico/Beholder-Skeleton-SaaS/azulMare/app/api/original_routes.py:3731)
  saludo automático: `Soy SAM, tu asistente virtual de Atención Ciudadana de SPGG`

### Implicación

Aunque el proyecto ya está en la rama `colegio-militar`, la identidad visible sigue mezclada entre:

- SPGG / San Pedro
- SAM
- Atención Ciudadana

## 2. Prompt

### Prompt por defecto actual

- [app/services/llm/config/system.py](/Users/federicogonzalez/Desktop/Desktop%20-%20MacBook%20Air%20de%20Federico/Beholder-Skeleton-SaaS/azulMare/app/services/llm/config/system.py:11)

### Hallazgo

El prompt por defecto no está alineado ni con San Pedro ni con Colegio Militar. Hoy define:

- agente: `Lucia`
- organización: `BLACKBERRY MEXICO`
- objetivo: soporte comercial y dudas técnicas

### Implicación

Antes de limpiar funciones, hay que redefinir el prompt central. Si no, el robot del Colegio Militar nacería con comportamiento de otro negocio.

## 3. Funciones Registradas

### Estado actual

- [app/services/functions/function_registry.py](/Users/federicogonzalez/Desktop/Desktop%20-%20MacBook%20Air%20de%20Federico/Beholder-Skeleton-SaaS/azulMare/app/services/functions/function_registry.py:1)
- Total actual en `registered_functions`: `70`

### Ejemplos de funciones heredadas de dominio anterior

- `get_funcionarios`
- `get_centros_comunitarios`
- `get_ubicaciones`
- `get_dif`
- `get_seguridad`
- `get_san_pedro_de_pinta`
- `get_predial`
- `get_pasaportes`
- `get_miercoles_ciudadano`
- `get_actividades_san_pedro_parques`
- `get_actividades_mayo_junio`
- `get_actividades_mundial`

### Implicación

No conviene “borrar todo” a ciegas. Lo correcto es clasificar estas 70 funciones en tres grupos:

- conservar como plantilla técnica
- adaptar a Colegio Militar
- eliminar/desregistrar

## 4. Integraciones

### Chat2Desk

- [app/frontend/controllers.py](/Users/federicogonzalez/Desktop/Desktop%20-%20MacBook%20Air%20de%20Federico/Beholder-Skeleton-SaaS/azulMare/app/frontend/controllers.py:433)
- [app/api/original_routes.py](/Users/federicogonzalez/Desktop/Desktop%20-%20MacBook%20Air%20de%20Federico/Beholder-Skeleton-SaaS/azulMare/app/api/original_routes.py:489)
- [app/api/original_routes.py](/Users/federicogonzalez/Desktop/Desktop%20-%20MacBook%20Air%20de%20Federico/Beholder-Skeleton-SaaS/azulMare/app/api/original_routes.py:3090)

Hallazgo:

- la mensajería depende fuertemente de `CHAT2DESK_API_TOKEN`
- hay búsquedas/creación de clientes
- hay envío de mensajes e imágenes
- el módulo de campañas también depende de Chat2Desk

### CIAC / APIs de San Pedro

- [app/api/original_routes.py](/Users/federicogonzalez/Desktop/Desktop%20-%20MacBook%20Air%20de%20Federico/Beholder-Skeleton-SaaS/azulMare/app/api/original_routes.py:412)
- [app/api/original_routes.py](/Users/federicogonzalez/Desktop/Desktop%20-%20MacBook%20Air%20de%20Federico/Beholder-Skeleton-SaaS/azulMare/app/api/original_routes.py:755)
- [app/api/original_routes.py](/Users/federicogonzalez/Desktop/Desktop%20-%20MacBook%20Air%20de%20Federico/Beholder-Skeleton-SaaS/azulMare/app/api/original_routes.py:812)

Hallazgo:

- `original_routes.py` sigue pegando a endpoints `ciac.sanpedro.gob.mx`
- esto no es branding; es lógica operativa real

### Implicación

Si Colegio Militar no usará esas APIs, estas integraciones deben apagarse o aislarse pronto.

## 5. Catálogos Y Datos Duros

### Arrays de calles y colonias

- [app/api/streets_array.py](/Users/federicogonzalez/Desktop/Desktop%20-%20MacBook%20Air%20de%20Federico/Beholder-Skeleton-SaaS/azulMare/app/api/streets_array.py:1)
- [app/api/colonies_array.py](/Users/federicogonzalez/Desktop/Desktop%20-%20MacBook%20Air%20de%20Federico/Beholder-Skeleton-SaaS/azulMare/app/api/colonies_array.py:1)
- [app/api/original_routes.py](/Users/federicogonzalez/Desktop/Desktop%20-%20MacBook%20Air%20de%20Federico/Beholder-Skeleton-SaaS/azulMare/app/api/original_routes.py:85)
- [app/api/original_routes.py](/Users/federicogonzalez/Desktop/Desktop%20-%20MacBook%20Air%20de%20Federico/Beholder-Skeleton-SaaS/azulMare/app/api/original_routes.py:1154)

Hallazgo:

- el flujo principal importa `SAN_PEDRO_STREETS_REAL` y `SAN_PEDRO_COLONIES`
- estas listas se usan activamente para detectar dirección/colonia
- no son archivos muertos

### Geografía fija en funciones

Ejemplos:

- [app/services/functions/implementations/get_climate.py](/Users/federicogonzalez/Desktop/Desktop%20-%20MacBook%20Air%20de%20Federico/Beholder-Skeleton-SaaS/azulMare/app/services/functions/implementations/get_climate.py:9)
  constantes `SAN_PEDRO_LAT`, `SAN_PEDRO_LON`, `SAN_PEDRO_NAME`
- [app/services/functions/implementations/get_traffic.py](/Users/federicogonzalez/Desktop/Desktop%20-%20MacBook%20Air%20de%20Federico/Beholder-Skeleton-SaaS/azulMare/app/services/functions/implementations/get_traffic.py:10)
  centro fijo de San Pedro

### Implicación

Si Colegio Militar no necesita catálogos territoriales, hay que sacarlos del flujo, no solo renombrarlos.

## 6. Admin Y Operación

### Rutas y credenciales hardcodeadas

- [app/frontend/routes.py](/Users/federicogonzalez/Desktop/Desktop%20-%20MacBook%20Air%20de%20Federico/Beholder-Skeleton-SaaS/azulMare/app/frontend/routes.py:17)
  `SAM_KB_USERNAME = "atencion_ciudadana"`
- [app/frontend/routes.py](/Users/federicogonzalez/Desktop/Desktop%20-%20MacBook%20Air%20de%20Federico/Beholder-Skeleton-SaaS/azulMare/app/frontend/routes.py:18)
  `SAM_KB_PASSWORD = "sam_2026"`
- [app/frontend/routes.py](/Users/federicogonzalez/Desktop/Desktop%20-%20MacBook%20Air%20de%20Federico/Beholder-Skeleton-SaaS/azulMare/app/frontend/routes.py:76)
  ruta `/ciac/sam-base-de-conocimiento`
- [app/frontend/routes.py](/Users/federicogonzalez/Desktop/Desktop%20-%20MacBook%20Air%20de%20Federico/Beholder-Skeleton-SaaS/azulMare/app/frontend/routes.py:143)
  ruta `/ciac/mensajes-proactivos`

### Módulo de campañas

- [app/frontend/pages/outgoing_messages.html](/Users/federicogonzalez/Desktop/Desktop%20-%20MacBook%20Air%20de%20Federico/Beholder-Skeleton-SaaS/azulMare/app/frontend/pages/outgoing_messages.html:171)
  ejemplo de destinatarios con campo `K`
- [app/frontend/controllers.py](/Users/federicogonzalez/Desktop/Desktop%20-%20MacBook%20Air%20de%20Federico/Beholder-Skeleton-SaaS/azulMare/app/frontend/controllers.py:36)
  `DEFAULT_CHAT2DESK_CHANNEL_ID = 43388`

### Implicación

El admin no está neutro:

- conserva naming `SAM`
- conserva naming `CIAC`
- conserva credenciales fijas
- conserva supuestos operativos (`K`, Chat2Desk, campañas)

## 7. Clasificación Inicial Recomendada

### Branding

- `app/main.py`
- `app/frontend/pages/sam_base_conocimiento.html`
- saludos y mensajes de `original_routes.py`

### Prompt

- `app/services/llm/config/system.py`
- prompt guardado dinámicamente en `configs.prompt`

### Funciones

- `app/services/functions/function_registry.py`
- `app/services/functions/implementations/`

### Integraciones

- `app/api/original_routes.py`
- `app/frontend/controllers.py`

### Catálogos

- `app/api/streets_array.py`
- `app/api/colonies_array.py`

### Admin

- `app/frontend/routes.py`
- `app/frontend/pages/outgoing_messages.html`
- `app/frontend/pages/sam_base_conocimiento.html`

## 8. Recomendación Inmediata

Orden recomendado de trabajo desde este punto:

1. redefinir prompt y nombre del agente para Colegio Militar
2. reducir `function_registry.py` a un conjunto mínimo controlado
3. sacar del flujo principal los arrays de San Pedro
4. apagar o aislar integraciones CIAC
5. renombrar rutas/admin `SAM` y `CIAC`

## 9. Decisión Técnica Recomendada Sobre Funciones

No recomiendo borrar de inmediato todos los archivos `get_*`.

Sí recomiendo:

1. dejar `function_registry.py` mínimo
2. conservar implementaciones viejas solo como referencia temporal
3. dejar una función muestra neutra para validar el mecanismo KB

Esto permite limpiar comportamiento sin destruir contexto útil todavía.
