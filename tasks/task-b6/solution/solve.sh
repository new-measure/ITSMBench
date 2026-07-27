#!/usr/bin/env bash
set -euo pipefail

request() {
  local method="$1" host="$2" path="$3" data="${4:-}" url
  local args=(-fsS -X "$method" -H "Host: $host" -H "Content-Type: application/json")
  if [[ -n "$data" ]]; then args+=(--data "$data"); fi
  if [[ -n "${MOCK_ADDR:-}" ]]; then url="http://${MOCK_ADDR}${path}"; else url="http://${host}:8080${path}"; fi
  curl "${args[@]}" "$url"
}

JSM=jira-service-management.local.mock
ORG=702

remove_from_org() { request DELETE "$JSM" "/rest/servicedeskapi/organization/${ORG}/user" "{\"accountIds\":[\"$1\"]}" >/dev/null; }
add_to_org()      { request POST   "$JSM" "/rest/servicedeskapi/organization/${ORG}/user" "{\"accountIds\":[\"$1\"]}" >/dev/null; }

for ID in \
  account-b651d0000000000000f00001 account-b651d0000000000000f00002 \
  account-b651d0000000000000a00001 account-b651d0000000000000a00002 account-b651d0000000000000a00003 \
  account-b651d0000000000000a00004 account-b651d0000000000000a00005 ; do
  remove_from_org "$ID"
done

for ID in \
  account-b651d0000000000000d00001 account-b651d0000000000000d00002 account-b651d0000000000000d00003 \
  account-b651d0000000000000d00004 account-b651d0000000000000d00005 account-b651d0000000000000d00006 \
  account-b651d0000000000000d00007 ; do
  add_to_org "$ID"
done

echo "[solve] task-b6: cut privileged access for 7 confirmed-compromised agents (removed from org 702); restored 7 wrongly-revoked clean agents (added to org 702)"
