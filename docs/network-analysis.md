# Análisis de la comunicación remota

## Captura real y alcance

El 21 de septiembre de 2026 se ejecutó el chatbot con Gemini y farmacia remota.
Se capturó su tráfico con Dumpcap 4.6.8 y se analizó con TShark 4.6.8, componentes
de Wireshark. El archivo es `logs/captures/pharmacy-remote.pcapng`. El inicio del
primer paquete fue 06:51:04.809 UTC, equivalente a 00:51:04.809 en Guatemala.

| Dato medido | Resultado |
| --- | --- |
| Interfaz | Ethernet 3, cliente Windows |
| Filtro de captura | `host 46.225.13.27 and tcp port 443` |
| Paquetes capturados / descartados | 181 / 0, según Dumpcap |
| Tiempo entre primer y último paquete | 107.238 s |
| Ventana configurada de captura | 180 s; incluye tiempo sin tráfico |
| Conexiones TCP | 8 |
| Mensajes HTTP reconstruidos | 16: 8 solicitudes y 8 respuestas |
| Mensajes JSON-RPC | 13: 6 solicitudes, 6 respuestas y 1 notificación |
| Retransmisiones detectadas por TShark | 0 en esta muestra |
| TLS negociado | TLS 1.3; suite `TLS_AES_256_GCM_SHA384` |

SHA-256 del archivo original:

```text
54ee3f9f6a1358de3e0c288159b3500feb34f1aa6d882750c2a46f11107372b4
```

El filtro incluye únicamente el tráfico HTTPS hacia la IP de Hetzner. No captura
la API de Gemini, SSH, DNS ni stdio. Los MCP oficiales locales se comprueban en
`docs/evidence/mcp-exchanges.json`; stdio no produce paquetes de red.
La captura observa el tramo cliente-Nginx, no el tramo interno Nginx-contenedor.

