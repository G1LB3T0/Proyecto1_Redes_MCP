# Remote deployment and HTTP specification

The pharmacy service runs at `https://mcp.canchonfc.online/mcp` on an Ubuntu
Hetzner server. The stdio and HTTP transports share `PharmacyMcpServer` and
`InventoryService`; tool definitions, validation and results are identical.
The [tool specification](pharmacy-mcp.md) applies to both transports.

## Client configuration

Set these values in your local, untracked `.env`:

```dotenv
PHARMACY_MCP_TRANSPORT=http
PHARMACY_MCP_URL=https://mcp.canchonfc.online/mcp
PHARMACY_MCP_TOKEN=<token supplied privately by the server administrator>
```

Run `python -m src.mcp.pharmacy_demo` for protocol checks, or `python -m src.cli`
for the chatbot. Use `PHARMACY_MCP_TRANSPORT=stdio` to switch back to the local
server. The Filesystem and Git servers always remain local.

## HTTP interface

| Endpoint / method | Purpose | Response |
| --- | --- | --- |
| `POST /mcp` | One JSON-RPC request or notification | JSON response, or empty 202 for a notification |
| `DELETE /mcp` | End the current MCP session | Empty 204 |
| `GET /mcp` | Optional server event stream is not implemented | 405 with `Allow: POST, DELETE`, after authentication |
| `GET /healthz` | Public readiness check | 200 `{"status":"ok"}` |
| Other paths | No public application route | 404 |

Every `/mcp` request requires `Authorization: Bearer <token>`. POST also requires
`Content-Type: application/json` and `Accept: application/json, text/event-stream`.
The client sends `MCP-Protocol-Version: 2025-11-25`. Initialization returns
`MCP-Session-Id`; subsequent requests, notifications and DELETE carry that ID.
Initialization and tool JSON bodies are documented in the tool specification.

HTTP errors: 400 for invalid versions, envelopes or missing initialization;
401 for missing/incorrect credentials; 403 for an unapproved Origin; 404 for an
expired/unknown session; 406 for unsupported Accept; 411 for missing length;
413 for bodies over 64 KiB; 415 for non-JSON bodies; 503 when 128 sessions are
active. Nginx can also reject oversized bodies before they reach the application.
JSON-RPC errors and inventory errors retain the formats of the local server.

Sessions expire after 30 minutes of inactivity. The client restores an expired
session once after a 404, then retries the read-only operation. DELETE releases
session state. Requests are limited to 64 KiB and client responses to 1 MiB.
The inventory is read-only. The server validates any supplied Origin against
`https://mcp.canchonfc.online`; native clients may omit Origin.

This is the JSON-response profile of MCP Streamable HTTP, with a private static
bearer credential for this course deployment. It does not implement OAuth
discovery/authorization, a browser UI, resumable SSE, server-initiated requests,
resources or prompts. It is not a general public multi-user MCP hosting service.
TLS verification is enabled; remote plain HTTP and redirects are rejected by
the client. No Gemini key is needed or installed on the server.

## Isolated service layout

```text
/home/gil/pharmacy-mcp/
  src/                       manual server and shared inventory logic
  data/pharmacy_inventory.json
  deploy/compose.yaml         project: pharmacy-mcp
  deploy/Dockerfile
  deploy/runtime.env          MCP_AUTH_TOKEN only; chmod 600

Internet HTTPS :443 -> host Nginx -> 127.0.0.1:8091 -> container :8000
```

Only one Gunicorn worker is used because session state lives in process memory.
Four threads handle concurrent connections. Restarting the service invalidates
sessions; clients reinitialize automatically. Docker enforces a 256 MiB memory
limit, 0.5 CPU and 64 processes. The container runs as UID 10001, with a read-only
root filesystem, a 16 MiB temporary directory and all Linux capabilities dropped.
Its network is separate from the existing services and it shares no volumes.

The host's existing frontend, backend, PostgreSQL, Lavalink and bot service are
independent. In particular, do not run Compose from their old configuration
paths or change their networks/volumes to deploy this service.

## Installation on the configured host

Transfer only `src/`, `data/`, `deploy/` and `.dockerignore` to the dedicated
directory using SSH. Exclude `.env`, `.venv`, `.git`, logs and captures. Create
`deploy/runtime.env` privately with a cryptographically random `MCP_AUTH_TOKEN`;
configure the same value in the local client's `.env`.

```bash
cd /home/gil/pharmacy-mcp
chmod 600 deploy/runtime.env
docker compose -f deploy/compose.yaml config --quiet
docker compose -f deploy/compose.yaml up -d --build
curl --fail http://127.0.0.1:8091/healthz
```

Use `config --quiet`: printing the expanded Compose configuration would reveal
the token. `.dockerignore` excludes environment files from the build context.

Create a dedicated Nginx HTTP virtual host from `deploy/nginx-http.conf`, with
ACME webroot `/var/www/pharmacy-mcp-acme`. Validate using `sudo nginx -t`, then
reload Nginx. Obtain the certificate using the existing Certbot account:

```bash
sudo certbot certonly --webroot -w /var/www/pharmacy-mcp-acme \
  -d mcp.canchonfc.online --cert-name mcp.canchonfc.online --non-interactive
```

Add `deploy/nginx-https.conf` as a second, dedicated virtual host and validate
before reloading. Install `deploy/renew-nginx.sh` as an executable Certbot deploy
hook under `/etc/letsencrypt/renewal-hooks/deploy/`. It reloads Nginx only for this
certificate. Ports 80 and 443 are already permitted; port 8091 stays on loopback.

## Operations and rollback

```bash
cd /home/gil/pharmacy-mcp
docker compose -f deploy/compose.yaml ps
docker compose -f deploy/compose.yaml logs --tail 50
curl --fail https://mcp.canchonfc.online/healthz
```

For a code update, transfer the changed source, rebuild and recreate only this
project. For token rotation, update its `runtime.env` and the client's `.env`,
then run `docker compose -f deploy/compose.yaml up -d --force-recreate pharmacy`.
Existing sessions terminate and reinitialize with the new credential.

To roll back, stop only `pharmacy-mcp` using its explicit Compose file. Disable
only the two `pharmacy-mcp` Nginx symlinks, validate and reload Nginx. Do not prune
Docker resources, restart Docker, or stop the existing application containers.

## References

- [MCP Streamable HTTP specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
- [Docker Compose service configuration](https://docs.docker.com/reference/compose-file/services/)
- [Nginx proxy module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)
