#!/usr/bin/env bash
set -euo pipefail

request() {
  local method="$1" host="$2" path="$3" body="${4:-}" url
  local args=(-fsS -X "$method" -H "Host: $host")
  if [[ -n "$body" ]]; then args+=(-H "Content-Type: application/json" -d "$body"); fi
  if [[ -n "${MOCK_ADDR:-}" ]]; then url="http://${MOCK_ADDR}${path}"; else url="http://${host}:8080${path}"; fi
  curl "${args[@]}" "$url"
}

INTUNE=microsoft-intune.local.mock
BASE_REF="http://microsoft-intune.local.mock:8080/v1.0/deviceManagement/deviceCategories"

set_category() {
  request PUT "$INTUNE" "/v1.0/deviceManagement/managedDevices/$1/deviceCategory/\$ref" \
    "{\"@odata.id\":\"${BASE_REF}/$2\"}" >/dev/null
}

for ID in \
  asset-a1b2c3d4e5f60001 asset-a1b2c3d4e5f60002 \
  asset-b1b2c3d4e5f60001 asset-b1b2c3d4e5f60002 asset-b1b2c3d4e5f60003 \
  asset-b1b2c3d4e5f60004 asset-b1b2c3d4e5f60005 asset-b1b2c3d4e5f60006 \
  asset-b1b2c3d4e5f60007 ; do
  set_category "$ID" category-quarantine
done

for ID in asset-d1b2c3d4e5f60001 asset-d1b2c3d4e5f60002 asset-d1b2c3d4e5f60003 ; do
  set_category "$ID" category-clinical
done
set_category asset-d1b2c3d4e5f60004 category-corporate
set_category asset-d1b2c3d4e5f60005 category-mobile
set_category asset-d1b2c3d4e5f60006 category-corporate
set_category asset-d1b2c3d4e5f60007 category-corporate
set_category asset-d1b2c3d4e5f60008 category-corporate

echo "[solve] task-b5: 9 compromised endpoints isolated into Security-Hold; 8 wrongly-quarantined clean devices restored to normal categories"
