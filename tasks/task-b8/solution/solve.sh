#!/usr/bin/env bash
set -euo pipefail

HP=haproxy.local.mock

http_code() {
  local method="$1" prefix="$2" p="$3" body="${4:-}"
  local url args=(-s -o /dev/null -w '%{http_code}' -X "$method" -H "Host: $HP")
  [[ -n "$body" ]] && args+=(-H 'Content-Type: application/json' -d "$body")
  if [[ -n "${MOCK_ADDR:-}" ]]; then url="http://${MOCK_ADDR}${prefix}${p}"; else url="http://${HP}:8080${prefix}${p}"; fi
  curl "${args[@]}" "$url"
}

PREFIX="/v3"
code="$(http_code GET /v3 /services/haproxy/configuration/version || true)"
if [[ "$code" != 2* ]]; then
  code="$(http_code GET '' /services/haproxy/configuration/version || true)"
  [[ "$code" == 2* ]] && PREFIX=""
fi
echo "[solve] using HAProxy path prefix '${PREFIX}'"

req() {
  local method="$1" p="$2" body="${3:-}"
  local url args=(-fsS -X "$method" -H "Host: $HP")
  [[ -n "$body" ]] && args+=(-H 'Content-Type: application/json' -d "$body")
  if [[ -n "${MOCK_ADDR:-}" ]]; then url="http://${MOCK_ADDR}${PREFIX}${p}"; else url="http://${HP}:8080${PREFIX}${p}"; fi
  curl "${args[@]}" "$url"
}

MAINT='{"admin_state":"maint","operational_state":"down"}'
READY='{"admin_state":"ready","operational_state":"up"}'

take_out() {
  req PUT "/services/haproxy/runtime/backends/$1/servers/$2" "$MAINT" >/dev/null
}
remove_backend_server() {
  req PUT "/services/haproxy/runtime/backends/$1/servers/$2" "$MAINT" >/dev/null
  req DELETE "/services/haproxy/runtime/backends/$1/servers/$2" >/dev/null || true
  req DELETE "/services/haproxy/configuration/backends/$1/servers/$2" >/dev/null || true
}
return_up() {
  req PUT "/services/haproxy/runtime/backends/$1/servers/$2" "$READY" >/dev/null
}

remove_backend_server pool-storefront-web web-edge-cdn-x1
remove_backend_server pool-storefront-api api-edge-proxy-x1
remove_backend_server pool-storefront-cdn cdn-edge-origin-x9

take_out pool-storefront-web web-prod-03
take_out pool-storefront-web web-prod-07
take_out pool-storefront-web web-prod-12
take_out pool-storefront-api api-prod-04
take_out pool-storefront-api api-prod-09
take_out pool-storefront-cdn cdn-edge-05

return_up pool-storefront-web web-prod-02
return_up pool-storefront-web web-prod-05
return_up pool-storefront-web web-prod-09
return_up pool-storefront-api api-prod-02
return_up pool-storefront-api api-prod-06
return_up pool-storefront-api api-prod-11
return_up pool-storefront-cdn cdn-edge-03

echo "[solve] task-b8: 3 rogue + 6 compromised backends taken off the live path; 7 wrongly-flapped healthy nodes returned to ready"
