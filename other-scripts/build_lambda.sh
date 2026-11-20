#!/usr/bin/env bash
# Build a deployable zip for one Lambda: its code plus its pip dependencies.
# Usage: other-scripts/build_lambda.sh index-photos   -> build/index-photos.zip
# boto3 is already in the Lambda runtime, so it is not bundled.
set -euo pipefail
name="$1"
root="$(cd "$(dirname "$0")/.." && pwd)"
src="$root/lambda-functions/$name"
out="$root/build/$name"
rm -rf "$out" "$out.zip" && mkdir -p "$out"
if [ -s "$src/requirements.txt" ]; then
  python3 -m pip install -q -r "$src/requirements.txt" -t "$out" \
    --platform manylinux2014_aarch64 --python-version 3.13 --only-binary=:all: --upgrade
fi
cp "$src"/*.py "$out"/
(cd "$out" && zip -qr "$out.zip" . -x '*__pycache__*')
echo "$out.zip"
