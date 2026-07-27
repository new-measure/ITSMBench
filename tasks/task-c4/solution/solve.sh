#!/usr/bin/env bash
set -euo pipefail

request() {
  local method="$1" host="$2" path="$3" body="${4:-}" url
  local args=(-fsS -X "$method" -H "Host: $host")
  if [[ -n "$body" ]]; then args+=(-H "Content-Type: application/json" -d "$body"); fi
  if [[ -n "${MOCK_ADDR:-}" ]]; then url="http://${MOCK_ADDR}${path}"; else url="http://${host}:8080${path}"; fi
  curl "${args[@]}" "$url"
}

OKTA=okta.local.mock

deactivate_app() { request POST "$OKTA" "/api/v1/apps/$1/lifecycle/deactivate" >/dev/null; }
activate_app()   { request POST "$OKTA" "/api/v1/apps/$1/lifecycle/activate" >/dev/null; }
delete_app()     { request DELETE "$OKTA" "/api/v1/apps/$1" >/dev/null; }
revoke_token()   { request DELETE "$OKTA" "/api/v1/api-tokens/$1" >/dev/null; }

for ID in \
  0oac4rogue0000000001 0oac4rogue0000000002 \
  0oac4rogue0000000003 0oac4rogue0000000004 0oac4rogue0000000005 \
  0oac4rogue0000000006 0oac4rogue0000000007 0oac4rogue0000000008 ; do
  deactivate_app "$ID"
  delete_app "$ID" || true
done

revoke_token 00Tc4atkr0000000001

for ID in \
  0oac4legit0000000001 0oac4legit0000000002 0oac4legit0000000003 \
  0oac4legit0000000004 0oac4legit0000000005 0oac4legit0000000006 \
  0oac4legit0000000007 ; do
  activate_app "$ID"
done

echo "[solve] task-c4: 8 rogue OAuth apps neutralized + attacker API token revoked; 7 wrongly-disabled legit apps re-activated"
