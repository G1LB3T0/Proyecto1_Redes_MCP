# Proyecto 1: uso de un protocolo existente

Universidad del Valle de Guatemala · CC3067 Redes

**Caso de estudio:** inventario de farmacia mediante Model Context Protocol.
**Fecha de verificación:** 21 de septiembre de 2026.

## 1. Objetivo y resultado

Se implementó un chatbot de consola que accede a Gemini mediante su API,
mantiene contexto durante la sesión y coordina tres servidores MCP. Filesystem
y Git son servidores oficiales locales. Farmacia es una implementación manual
propia disponible tanto por stdio local como por HTTPS en Hetzner.

La demostración real completó seis turnos: pregunta general, seguimiento con
contexto, tres consultas de farmacia, seguimiento sobre los resultados, consulta
de un SKU inexistente y escritura/commit con los servidores oficiales. Pasaron
27 pruebas automatizadas. Una captura de Wireshark documenta los intercambios
remotos completos. Estas evidencias verifican el comportamiento observado,
sin sustituir la demostración personal ante el catedrático.

## 2. Caso de uso y alcance

El caso, aprobado por el catedrático según confirmación del estudiante, permite
consultar existencias y detectar productos que requieren reposición. Usa nueve
registros ficticios en `data/pharmacy_inventory.json`. No modifica inventario,
realiza ventas, interpreta síntomas ni recomienda tratamientos.

La función del LLM es interpretar la solicitud y redactar una respuesta con los
datos obtenidos. El anfitrión ejecuta las herramientas. Esta separación permite
mostrar de dónde provienen cantidades concretas como las 48 cajas de FAR-001.

## 3. Arquitectura e implementación

```text
Usuario -> CLI -> ChatbotCore -> Gemini API
                    |
                    +-> McpCoordinator -> cliente stdio -> Filesystem oficial
                    +-> McpCoordinator -> cliente stdio -> Git oficial
                    +-> McpCoordinator -> cliente stdio -> Farmacia local
                                       o cliente HTTPS -> Nginx -> Farmacia remota
```

`ConversationSession` conserva mensajes, llamadas de función, resultados y
respuestas solo en memoria. `McpCoordinator` descubre herramientas, expone sus
esquemas a Gemini con prefijos por servidor y traduce sus llamadas a JSON-RPC.
El log registra solicitudes y respuestas reales con servidor, transporte,
método e ID; `/mcp-log` permite consultarlo en la consola.

Los clientes `stdio_client.py` y `http_client.py`, el dispatcher `server_core.py`
y ambos transportes se implementaron directamente con JSON y la biblioteca
estándar de Python. No se utiliza un SDK MCP ni FastMCP en el código propio.
El SDK de Google se utiliza solo para la API del LLM. Los servidores oficiales
son procesos externos instalados mediante npx y uvx.

Las consultas locales y remotas comparten `InventoryService` y
`PharmacyMcpServer`; una prueba compara sus resultados. El directorio
`demo_workspace/git_demo` está aislado del repositorio principal. El anfitrión
lo inicializa y el chatbot usa las herramientas oficiales para escribir,
agregar archivos, confirmar cambios y consultar el historial.

## 4. Especificación del servidor desarrollado

| Propiedad | Especificación |
| --- | --- |
| Identidad | pharmacy-inventory, versión 0.2.0 |
| Protocolo | JSON-RPC 2.0; MCP 2025-11-25 |
| Capacidad anunciada | tools, listChanged=false |
| Endpoint local | `python -m src.custom_mcp.stdio_server`, stdin/stdout UTF-8 |
| Endpoint remoto | `https://mcp.canchonfc.online/mcp` |
| Métodos HTTP | POST: mensajes; DELETE: cierre; GET: 405 para SSE opcional |
| Salud | GET `/healthz`, HTTP 200 |
| Acceso remoto | HTTPS y token Bearer privado |
| Sesión remota | MCP-Session-Id, 30 minutos de inactividad, máximo 128 |

| Herramienta | Parámetros | Resultado |
| --- | --- | --- |
| get_medication_stock | sku: string obligatorio | Producto con sku, name, stock y unit |
| search_medications | query: string obligatorio | Objeto items con coincidencias en nombre o SKU |
| list_low_stock | threshold: entero >=0, opcional, predeterminado 10 | Objeto items con stock <= threshold |

Los argumentos adicionales se rechazan. Las búsquedas y SKU ignoran mayúsculas;
se eliminan espacios externos. Los resultados incluyen un bloque de texto JSON,
`structuredContent` equivalente e `isError`. Un SKU desconocido produce
`isError:true`; una herramienta desconocida produce error JSON-RPC -32602.
También se validan JSON estricto, IDs, inicialización, parámetros y tamaño.

