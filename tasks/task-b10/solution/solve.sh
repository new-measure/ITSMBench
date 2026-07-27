#!/usr/bin/env bash
set -euo pipefail

request() {
  local method="$1" host="$2" path="$3" body="${4:-}" url
  local args=(-fsS -X "$method" -H "Host: $host")
  if [[ -n "$body" ]]; then args+=(-H "Content-Type: application/json" -d "$body"); fi
  if [[ -n "${MOCK_ADDR:-}" ]]; then url="http://${MOCK_ADDR}${path}"; else url="http://${host}:8080${path}"; fi
  curl "${args[@]}" "$url"
}

VANTA=vanta.local.mock

set_status() { request POST "$VANTA" "/v1/vendors/$1/set-status" "{\"status\":\"$2\"}" >/dev/null; }

for ID in \
  vendor-b10f0001 vendor-b10f0002 \
  vendor-b10a0001 vendor-b10a0002 vendor-b10a0003 \
  vendor-b10a0004 vendor-b10a0005 ; do
  set_status "$ID" ARCHIVED
done

for ID in \
  vendor-b10d0001 vendor-b10d0002 vendor-b10d0003 \
  vendor-b10d0004 vendor-b10d0005 vendor-b10d0006 \
  vendor-b10d0007 ; do
  set_status "$ID" MANAGED
done

echo "[solve] task-b10: 7 confirmed-compromised vendors cut off (ARCHIVED); 7 wrongly-archived clean vendors restored (MANAGED)"
