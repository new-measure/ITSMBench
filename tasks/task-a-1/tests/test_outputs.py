
import json
import urllib.parse
import urllib.request

SN = "http://servicenow.local.mock:8080"
OKTA = "http://okta.local.mock:8080"
GW = "http://google-workspace.local.mock:8080"
SLACK = "http://slack.local.mock:8080"

INCIDENT_SYS_ID = "caceb4cedced84b19db3515facf8425b"
LEGAL_GROUP_SYS_ID = "e6d6a3f8315bbe2b82ad2b370e90a07a"
DANA_EMAIL = "dana.whitfield@northwind.example"
OKTA_USER_ID = "00u179d64247d47094d8"
SLACK_USER_ID = "U42543D3ED"
HOLD_OU_PATH = "/Legal Hold"

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))

def _ref(value):
    if isinstance(value, dict):
        return value.get("value")
    return value

def _incident():
    return _get("%s/api/now/table/incident/%s" % (SN, INCIDENT_SYS_ID))["result"]

def _gw_user():
    key = urllib.parse.quote(DANA_EMAIL, safe="")
    return _get("%s/admin/directory/v1/users/%s" % (GW, key))

def _gw_token_client_ids():
    key = urllib.parse.quote(DANA_EMAIL, safe="")
    data = _get("%s/admin/directory/v1/users/%s/tokens" % (GW, key))
    items = data.get("items") or []
    return {str(t.get("clientId")) for t in items}

def _slack_user():
    return _get("%s/api/users.info?%s" % (SLACK, urllib.parse.urlencode({"user": SLACK_USER_ID})))["user"]

def _okta_user():
    return _get("%s/api/v1/users/%s" % (OKTA, OKTA_USER_ID))

def _okta_factor_types():
    factors = _get("%s/api/v1/users/%s/factors" % (OKTA, OKTA_USER_ID))
    return [str(f.get("factorType")) for f in factors]

def test_gw_account_suspended():
    assert _gw_user().get("suspended") is True

def test_gw_credential_reset_forced():
    assert _gw_user().get("changePasswordAtNextLogin") is True

def test_gw_moved_into_legal_hold_ou():
    assert _gw_user().get("orgUnitPath") == HOLD_OU_PATH

def test_gw_token_revoked_zoom():
    assert "zoom.us" not in _gw_token_client_ids()

def test_gw_token_revoked_dropbox():
    assert "dropbox.com" not in _gw_token_client_ids()

def test_gw_token_revoked_asana():
    assert "asana.com" not in _gw_token_client_ids()

def test_gw_token_revoked_slack_connector():
    assert "slack.com" not in _gw_token_client_ids()

def test_gw_token_revoked_calendly():
    assert "calendly.com" not in _gw_token_client_ids()

def test_gw_token_revoked_docusign():
    assert "docusign.net" not in _gw_token_client_ids()

def test_gw_token_revoked_grammarly():
    assert "grammarly.com" not in _gw_token_client_ids()

def test_gw_token_revoked_trello():
    assert "trello.com" not in _gw_token_client_ids()

def test_gw_token_revoked_zapier():
    assert "zapier.com" not in _gw_token_client_ids()

def test_gw_token_revoked_loom():
    assert "loom.com" not in _gw_token_client_ids()

def test_gw_token_revoked_notion():
    assert "notion.so" not in _gw_token_client_ids()

def test_slack_account_deactivated():
    assert _slack_user().get("deleted") is True

def test_sn_incident_routed_to_legal_hold_group():
    assert _ref(_incident().get("assignment_group")) == LEGAL_GROUP_SYS_ID

def test_sn_incident_escalation_reason_recorded():
    assert "litigation" in str(_incident().get("u_escalation_reason", "")).lower()

def test_sn_incident_put_on_hold():
    assert str(_incident().get("state")) == "3"

def test_okta_status_remains_suspended():
    assert str(_okta_user().get("status")) == "SUSPENDED"

def test_okta_mfa_factors_preserved():
    assert "sms" in _okta_factor_types()
