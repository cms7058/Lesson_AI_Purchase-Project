#!/usr/bin/env sh
set -eu

BASE_URL="${BASE_URL:-http://127.0.0.1:8080}"
TMP_HOME="$(mktemp)"
TMP_API="$(mktemp)"
trap 'rm -f "$TMP_HOME" "$TMP_API"' EXIT

curl --fail --silent --show-error "$BASE_URL/" > "$TMP_HOME"
curl --fail --silent --show-error "$BASE_URL/api/v1/health" > "$TMP_API"
grep -q "AI助力" "$TMP_HOME"
grep -q '"status":"ok"' "$TMP_API"
curl --fail --silent --show-error "$BASE_URL/api/v1/ready" | grep -q '"status":"ready"'

echo "AI助力 deployment check passed: $BASE_URL"
