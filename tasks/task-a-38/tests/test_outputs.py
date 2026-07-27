import json
import urllib.error
import urllib.request

OKTA = "http://okta.local.mock:8080/api/v1"
GH = "http://github.local.mock:8080"
JC = "http://jumpcloud.local.mock:8080/api"
SNIPE = "http://snipeit.local.mock:8080/api/v1"
PD = "http://pagerduty.local.mock:8080"
JSM = "http://jira-service-management.local.mock:8080/rest/servicedeskapi"

ORG = "northwind-robotics"

import hashlib

def _h(*p):
    return hashlib.md5("|".join(str(x) for x in p).encode()).hexdigest()

def OUID(k):
    return "00u" + _h("okta-user", k)[:17]

def OGID(k):
    return "00g" + _h("okta-group", k)[:17]

def OAPP(k):
    return "0oa" + _h("okta-app", k)[:17]

def JCID(k):
    return _h("jumpcloud", k)[:24]

def PDID(k):
    return "P" + _h("pagerduty", k)[:6].upper()

MAYA, RAVI, ELENA, TOMAS, NADIA, SAM, DANA = (
    "maya-okonkwo", "ravi-balan", "elena-novak", "tomas-reyes", "nadia-farah",
    "sam-levine", "dana-kessler")

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    return json.loads(raw) if raw else None

def _as_list(obj, *keys):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in keys + ("value", "values", "result", "results", "data", "rows"):
            if k in obj and isinstance(obj[k], list):
                return obj[k]
    return []

def _okta_status(k):
    u = _get(OKTA + "/users/" + OUID(k))
    return None if u is None else u.get("status")

def _okta_cannot_auth(k):
    st = _okta_status(k)
    return st is None or st != "ACTIVE"

def _okta_group_user_ids(gk):
    return {str(u.get("id")) for u in _as_list(_get(OKTA + "/groups/%s/users?limit=200" % OGID(gk)))}

def _okta_app_user_ids(appk):
    return {str(u.get("id")) for u in _as_list(_get(OKTA + "/apps/%s/users?limit=200" % OAPP(appk)))}

def _gh_org_member_logins():
    return {str(m.get("login")) for m in _as_list(_get(GH + "/orgs/%s/members?per_page=100" % ORG))}

def _gh_is_org_member(user_login):
    return user_login in _gh_org_member_logins()

def _gh_repo_key_ids(repo):
    return {str(k.get("id")) for k in _as_list(_get(GH + "/repos/%s/%s/keys" % (ORG, repo)))}

def _jc_offboarded(k):
    u = _get(JC + "/systemusers/" + JCID(k))
    if u is None:
        return True
    return bool(u.get("suspended")) or str(u.get("state")) == "SUSPENDED" or bool(u.get("account_locked"))

def _snipe_assigned_id(asset_id):
    a = _get(SNIPE + "/hardware/%s" % asset_id)
    assigned = (a or {}).get("assigned_to")
    if not assigned:
        return None
    return str(assigned.get("id")) if isinstance(assigned, dict) else str(assigned)

def _pd_ep_targets(epk):
    ep = (_get(PD + "/escalation_policies/" + PDID(epk)) or {}).get("escalation_policy", {})
    out = []
    for rule in ep.get("escalation_rules", []) or []:
        for t in rule.get("targets", []) or []:
            out.append((str(t.get("type")), str(t.get("id"))))
    return out

def _pd_user_ids():
    return {str(u.get("id")) for u in _as_list(_get(PD + "/users"), "users")}

def test_maya_okta_deactivated():
    assert _okta_cannot_auth(MAYA)

def test_maya_removed_from_platform_group():
    assert OUID(MAYA) not in _okta_group_user_ids("g-platform")

def test_maya_github_membership_removed():
    assert not _gh_is_org_member(MAYA)

def test_maya_deploy_key_removed():
    assert "5001" not in _gh_repo_key_ids("payments-terraform")

def test_maya_edge_deploy_key_removed():
    assert "5003" not in _gh_repo_key_ids("edge-gateway")

def test_ravi_okta_deactivated():
    assert _okta_cannot_auth(RAVI)

def test_ravi_jumpcloud_offboarded():
    assert _jc_offboarded(RAVI)

def test_ravi_github_membership_removed():
    assert not _gh_is_org_member(RAVI)

def test_ravi_asset_no_longer_assigned():
    assert _snipe_assigned_id(106) != "504"

def test_elena_okta_deactivated():
    assert _okta_cannot_auth(ELENA)

def test_elena_removed_from_payments_group():
    assert OUID(ELENA) not in _okta_group_user_ids("g-payments")

def test_elena_github_membership_removed():
    assert not _gh_is_org_member(ELENA)

def test_elena_no_longer_oncall_target():
    assert ("user_reference", PDID(ELENA)) not in _pd_ep_targets("ep-payments")

def test_payments_policy_retains_active_target():
    targets = _pd_ep_targets("ep-payments")
    users = _pd_user_ids()
    assert any(kind == "user_reference" and tid != PDID(ELENA) and tid in users
               for kind, tid in targets)

def test_tomas_okta_deactivated():
    assert _okta_cannot_auth(TOMAS)

def test_tomas_github_membership_removed():
    assert not _gh_is_org_member(TOMAS)

def test_tomas_laptop_no_longer_assigned():
    assert _snipe_assigned_id(101) != "501"

def test_tomas_securitykey_no_longer_assigned():
    assert _snipe_assigned_id(102) != "501"

def test_nadia_okta_deactivated():
    assert _okta_cannot_auth(NADIA)

def test_nadia_removed_from_data_group():
    assert OUID(NADIA) not in _okta_group_user_ids("g-data")

def test_nadia_datadog_grant_removed():
    assert OUID(NADIA) not in _okta_app_user_ids("datadog")

def test_nadia_awsconsole_grant_removed():
    assert OUID(NADIA) not in _okta_app_user_ids("aws-console")

def test_sam_jumpcloud_offboarded():
    assert _jc_offboarded(SAM)

def test_dana_jumpcloud_offboarded():
    assert _jc_offboarded(DANA)

def test_dana_asset_no_longer_assigned():
    assert _snipe_assigned_id(107) != "505"

def test_ticket_closed():
    r = _get(JSM + "/request/HELP-4127")
    assert str((r or {}).get("currentStatus", {}).get("statusCategory")) == "COMPLETE"