El cliente exportó claves TLS únicamente desde su contexto SSL de farmacia
mediante `MCP_TLS_KEYLOG_FILE`. TShark reconstruyó los flujos TCP y descifró TLS
con ese archivo. Sin las claves se observa tráfico cifrado, no JSON en claro.
La opción de Wireshark utilizada es `tls.keylog_file`.
[Documentación de descifrado TLS](https://wiki.wireshark.org/TLS).

## Clasificación de todos los intercambios

Los números corresponden a los frames donde TShark presenta el mensaje HTTP
completo después de reconstruirlo. Un mensaje puede ocupar varios segmentos TCP;
por eso un frame HTTP no equivale a un único paquete original de aplicación.

| Frames cliente / servidor | ID JSON-RPC | Clasificación y operación | Resultado |
| --- | --- | --- | --- |
| 14 / 18 | 1 | Sincronización: `initialize` y respuesta | HTTP 200; versión 2025-11-25, capacidades y serverInfo |
| 37 / 41 | Sin ID | Sincronización: `notifications/initialized` | HTTP 202 vacío; no hay respuesta JSON-RPC |
| 60 / 65 | 2 | Solicitud y respuesta: `tools/list` | HTTP 200; tres herramientas |
| 83 / 87 | 3 | Solicitud y respuesta: `get_medication_stock`, FAR-001 | HTTP 200; 48 cajas; isError=false |
| 105 / 109 | 4 | Solicitud y respuesta: `search_medications`, vitamin | HTTP 200; FAR-004: 6, FAR-005: 12 |
| 128 / 132 | 5 | Solicitud y respuesta: `list_low_stock`, threshold=10 | HTTP 200; FAR-002, FAR-004, FAR-006 y FAR-008 |
| 151 / 156 | 6 | Solicitud y respuesta: `get_medication_stock`, FAR-999 | HTTP 200; isError=true, SKU inexistente |
| 172 / 176 | No aplica | Cierre de sesión mediante HTTP DELETE | HTTP 204 vacío; no es un mensaje JSON-RPC |

`initialize` también es una solicitud JSON-RPC con su respuesta; se clasifica
como sincronización por su función en el ciclo de vida. El ACK de TCP, el HTTP
202 y una respuesta JSON-RPC son mecanismos diferentes. La notificación no lleva
`id` y no tiene respuesta JSON-RPC, aunque HTTP confirme su recepción. Las seis
respuestas con ID coinciden con sus solicitudes. El error de inventario no es un
fallo de transporte: viaja con HTTP 200 y `result.isError=true`.

Ejemplo extraído del frame 83:

```json
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_medication_stock","arguments":{"sku":"FAR-001"}}}
```

La respuesta del frame 87 repite `id:3`, incluye `stock:48` en
`result.structuredContent` y `isError:false`. Los cuerpos completos están en
`docs/evidence/network-summary.json`, sin cabeceras de autorización ni claves.

## Capa de enlace

La interfaz presenta tramas Ethernet II con EtherType `0x0800`, que indica IPv4.
Las direcciones MAC corresponden al enlace local del cliente y su siguiente
salto; no identifican directamente la tarjeta de red del servidor en Alemania.
La captura desde Windows no muestra los enlaces de los routers intermedios.

Los frames 1 y 2 tienen 66 bytes y el frame 3 tiene 54 bytes. El frame 4 presenta
1581 bytes en la captura del host. Ese tamaño no permite deducir por sí solo la
MTU física: funciones de segmentación/agrupación de la interfaz pueden modificar
lo observado por una captura local. No se capturó ARP porque el filtro lo excluye.

## Capa de red

El frame 1 sale de `192.168.1.152` hacia `46.225.13.27`; el frame 2 regresa en
sentido inverso. El TTL observado es 128 en el envío y 50 en la respuesta. No
se conoce el TTL inicial remoto a partir de este punto de captura, por lo que
no se afirma un número exacto de saltos.

La dirección privada identifica al cliente en su LAN. El acceso a la IP pública
atraviesa la red del proveedor y, normalmente, traducción de direcciones; esta
captura anterior a esa traducción no permite reconstruir toda la ruta ni ver
la dirección pública asignada al cliente. La resolución DNS se comprobó aparte;
no se atribuye una consulta DNS a este archivo.

## Capa de transporte

La primera conexión usa el puerto efímero 65250 del cliente y el puerto 443 del
servidor. Los frames 1, 2 y 3 muestran SYN, SYN-ACK y ACK. Los números relativos
de secuencia pasan de 0 a 1 porque SYN consume una posición. El frame 4 transporta
1527 bytes TCP y el frame 5 los confirma con ACK relativo 1528.

TCP ofrece el flujo de bytes que permite reconstruir TLS y HTTP. La sesión MCP
se mantiene mediante `MCP-Session-Id`, no mediante una sola conexión TCP: urllib
abre aquí ocho conexiones, una por operación HTTP. Esto simplifica el cliente,
pero repite los establecimientos TCP/TLS. No se detectaron retransmisiones en
esta muestra; el resultado no garantiza ausencia de pérdidas en otras sesiones.

## TLS y capa de aplicación

El ServerHello del frame 6 y los otros siete flujos negocian versión `0x0304`
(TLS 1.3) y suite `0x1302` (AES-256-GCM/SHA-384). TLS autentica al servidor y
protege los bytes HTTP sobre TCP. El cliente verifica la cadena y el nombre del
certificado; el certificado privado del servidor no se copió al cliente.
[RFC 8446, TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446.html).

Sobre TLS se observa HTTP/1.1; los POST contienen JSON-RPC 2.0 y métodos MCP.
`initialize` negocia versión y capacidades, `tools/list` descubre esquemas,
`tools/call` consulta el inventario y el anfitrión entrega esos resultados al LLM.
El transporte local representa los mismos mensajes como líneas UTF-8 por stdio.

Entre solicitud HTTP completa y respuesta completa transcurren aproximadamente
157 a 165 ms en los intercambios registrados. Es una medición desde el cliente
que incluye red, proxy y aplicación; no es tiempo puro de ejecución del servidor.
Las pausas entre consultas también incluyen interacción con Gemini y otros
turnos. No deben interpretarse como latencia de una herramienta MCP.

## Reproducción y revisión en Wireshark

Desde la raíz del proyecto, con `.env` en modo HTTP, abre dos terminales. En la
primera enumera interfaces y selecciona la que corresponda a tu conexión:

```powershell
& 'C:/Program Files/Wireshark/dumpcap.exe' -D
New-Item -ItemType Directory -Force logs/captures
& 'C:/Program Files/Wireshark/dumpcap.exe' -i 1 `
  -f 'host 46.225.13.27 and tcp port 443' -a duration:180 `
  -w logs/captures/pharmacy-remote.pcapng
```

En la segunda, mientras la captura está activa:

```powershell
. ./.venv/Scripts/Activate.ps1
$env:MCP_TLS_KEYLOG_FILE = 'logs/captures/mcp-tls.keys'
python -m scripts.live_demo
Remove-Item Env:MCP_TLS_KEYLOG_FILE
```

Espera a que Dumpcap cierre el archivo antes del análisis. Si Gemini tarda más
de tres minutos, amplía la ventana; la captura debe incluir initialize y DELETE.
Conserva la evidencia original usando otro nombre para nuevas ejecuciones.

```powershell
python -m scripts.analyze_capture
```

Abre el `.pcapng` en Wireshark. En Edit > Preferences > Protocols > TLS, selecciona
`logs/captures/mcp-tls.keys` en `(Pre)-Master-Secret log filename`. Aplica `http`
para ver los 16 intercambios, `tcp.stream == 0` para la primera conexión o
`frame.number == 83 || frame.number == 87` para la consulta FAR-001. En Follow >
TLS Stream se puede revisar el contenido reconstruido. Los números cambiarán en
otra ejecución. [Manual de Dumpcap](https://www.wireshark.org/docs/man-pages/dumpcap.html),
[manual de TShark](https://www.wireshark.org/docs/man-pages/tshark.html).

Los originales y las claves permanecen fuera de Git. El token usado durante
esta captura fue revocado; se comprobó que es rechazado y que el nuevo funciona.
La evidencia publicada contiene solo metadatos seleccionados y cuerpos JSON-RPC.
Antes de compartir otra captura descifrada, cambia también su token de servicio.
