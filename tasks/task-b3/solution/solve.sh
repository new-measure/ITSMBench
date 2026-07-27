#!/usr/bin/env bash
set -euo pipefail

request() {
  local method="$1"
  local host="$2"
  local path="$3"
  local body="${4:-}"
  local url
  local args=(-fsS -X "$method" -H "Host: $host")

  if [[ -n "$body" ]]; then
    args+=(-H "Content-Type: application/json" -d "$body")
  fi

  if [[ -n "${MOCK_ADDR:-}" ]]; then
    url="http://${MOCK_ADDR}${path}"
  else
    url="http://${host}:8080${path}"
  fi

  curl "${args[@]}" "$url"
}

CS=crowdstrike.local.mock
OKTA=okta.local.mock

REPORTED_HOST="aa11bb22cc33dd44ee55ff6600000001"
FIN_APP_SVR="aa11bb22cc33dd44ee55ff6600000006"
FIN_RPT_SVR="aa11bb22cc33dd44ee55ff6600000007"
FP_ALERT="alert-f9e8d7c6b5a40312"
NADIA_OKTA_ID="person-a3f5c9d21e084b76"

request POST "$CS" "/devices/entities/devices-actions/v2?action_name=contain" \
  "{\"ids\":[\"${REPORTED_HOST}\"]}" >/dev/null

request POST "$CS" "/iocs/entities/indicators/v1" \
  '{"indicators":[{"type":"domain","value":"telemetry-sync-edge.net","action":"prevent","severity":"high","applied_globally":true,"platforms":["windows"],"description":"C2 for infostealer loader (invoice_remittance_mar) — block fleet-wide","source":"IR-b3"}]}' >/dev/null

request PATCH "$CS" "/alerts/entities/alerts/v3" \
  "{\"composite_ids\":[\"${FP_ALERT}\"],\"action_parameters\":[{\"name\":\"update_status\",\"value\":\"closed\"}]}" >/dev/null

request POST "$CS" "/devices/entities/devices-actions/v2?action_name=lift_containment" \
  "{\"ids\":[\"${FIN_APP_SVR}\"]}" >/dev/null
request POST "$CS" "/devices/entities/devices-actions/v2?action_name=lift_containment" \
  "{\"ids\":[\"${FIN_RPT_SVR}\"]}" >/dev/null

request POST "$OKTA" "/api/v1/users/${NADIA_OKTA_ID}/lifecycle/suspend" '{}' >/dev/null

echo "[solve] task-b3: host contained, C2 blocked (prevent), benign LSASS alert closed, two wrongly-contained finance servers released, compromised identity suspended"
