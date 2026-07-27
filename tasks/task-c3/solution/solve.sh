#!/usr/bin/env bash
set -euo pipefail

request() {
  local method="$1" host="$2" path="$3" url
  local args=(-fsS -X "$method" -H "Host: $host")
  if [[ -n "${MOCK_ADDR:-}" ]]; then url="http://${MOCK_ADDR}${path}"; else url="http://${host}:8080${path}"; fi
  curl "${args[@]}" "$url"
}

OKTA=okta.local.mock

suspend()   { request POST "$OKTA" "/api/v1/users/$1/lifecycle/suspend"   >/dev/null; }
unsuspend() { request POST "$OKTA" "/api/v1/users/$1/lifecycle/unsuspend" >/dev/null; }

for ID in \
  person-c30000000000f001 person-c30000000000f002 \
  person-c30000000000a001 person-c30000000000a002 person-c30000000000a003 \
  person-c30000000000a004 person-c30000000000a005 ; do
  suspend "$ID"
done

for ID in \
  person-c30000000000d001 person-c30000000000d002 person-c30000000000d003 \
  person-c30000000000d004 person-c30000000000d005 person-c30000000000d006 \
  person-c30000000000d007 ; do
  unsuspend "$ID"
done

echo "[solve] task-c3: 7 confirmed-compromised accounts locked down (SUSPENDED); 7 wrongly-suspended clean accounts restored (ACTIVE)"
