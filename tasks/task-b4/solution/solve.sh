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

CONF=confluence.local.mock
RA() { echo "/wiki/api/v2/spaces/$1/role-assignments"; }

strip() {
  local sid="$1"; shift
  local cur filtered
  cur=$(request GET "$CONF" "$(RA "$sid")?limit=250" | jq '.results // []')
  filtered=$(echo "$cur" | jq '[ .[] | select( ([.principalId] - $ARGS.positional) == [.principalId] ) ]' --args "$@")
  request POST "$CONF" "$(RA "$sid")" "$filtered" >/dev/null
}

strip space-44584a1bbbe66415 group-all-employees group-contractors-ext
strip space-3992f83ba808bca0 user-mallory-kade  group-all-employees
strip space-34cd7f70629cdb97 group-all-employees user-mallory-kade
strip space-a76d7296e7ebb334 user-mallory-kade

grant() {
  local sid="$1" pid="$2" ptype="$3" role="$4"
  local cur newra merged
  cur=$(request GET "$CONF" "$(RA "$sid")?limit=250" | jq '.results // []')
  newra=$(jq -n --arg pid "$pid" --arg pt "$ptype" --arg role "$role" \
    '{principal:{principalType:($pt|ascii_upcase), principalId:$pid}, roleId:("role-"+$role)}')
  merged=$(echo "$cur" | jq --argjson r "$newra" '. + [$r]')
  request POST "$CONF" "$(RA "$sid")" "$merged" >/dev/null
}

grant space-474b4f001f1a6ad8 group-engineering     group editor
grant space-474b4f001f1a6ad8 group-security        group viewer
grant space-0668e6cae43cc031 group-operations      group editor
grant space-ca69334611ae6981 group-sales-marketing group editor
grant space-63fb7aadd5abbd6b group-people          group editor
grant space-3b498129de11a15c group-it-support      group editor
grant space-53d41a7996b7e881 group-all-employees   group viewer

echo "[solve] task-b4: stripped 7 rogue grants from 4 sensitive spaces; restored 7 wrongly-revoked legit grants (correct roles) on 6 collateral spaces"
