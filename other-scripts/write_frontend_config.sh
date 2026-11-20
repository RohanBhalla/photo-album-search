#!/usr/bin/env bash
# Write front-end/config.js from the API_KEY in .env (or from $API_KEY if already set).
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
if [ -z "${API_KEY:-}" ] && [ -f "$root/.env" ]; then
  API_KEY="$(grep '^API_KEY=' "$root/.env" | cut -d= -f2-)"
fi
: "${API_KEY:?API_KEY is not set}"
printf 'window.APP_CONFIG = {\n  apiKey: "%s"\n};\n' "$API_KEY" > "$root/front-end/config.js"
echo "wrote front-end/config.js"
