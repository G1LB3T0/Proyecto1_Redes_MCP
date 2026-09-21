#!/bin/sh
# Reload the proxy only when this service's certificate is renewed.
set -eu
if [ "${RENEWED_LINEAGE:-}" = /etc/letsencrypt/live/mcp.canchonfc.online ]; then
    nginx -t
    systemctl reload nginx
fi
