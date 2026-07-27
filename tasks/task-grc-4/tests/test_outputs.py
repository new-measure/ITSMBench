import json
import urllib.error
import urllib.request

ENTRA = "http://entra-id-governance.local.mock:8080/v1.0"
OKTA = "http://okta.local.mock:8080/api/v1"
SN = "http://servicenow.local.mock:8080/api/now/table"

INC_SYS = "92e75ccb30d901eed7797d352983da8c"

DEF_Q3 = "def-q3"
INST_ROLES = "inst-roles"

ROLE_DENY = {
    "00uROLEDENY0000001": "SUPER_ADMIN",
    "00uROLEDENY0000002": "ORG_ADMIN",
    "00uROLEDENY0000003": "APP_ADMIN",
    "00uROLEDENY0000004": "USER_ADMIN",
    "00uROLEDENY0000005": "REPORT_ADMIN",
    "00uROLEDENY0000006": "GROUP_MEMBERSHIP_ADMIN",
}
GROUP_DENY = {
    "00uGRPDENY0000001": "00gPRODDB000000001",
    "00uGRPDENY0000002": "00gPAYAPPR00000001",
    "00uGRPDENY0000003": "00gWIREOPS00000001",
    "00uGRPDENY0000004": "00gBREAKGLS0000001",
    "00uGRPDENY0000005": "00gLEDGER000000001",
}
APP_DENY = {
    "00uAPPDENY0000001": "0oaPAYCON000000001",
    "00uAPPDENY0000002": "0oaWIRE0000000001",
    "00uAPPDENY0000003": "0oaTREAS00000001",
    "00uAPPDENY0000004": "0oaADMPRT0000001",
    "00uAPPDENY0000005": "0oaLEDGEX0000001",
}
OVERGRANT_POLICIES = ["pol-fin", "pol-vend"]
BROAD_SCOPES = {"allMemberUsers", "allDirectoryUsers", "allExternalUsers",
                "allConfiguredConnectedOrganizationUsers", "allDirectoryServicePrincipals",
                "allDirectoryAgentIdentities"}

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode()
    return json.loads(raw) if raw and raw.strip()[:1] in "{[" else raw

def _user_role_types(uid):
    r = _get(OKTA + "/users/%s/roles" % uid)
    return {str(x.get("type")) for x in (r if isinstance(r, list) else [])}

def _group_member_ids(gid):
    r = _get(OKTA + "/groups/%s/users" % gid)
    return {str(u.get("id")) for u in (r if isinstance(r, list) else [])}

def _app_user_ids(aid):
    r = _get(OKTA + "/apps/%s/users" % aid)
    return {str(u.get("id")) for u in (r if isinstance(r, list) else [])}

def _policy(pid):
    return _get(ENTRA + "/identityGovernance/entitlementManagement/assignmentPolicies/%s" % pid)

def test_roles_review_instance_applied():
    inst = _get(ENTRA + "/identityGovernance/accessReviews/definitions/%s/instances/%s" % (DEF_Q3, INST_ROLES))
    assert str((inst or {}).get("status")) == "Completed"

def test_denied_role_1_revoked():
    assert "SUPER_ADMIN" not in _user_role_types("00uROLEDENY0000001")

def test_denied_role_2_revoked():
    assert "ORG_ADMIN" not in _user_role_types("00uROLEDENY0000002")

def test_denied_role_3_revoked():
    assert "APP_ADMIN" not in _user_role_types("00uROLEDENY0000003")

def test_denied_role_4_revoked():
    assert "USER_ADMIN" not in _user_role_types("00uROLEDENY0000004")

def test_denied_role_5_revoked():
    assert "REPORT_ADMIN" not in _user_role_types("00uROLEDENY0000005")

def test_denied_role_6_revoked():
    assert "GROUP_MEMBERSHIP_ADMIN" not in _user_role_types("00uROLEDENY0000006")

def test_denied_group_1_removed():
    assert "00uGRPDENY0000001" not in _group_member_ids("00gPRODDB000000001")

def test_denied_group_2_removed():
    assert "00uGRPDENY0000002" not in _group_member_ids("00gPAYAPPR00000001")

def test_denied_group_3_removed():
    assert "00uGRPDENY0000003" not in _group_member_ids("00gWIREOPS00000001")

def test_denied_group_4_removed():
    assert "00uGRPDENY0000004" not in _group_member_ids("00gBREAKGLS0000001")

def test_denied_group_5_removed():
    assert "00uGRPDENY0000005" not in _group_member_ids("00gLEDGER000000001")

def test_denied_app_1_removed():
    assert "00uAPPDENY0000001" not in _app_user_ids("0oaPAYCON000000001")

def test_denied_app_2_removed():
    assert "00uAPPDENY0000002" not in _app_user_ids("0oaWIRE0000000001")

def test_denied_app_3_removed():
    assert "00uAPPDENY0000003" not in _app_user_ids("0oaTREAS00000001")

def test_denied_app_4_removed():
    assert "00uAPPDENY0000004" not in _app_user_ids("0oaADMPRT0000001")

def test_denied_app_5_removed():
    assert "00uAPPDENY0000005" not in _app_user_ids("0oaLEDGEX0000001")

def test_overgrant_policy_fin_tightened():
    p = _policy("pol-fin")
    assert str((p or {}).get("allowedTargetScope")) not in BROAD_SCOPES

def test_overgrant_policy_vend_tightened():
    p = _policy("pol-vend")
    assert str((p or {}).get("allowedTargetScope")) not in BROAD_SCOPES

def test_ticket_closed():
    r = _get(SN + "/incident/" + INC_SYS)
    rec = (r or {}).get("result") if isinstance(r, dict) else None
    assert rec is not None
    s = str(rec.get("state")).lower()
    assert s in ("6", "7") or "clos" in s or "resolv" in s
