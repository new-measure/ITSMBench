#!/usr/bin/env bash
set -euo pipefail

request() {
  local method="$1" host="$2" path="$3" body="${4:-}"
  local url
  local args=(-fsS -X "$method" -H "Host: $host")
  if [[ -n "$body" ]]; then args+=(-H "Content-Type: application/json" -d "$body"); fi
  if [[ -n "${MOCK_ADDR:-}" ]]; then url="http://${MOCK_ADDR}${path}"; else url="http://${host}:8080${path}"; fi
  curl "${args[@]}" "$url"
}

SP=sharepoint.local.mock
PERMS() { echo "/v1.0/sites/$1/permissions"; }

revoke() {
  local sid="$1" pid="$2"
  local permid
  permid=$(request GET "$SP" "$(PERMS "$sid")?\$top=999" \
    | jq -r --arg pid "$pid" '.value[] | select(.principalId==$pid) | .id' | head -n1)
  if [[ -n "$permid" && "$permid" != "null" ]]; then
    request DELETE "$SP" "$(PERMS "$sid")/$permid" >/dev/null
  fi
}

revoke site-9f2a1c4e7b3d6a08 group-all-staff
revoke site-9f2a1c4e7b3d6a08 group-contractors-ext
revoke site-3c8e5f0a1d9b7c24 user-mallory-kade
revoke site-3c8e5f0a1d9b7c24 group-all-staff
revoke site-7d1b9e2f4a6c8017 group-all-staff
revoke site-7d1b9e2f4a6c8017 user-mallory-kade
revoke site-2e6a8c0f5b3d9174 user-mallory-kade

restore() {
  local sid="$1" pid="$2"
  local permid
  permid=$(request GET "$SP" "$(PERMS "$sid")?\$top=999" \
    | jq -r --arg pid "$pid" '.value[] | select(.principalId==$pid) | .id' | head -n1)
  if [[ -n "$permid" && "$permid" != "null" ]]; then
    request PATCH "$SP" "$(PERMS "$sid")/$permid" '{"status":"ACTIVE"}' >/dev/null
  fi
}

restore site-5b3d7f1a9c2e4068 group-engineering
restore site-5b3d7f1a9c2e4068 person-df4e05d0c64d03a1
restore site-8a4c2e6f0b1d3957 group-operations
restore site-1d9f3b5a7c0e2846 group-sales-mktg
restore site-6c0e4a8f2b9d1735 group-people-hr
restore site-4f8b2d6a0c3e9157 group-itsupport
restore site-0a5c9e3f7b1d4268 group-all-staff

echo "[solve] task-b2: cut off 7 rogue grants on 4 sensitive sites; restored 7 wrongly-suspended legit grants on 6 bystander sites"
