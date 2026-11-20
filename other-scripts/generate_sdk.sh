#!/usr/bin/env bash
# Regenerate the API Gateway JavaScript SDK (SDK1) into front-end/sdk/.
# Run after changing other-scripts/infra/api.yaml and redeploying the v1 stage.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
api_id="${1:-4hknp7oxn6}"
tmp="$(mktemp -d)"
aws apigateway get-sdk --profile cc-hw1 --region us-east-1 \
  --rest-api-id "$api_id" --stage-name v1 --sdk-type javascript "$tmp/sdk.zip" >/dev/null
unzip -q "$tmp/sdk.zip" -d "$tmp"
rm -rf "$root/front-end/sdk" && mv "$tmp/apiGateway-js-sdk" "$root/front-end/sdk"
rm -rf "$tmp"
echo "SDK written to front-end/sdk/"
