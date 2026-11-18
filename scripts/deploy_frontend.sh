#!/usr/bin/env bash
# Upload frontend/ to the website bucket (B1). HTML/JS/CSS are sent with no-cache
# so browsers pick up new versions right away. Used locally and by pipeline P2.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
bucket="${FRONTEND_BUCKET:-photo-album-search-frontend-088850687383}"
[ -f "$root/frontend/config.js" ] || { echo "frontend/config.js missing (run scripts/write_frontend_config.sh)"; exit 1; }
aws s3 sync "$root/frontend/" "s3://$bucket/" --delete --no-progress \
  --exclude ".DS_Store" --exclude "config.example.js" --exclude "sdk/README.md" --exclude "sdk/CHANGELOG.md" \
  --cache-control "no-cache"
echo "http://$bucket.s3-website-us-east-1.amazonaws.com"
