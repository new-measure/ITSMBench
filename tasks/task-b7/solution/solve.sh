#!/usr/bin/env bash
set -euo pipefail

request() {
  local method="$1" host="$2" path="$3" url
  local args=(-fsS -X "$method" -H "Host: $host")
  if [[ $# -ge 4 ]]; then args+=(-H "Content-Type: application/json" -d "$4"); fi
  if [[ -n "${MOCK_ADDR:-}" ]]; then url="http://${MOCK_ADDR}${path}"; else url="http://${host}:8080${path}"; fi
  curl "${args[@]}" "$url"
}

MERCURY=mercury.local.mock

freeze()   { request POST "$MERCURY" "/api/v1/card/$1/freeze"   >/dev/null; }
unfreeze() { request POST "$MERCURY" "/api/v1/card/$1/unfreeze" >/dev/null; }

for ID in \
  card-b7fz000000000001 card-b7fz000000000002 card-b7fz000000000003 \
  card-b7fz000000000004 card-b7fz000000000005 \
  card-b7rg000000000001 ; do
  freeze "$ID"
done

request PATCH "$MERCURY" "/api/v1/recipient/recipient-b7mule00000000001" '{"status":"deleted"}' >/dev/null

for ID in \
  card-b7uf000000000001 card-b7uf000000000002 card-b7uf000000000003 \
  card-b7uf000000000004 card-b7uf000000000005 card-b7uf000000000006 \
  card-b7uf000000000007 ; do
  unfreeze "$ID"
done

echo "[solve] task-b7: 6 confirmed-fraudulent cards cut (frozen), mule recipient removed (deleted); 7 wrongly-frozen clean cards restored (active)"
