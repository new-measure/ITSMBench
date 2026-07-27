#!/usr/bin/env bash
set -euo pipefail

API=/services/data/v67.0

request() {
  local method="$1" host="$2" path="$3" body="${4:-}" url
  local args=(-fsS -X "$method" -H "Host: $host")
  [[ -n "$body" ]] && args+=(-H "Content-Type: application/json" -d "$body")
  if [[ -n "${MOCK_ADDR:-}" ]]; then url="http://${MOCK_ADDR}${path}"; else url="http://${host}:8080${path}"; fi
  curl "${args[@]}" "$url"
}

SF=salesforce.local.mock

deactivate() { request PATCH "$SF" "$API/sobjects/User/$1" '{"IsActive": false}' >/dev/null; }
reactivate() { request PATCH "$SF" "$API/sobjects/User/$1" '{"IsActive": true}'  >/dev/null; }

for ID in \
  005b11f00000000001 005b11f00000000002 \
  005b11a00000000001 005b11a00000000002 005b11a00000000003 \
  005b11a00000000004 005b11a00000000005 ; do
  deactivate "$ID"
done

request PATCH "$SF" "$API/sobjects/ConnectedApplication/0H4b11000000000001" '{"IsActive": false}' >/dev/null

for ID in \
  005b11d00000000001 005b11d00000000002 005b11d00000000003 \
  005b11d00000000004 005b11d00000000005 005b11d00000000006 \
  005b11d00000000007 ; do
  reactivate "$ID"
done

echo "[solve] task-b11: 7 confirmed-compromised accounts deactivated + rogue connected app revoked; 7 wrongly-frozen clean accounts restored (IsActive=true)"
