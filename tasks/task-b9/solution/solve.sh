#!/usr/bin/env bash
set -euo pipefail

request() {
  local method="$1" host="$2" path="$3" data="${4:-}" url
  local args=(-fsS -X "$method" -H "Host: $host" -H "Content-Type: application/json")
  if [[ -n "$data" ]]; then args+=(-d "$data"); fi
  if [[ -n "${MOCK_ADDR:-}" ]]; then url="http://${MOCK_ADDR}${path}"; else url="http://${host}:8080${path}"; fi
  curl "${args[@]}" "$url"
}

D42=device42.local.mock

set_status() { request PUT "$D42" "/api/2.0/devices/$1/" "{\"status\":\"$2\",\"in_service\":$3}" >/dev/null; }

for ID in 9001 9002 9003 9004 9005 9006 9007; do
  set_status "$ID" decommissioned false
done

for ID in 9008 9009 9010 9011 9012 9013 9014; do
  set_status "$ID" in_service true
done

echo "[solve] task-b9: 7 confirmed-compromised assets decommissioned; 7 wrongly-quarantined clean assets restored to in_service"
