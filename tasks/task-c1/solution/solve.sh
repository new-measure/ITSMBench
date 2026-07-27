#!/usr/bin/env bash
set -euo pipefail

request() {
  local method="$1" host="$2" path="$3" body="${4:-}" url
  local args=(-fsS -X "$method" -H "Host: $host")
  if [[ -n "$body" ]]; then args+=(-H "Content-Type: application/json" -d "$body"); fi
  if [[ -n "${MOCK_ADDR:-}" ]]; then url="http://${MOCK_ADDR}${path}"; else url="http://${host}:8080${path}"; fi
  curl "${args[@]}" "$url"
}

ROGUE_APP_ID="0oabec7f3a9c21d0e8b"
ROGUE_TOKEN_ID="00Tbec4d1f8a06c93b2"
ROGUE_DELEGATE="mailbox-archive@acme.com"
ROGUE_FILTER_ID="filter-bec7a1c9e02d4f6b8"
HEADLINE="tendai.tembo@acme.com"

GROUP_C=(
  person-78509f53252644ac
  person-72d8a8ef8bb5a26c
  person-79d933804707ca6e
  person-1e52caa67f3c2917
  person-b8730d6964f60170
)

GROUP_A=(
  person-02d2d98b0f85b92d
  person-df4e05d0c64d03a1
  person-cd5066c6ec15632e
  person-778f642c90ff759a
  person-aacafca2ae53acaf
  person-9105060cfcda77e3
  person-d49213a2b2985640
  person-dadf64c7e54e7fda
)

for uid in "${GROUP_C[@]}"; do
  request POST okta.local.mock "/api/v1/users/${uid}/lifecycle/suspend" '{}' >/dev/null
done

request DELETE okta.local.mock "/api/v1/api-tokens/${ROGUE_TOKEN_ID}" >/dev/null
request POST okta.local.mock "/api/v1/apps/${ROGUE_APP_ID}/lifecycle/deactivate" '{}' >/dev/null

request DELETE gmail.local.mock \
  "/gmail/v1/users/${HEADLINE}/settings/delegates/${ROGUE_DELEGATE}" >/dev/null
request DELETE gmail.local.mock \
  "/gmail/v1/users/${HEADLINE}/settings/filters/${ROGUE_FILTER_ID}" >/dev/null

for uid in "${GROUP_A[@]}"; do
  request POST okta.local.mock "/api/v1/users/${uid}/lifecycle/unsuspend" '{}' >/dev/null
done

echo "[solve] task-c1 BEC lock-down + wrongful-lockout release complete"