El cliente envía `initialize`, recibe versión/capacidades, emite
`notifications/initialized`, descubre con `tools/list` y llama con `tools/call`.
Las notificaciones no tienen ID. Las respuestas repiten el ID de su solicitud.
La especificación completa con ejemplos reproducibles está en
`docs/pharmacy-mcp.md`; HTTP, cabeceras, estados y operación en
`docs/deployment.md`. Referencias normativas:
[MCP 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25),
[JSON-RPC 2.0](https://www.jsonrpc.org/specification).

## 5. Despliegue sin afectar servicios existentes

Se inspeccionaron los puertos, contenedores, redes, volúmenes y Nginx del host.
Se creó exclusivamente el proyecto Compose `pharmacy-mcp` bajo
`/home/gil/pharmacy-mcp`, con su propia red y sin volúmenes compartidos.
Nginx recibe HTTPS y reenvía hacia `127.0.0.1:8091`; el contenedor escucha en
8000. No se expone directamente ese puerto en Internet.

El contenedor ejecuta Gunicorn con un worker y cuatro hilos. Tiene límite de
256 MiB y 0.5 CPU, usuario sin privilegios, filesystem de solo lectura y
directorio temporal limitado. El certificado de Let's Encrypt corresponde
únicamente al subdominio nuevo. Su renovación tiene una tarea programada y un
hook de recarga de Nginx. La clave de Gemini permanece en el cliente.

Después del despliegue, frontend, backend, PostgreSQL y Lavalink conservaron sus
identificadores y tiempos de actividad. El bot permaneció activo y el portal
existente respondió HTTP 200. El contenedor nuevo se observó saludable y consumió
aproximadamente 33.75 MiB en una medición en reposo; no es una prueba de carga.

## 6. Verificación funcional

| Comprobación | Evidencia observada |
| --- | --- |
| Suite automatizada | 27 pruebas aprobadas; stdio, HTTP y modelo simulado |
| API y contexto reales | Respuesta sobre Alan Turing y fecha de nacimiento en el siguiente turno |
| Stock remoto | FAR-001 devuelve 48 cajas |
| Búsqueda remota | FAR-004: 6 botellas; FAR-005: 12 botellas |
| Existencias bajas | FAR-002, FAR-004, FAR-006 y FAR-008 con umbral 10 |
| Contexto sobre resultados | Identifica FAR-004 como vitamina con stock <=10 |
| Error de negocio | FAR-999 no existe; el chatbot lo comunica |
| MCP oficiales | Filesystem escribe README; Git agrega, confirma y muestra el commit |
| Captura | 181 paquetes, 13 mensajes JSON-RPC, 8 conexiones TCP |

El commit de la demostración aislada fue
`1c2cbf5d0ee49f00fa4ded2e049118be4b9416ea`. El diálogo exacto está en
`docs/evidence/live-demo.json`; los 31 mensajes MCP de los tres servidores en
`docs/evidence/mcp-exchanges.json`. Los metadatos de los paquetes y los cuerpos
descifrados seleccionados están en `docs/evidence/`. Los archivos originales de
captura y claves TLS se conservan localmente fuera de Git.

## 7. Análisis por capas

El anexo de red contiene la tabla de todos los intercambios y su reproducción.
En enlace se observan tramas Ethernet II de la LAN; en red, IPv4 entre
192.168.1.152 y 46.225.13.27; en transporte, conexiones TCP a 443; por encima,
TLS 1.3 protege HTTP/1.1 con JSON-RPC/MCP. Las direcciones MAC son del enlace
local y el TTL no demuestra por sí solo una ruta completa.

Se identificaron la sincronización (frames 14/18 y 37/41), el descubrimiento
(60/65), tres llamadas correctas (83/87, 105/109, 128/132), un error de inventario
(151/156) y el cierre HTTP (172/176). HTTP 202 confirma una notificación sin
introducir una respuesta JSON-RPC. HTTP 200 puede transportar `isError:true`:
el éxito del transporte no equivale al éxito de la operación de inventario.

## 8. Dificultades, límites y lecciones

La implementación manual exigió separar validación JSON-RPC, secuencia MCP y
errores de herramientas. Compartir el dispatcher evitó diferencias entre local
y remoto. Las pruebas reales sobre sockets y procesos detectan problemas que
una prueba de funciones aisladas no cubre.

El tiempo de espera inicial de 15 segundos para el LLM fue insuficiente en una
demostración anterior; se ajustó a 60 segundos con un reintento breve para
fallos transitorios. El programa comunica errores de disponibilidad y cuota;
las pruebas automatizadas no garantizan disponibilidad futura de Gemini.

HTTPS impedía leer JSON directamente desde los paquetes. Exportar secretos TLS
solo del cliente de farmacia permitió analizar la sesión sin registrar la clave
de Gemini. Después se rotó el token de servicio y se verificó el rechazo del
anterior. El log de aplicación facilita depurar llamadas; la captura aporta
evidencia independiente de TCP, TLS y HTTP.

El despliegue en un host compartido requirió reservar un puerto y un virtual
host propios, validar Nginx antes de recargar y comprobar los servicios previos.
No se realizaron reinicios generales de Docker ni migraciones de contenedores.

Límites: inventario estático, contexto no persistente, un worker para sesiones
en memoria, autenticación estática sin OAuth, sin SSE persistente y sin interfaz
gráfica opcional. Reutilizar conexiones, añadir almacenamiento transaccional y
autorización por usuario serían ampliaciones futuras, fuera del alcance probado.

## 9. Conclusiones

La misma interfaz MCP permitió consultar el inventario local y remoto sin
cambiar las herramientas expuestas al modelo. Separar anfitrión, cliente,
transporte y lógica de negocio fue esencial para conservar ese comportamiento.

Los resultados verificables provienen del servidor y quedan vinculados mediante
IDs a sus solicitudes. El seguimiento conversacional pudo utilizar esos datos
en turnos posteriores. La captura confirmó el ciclo de vida y mostró que una
sesión MCP puede abarcar varias conexiones TCP.

El proyecto demuestra integración funcional y una metodología reproducible:
pruebas automáticas, ejecución con API real, captura y análisis por capas. La
evidencia respalda esta ejecución concreta; no representa una certificación de
rendimiento, disponibilidad continua ni conformidad con todas las capacidades
opcionales del protocolo.

## 10. Preparación de la entrega

El README en inglés documenta instalación y uso. Se incluye guía de presentación
y demostración en `docs/presentation.md`. Antes de la entrega académica se debe
confirmar que GitHub está privado, conceder acceso a docentes/auxiliares y
completar los datos de identificación exigidos por el curso. La exposición debe
realizarla el estudiante. La interfaz gráfica corresponde a un extra opcional.
