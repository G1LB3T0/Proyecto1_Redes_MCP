# Guía de presentación y demostración

Duración sugerida: 8 a 10 minutos. Ensayar con la clave de Gemini configurada y
el entorno virtual activo. No mostrar `.env`, cabeceras Authorization ni claves TLS.

## 1. Problema y caso de uso (1 minuto)

Una farmacia necesita consultar existencias y detectar productos que debe
reponer. El chatbot usa datos ficticios de nueve productos. Explicar la
aprobación del caso y el alcance de solo lectura.

## 2. Arquitectura (1 minuto)

Mostrar el diagrama del informe. Distinguir anfitrión, cliente y servidor.
Gemini propone llamadas; el anfitrión las ejecuta. Filesystem y Git son locales;
farmacia puede alternar entre stdio y HTTPS con las mismas herramientas.

## 3. Demostración funcional (3 minutos)

```powershell
. ./.venv/Scripts/Activate.ps1
python -m src.cli
```

1. Preguntar quién fue Alan Turing y luego cuándo nació, sin repetir el nombre.
2. Pedir FAR-001, búsqueda de vitamin y stock <=10. Esperar 48 cajas y las dos vitaminas.
3. Preguntar cuál de esas vitaminas tiene stock <=10. Esperar FAR-004, 6 botellas.
4. Consultar FAR-999 y explicar el error de negocio.
5. Pedir escribir README en `demo_workspace/git_demo`, agregarlo y hacer commit.
6. Usar `/mcp-log` para señalar una solicitud y su respuesta con el mismo ID.

`python -m scripts.live_demo` reproduce estas seis conversaciones y guarda su
transcripción. Una segunda ejecución modifica solo el repositorio de demostración.
Para comparar local/remoto sin Gemini, cambiar `PHARMACY_MCP_TRANSPORT` y ejecutar
`python -m src.mcp.pharmacy_demo` en cada modo.

## 4. Servidor remoto y Wireshark (2 minutos)

Mostrar `https://mcp.canchonfc.online/healthz` y la separación del contenedor.
Abrir la captura original, cargar las claves de su sesión según la guía de red
y aplicar `http`. Señalar frames 14/18 (initialize), 37/41 (notificación y HTTP
202), 83/87 (consulta/respuesta) y 151/156 (error de inventario). No abrir las
cabeceras de autorización en una proyección pública.

Explicar Ethernet -> IPv4 -> TCP -> TLS -> HTTP -> JSON-RPC/MCP. Usar frames 1-3
para el handshake TCP. Aclarar que el 202 no es una respuesta JSON-RPC y que
un error de inventario puede llegar mediante HTTP 200.

## 5. Dificultades y lecciones (1 minuto)

- Implementación manual: validación, IDs y orden de inicialización.
- Tiempo del LLM: timeout y tratamiento de fallos transitorios.
- TLS: exportación de claves de la sesión de farmacia para analizar JSON.
- Host compartido: servicio, red, puerto y virtual host independientes.
- Evidencia: distinguir prueba simulada, ejecución real y captura de paquetes.

## 6. Cierre y preguntas (1 minuto)

Presentar las 27 pruebas y el resultado de la captura. Explicar los límites:
inventario estático, contexto de sesión y autenticación privada sin OAuth.
Posibles preguntas: por qué un HTTP 200 contiene isError, diferencia entre
session ID e ID JSON-RPC, por qué existen ocho conexiones TCP y cómo se conserva
el comportamiento de las herramientas al cambiar el transporte.

Si la API está temporalmente indisponible, mostrar el error real, ejecutar la
prueba de farmacia sin Gemini y usar la transcripción y captura previas como
evidencia histórica claramente identificada. No presentarlas como una sesión en vivo.
