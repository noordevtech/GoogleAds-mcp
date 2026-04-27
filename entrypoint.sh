#!/bin/sh
set -e

# If a service account JSON blob was provided via env, materialize it to disk
# and point the auth manager at the resulting file.
if [ -n "$GOOGLE_ADS_SERVICE_ACCOUNT_JSON" ]; then
  printf "%s" "$GOOGLE_ADS_SERVICE_ACCOUNT_JSON" > /app/service_account.json
  export GOOGLE_ADS_SERVICE_ACCOUNT_PATH=/app/service_account.json
fi

exec mcp-proxy \
  --port 8000 \
  --host 0.0.0.0 \
  --allow-origin "*" \
  --pass-environment \
  -- python /app/run_server.py
