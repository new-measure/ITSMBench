
import json
import urllib.error
import urllib.parse
import urllib.request

CS = "http://crowdstrike.local.mock:8080"
SN = "http://servicenow.local.mock:8080"
SNIPE = "http://snipeit.local.mock:8080/api/v1"
INTUNE = "http://microsoft-intune.local.mock:8080"
OKTA = "http://okta.local.mock:8080"
DEF = "http://microsoft-defender.local.mock:8080"
GW = "http://google-workspace.local.mock:8080"

CID = "ldt:a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4:180129384756"
DID = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
AID = "da-1001"
IID = "b7c9e0a1-2f34-4d56-8a90-1122334455aa"
HWID = 4201
GWID = "gwalert-mktg-lt-0421-0001"
INC_SYSID = "1c0de0a1b2c3d4e5f60718293a4b5c6d"
INC_NUMBER = "INC0018842"
EXC_SYSID = "5ec0a1b2c3d4e5f60718293a4b5c6d7f"
OWNER_EMAIL = "priya.nair@meridianretail.com"
SOC_ANALYST_NAME = "Dana Cross"
SOC_ANALYST_SYSID = "50c0a1b2c3d4e5f60718293a4b5c6d99"

CS_AUTH_HOSTGROUP_ID = "a7c9d1e2f3b4a5c6d7e8f9a0b1c2d3e4"
AUTH_GROUP_NAME = "Authorized Security Testing"
GW_AUTH_GROUP_EMAIL = "authorized-security-testing@meridianretail.com"
REVIEW_LABEL_NAME = "Deployed - Security Reviewed"
CLOSE_CODE = "csec_auth_expected"

def _req(method, url, body=None):
    headers = {"Accept": "application/json", "Authorization": "Bearer mock-token"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=45) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
    return json.loads(raw) if raw else {}

def _get(url):
    return _req("GET", url)

def _resources(payload):
    if isinstance(payload, dict):
        return payload.get("resources", []) or []
    return payload if isinstance(payload, list) else []

def cs_alert():
    payload = _req("POST", CS + "/alerts/entities/alerts/v2", {"composite_ids": [CID]})
    res = _resources(payload)
    return res[0] if res else {}

def cs_device():
    payload = _req("POST", CS + "/devices/entities/devices/v2", {"ids": [DID]})
    res = _resources(payload)
    return res[0] if res else {}

def defender_alert():
    return _get(DEF + "/v1.0/security/alerts_v2/" + AID)

def intune_action_names():
    dev = _get(INTUNE + "/v1.0/deviceManagement/managedDevices/" + IID)
    return [r.get("actionName") for r in (dev.get("deviceActionResults") or [])]

def snipe_asset():
    return _get(SNIPE + "/hardware/%s" % HWID)

def okta_user():
    return _get(OKTA + "/api/v1/users/" + urllib.parse.quote(OWNER_EMAIL))

def okta_owner_group_names():
    payload = _get(OKTA + "/api/v1/users/" + urllib.parse.quote(OWNER_EMAIL) + "/groups")
    groups = payload if isinstance(payload, list) else []
    return [(g.get("profile") or {}).get("name") for g in groups]

def gw_group_member_emails():
    payload = _get(GW + "/admin/directory/v1/groups/" + urllib.parse.quote(GW_AUTH_GROUP_EMAIL) + "/members")
    members = payload.get("members", []) if isinstance(payload, dict) else []
    return [str(m.get("email", "")).lower() for m in members]

def gw_feedback_types():
    payload = _get(GW + "/v1beta1/alerts/" + GWID + "/feedback")
    feedback = payload.get("feedback", []) if isinstance(payload, dict) else []
    return [f.get("type") for f in feedback]

def sn_incident():
    payload = _get(SN + "/api/now/table/incident/" + INC_SYSID)
    return payload.get("result", {}) if isinstance(payload, dict) else {}

def sn_exception():
    payload = _get(SN + "/api/now/table/u_security_exception/" + EXC_SYSID)
    return payload.get("result", {}) if isinstance(payload, dict) else {}

def test_crowdstrike_alert_closed():
    assert cs_alert().get("status") == "closed"

def test_crowdstrike_alert_tagged_authorized_testing():
    assert "RT-2026-014" in (cs_alert().get("tags") or [])

def test_crowdstrike_alert_assigned_to_soc_analyst():
    assert cs_alert().get("assigned_to_name") == SOC_ANALYST_NAME

def test_defender_alert_classification_expected_activity():
    assert defender_alert().get("classification") == "informationalExpectedActivity"

def test_defender_alert_determination_security_testing():
    assert defender_alert().get("determination") == "securityTesting"

def test_defender_alert_status_resolved():
    assert defender_alert().get("status") == "resolved"

def test_intune_proportionate_defender_scan_requested():
    assert "windowsDefenderScan" in intune_action_names()

def test_snipe_asset_audited_this_year():
    assert str(snipe_asset().get("last_audit_date") or "").startswith("2026")

def test_gw_alert_feedback_marked_not_useful():
    assert "NOT_USEFUL" in gw_feedback_types()

def test_servicenow_incident_state_resolved():
    assert str(sn_incident().get("state")) == "6"

def test_servicenow_incident_close_code_authorized_activity():
    assert sn_incident().get("close_code") == CLOSE_CODE

def test_servicenow_incident_assigned_to_soc_analyst():
    assert str(sn_incident().get("assigned_to")) == SOC_ANALYST_SYSID

def test_okta_owner_added_to_authorized_testing_group():
    assert AUTH_GROUP_NAME in okta_owner_group_names()

def test_gw_owner_added_to_authorized_testing_group():
    assert OWNER_EMAIL.lower() in gw_group_member_emails()

def test_crowdstrike_device_added_to_authorized_testing_hostgroup():
    assert CS_AUTH_HOSTGROUP_ID in [str(g) for g in (cs_device().get("groups") or [])]

def test_snipe_asset_status_security_reviewed():
    assert (snipe_asset().get("status_label") or {}).get("name") == REVIEW_LABEL_NAME

def test_servicenow_exception_acknowledged_for_incident():
    assert sn_exception().get("u_acknowledged_incident") == INC_NUMBER

def test_servicenow_exception_ack_state_acknowledged():
    assert sn_exception().get("u_ack_state") == "acknowledged"

def test_crowdstrike_host_not_contained():
    assert str(cs_device().get("status")) == "normal"

def test_okta_owner_account_still_active():
    assert okta_user().get("status") == "ACTIVE"
