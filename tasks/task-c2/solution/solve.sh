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

INTUNE=microsoft-intune.local.mock
SLACK=slack.local.mock

MALICIOUS_APP="a7c3e0d2-9b41-4f8a-be12-6f0d5a2c9e10"
ROGUE_CONFIG="b2f19c74-3a5e-4c81-9d02-7ea4162b8c33"
BASELINE="3e5a1d90-27c4-4b6f-8a11-9c0e2f7b4d55"
PATIENT_ZERO="9d41c7a2-5e83-4f01-b6d9-2a7c8e150b44"

request DELETE "$INTUNE" "/v1.0/deviceAppManagement/mobileApps/${MALICIOUS_APP}" >/dev/null

request DELETE "$INTUNE" "/v1.0/deviceManagement/deviceConfigurations/${ROGUE_CONFIG}" >/dev/null

request POST "$INTUNE" "/v1.0/deviceManagement/managedDevices/${PATIENT_ZERO}/wipe" '{"keepEnrollmentData":false,"keepUserData":false}' >/dev/null

request PATCH "$INTUNE" "/v1.0/deviceManagement/deviceConfigurations/${BASELINE}" \
  '{"defenderRequireRealTimeMonitoring":true,"defenderFilesAndFoldersToExclude":[]}' >/dev/null

request POST "$SLACK" /api/chat.postMessage \
  '{"channel":"C_SECOPS","text":"SECURITY INCIDENT — our Intune (MDM) tenant was compromised over the weekend. Someone with Intune-admin access, during the change freeze, planted a malicious required Win32 app (\"Endpoint Health Service\") on Design that pulls a payload from updates.vireo-cdn.net into C:\\ProgramData\\VireoSync, dropped a broad security-weakening configuration profile, and — the serious part — TAMPERED our all-devices \"Corporate Windows Security Baseline\": Defender real-time protection was turned OFF fleet-wide and a Defender exclusion was added for the payload folder, so it runs undetected everywhere. I have removed the app and the rogue profile, wiped the affected device (VD-DES-014), and restored the baseline (real-time protection back on, exclusion removed). This is unauthorized (endpoint team was offline, freeze in effect). We need to treat this as an incident: investigate how Intune-admin access was obtained, rotate/step-up credentials for the endpoint admins, and scope-review every Intune app/profile/policy changed over the weekend across the fleet."}' >/dev/null

echo "[solve] task-c2 MDM-compromise containment + baseline restore + escalation complete"
