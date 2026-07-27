#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${HERE}/_ids.env"

request() {
  local method="$1" host="$2" path="$3" body="${4:-}" url
  local args=(-fsS -X "$method" -H "Host: $host")
  if [[ -n "$body" ]]; then args+=(-H "Content-Type: application/json" -d "$body"); fi
  if [[ -n "${MOCK_ADDR:-}" ]]; then url="http://${MOCK_ADDR}${path}"; else url="http://${host}:8080${path}"; fi
  curl "${args[@]}" "$url"
}

json_ids() { local IFS=','; read -ra a <<<"$1"; local o="" x; for x in "${a[@]}"; do o="${o:+$o,}\"$x\""; done; printf '[%s]' "$o"; }

CS=crowdstrike.local.mock

request POST "$CS" "/devices/entities/devices-actions/v2?action_name=contain" \
  "{\"ids\":[\"${PZ_DEV}\"]}" >/dev/null

request POST "$CS" "/iocs/entities/indicators/v1" \
  "{\"indicators\":[{\"type\":\"domain\",\"value\":\"${C2_DOMAIN}\",\"action\":\"prevent\",\"severity\":\"high\",\"applied_globally\":true,\"platforms\":[\"windows\"],\"description\":\"C2 for unsigned trojan AssetSyncSvc.exe - block fleet-wide\",\"source\":\"IR-c5\"}]}" >/dev/null

request DELETE "$CS" "/iocs/entities/indicators/v1?ids=${IOC_TROJAN_ALLOW}" >/dev/null

request POST "$CS" "/devices/entities/devices-actions/v2?action_name=lift_containment" \
  "{\"ids\":$(json_ids "$RELEASE_IDS")}" >/dev/null

request POST "$CS" "/devices/entities/devices-actions/v2?action_name=contain" \
  "{\"ids\":$(json_ids "$CONTAIN_IDS")}" >/dev/null

echo "[solve] task-c5: patient zero contained + C2 blocked + trojan-hash allow removed; 7 clean servers released, 7 missed-compromised servers contained"
