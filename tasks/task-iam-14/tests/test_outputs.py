import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request

OKTA = "http://okta.local.mock:8080/api/v1"
GH = "http://github.local.mock:8080"
SN = "http://servicenow.local.mock:8080/api/now/table"
ORG = "meridian-ledger"

def _h(*p):
    return hashlib.md5("|".join(str(x) for x in p).encode()).hexdigest()

def UID(k):
    return "00u" + _h("okta-user", k)[:17]

def GID(k):
    return "00g" + _h("okta-group", k)[:17]

def APPID(k):
    return "0oa" + _h("okta-app", k)[:17]

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
        for k in keys + ("result", "value", "values", "results", "data", "rows"):
            if isinstance(obj.get(k), list):
                return obj[k]
    return []

def _group_uids(gk):
    return {str(u.get("id")) for u in _as_list(_get(OKTA + "/groups/%s/users?limit=500" % GID(gk)))}

def _app_uids(ak):
    return {str(u.get("id")) for u in _as_list(_get(OKTA + "/apps/%s/users?limit=500" % APPID(ak)))}

def _okta_role_types(k):
    return {str(r.get("type")) for r in _as_list(_get(OKTA + "/users/%s/roles" % UID(k)))}

def _org_members():
    return {str(m.get("login")): str(m.get("role")) for m in _as_list(_get(GH + "/orgs/%s/members?per_page=100" % ORG))}

def _repo_collab_logins(repo):
    return {str(c.get("login")) for c in _as_list(_get(GH + "/repos/%s/%s/collaborators?per_page=100" % (ORG, repo)))}

def _repo_key_ids(repo):
    return {str(k.get("id")) for k in _as_list(_get(GH + "/repos/%s/%s/keys?per_page=100" % (ORG, repo)))}

def _recert_closed():
    r = [x for x in _as_list(_get(SN + "/sc_request")) if str(x.get("number")) == "REQ0071001"]
    if not r:
        return False
    rec = r[0]
    return str(rec.get("request_state", "")).lower().startswith("closed") or str(rec.get("state")) == "3"

def test_apply_priya_deploy_group():
    assert UID("priya-nair") in _group_uids("g-deploy")

def test_apply_priya_spinnaker_app():
    assert UID("priya-nair") in _app_uids("app-spinnaker")

def test_apply_diego_org_member():
    assert "diego-santos" in _org_members()

def test_apply_diego_collaborator_payments_ledger():
    assert "diego-santos" in _repo_collab_logins("payments-ledger")

def test_apply_diego_grafana_app():
    assert UID("diego-santos") in _app_uids("app-grafana")

def test_apply_priya_collaborator_edge_gateway():
    assert "priya-nair" in _repo_collab_logins("edge-gateway")

def test_revoke_marcus_admin_group():
    assert UID("marcus-feld") not in _group_uids("g-admin")

def test_revoke_marcus_netsuite_app():
    assert UID("marcus-feld") not in _app_uids("app-netsuite")

def test_revoke_marcus_collaborator_treasury():
    assert "marcus-feld" not in _repo_collab_logins("treasury-core")

def test_revoke_yuki_admin_group():
    assert UID("yuki-tan") not in _group_uids("g-admin")

def test_revoke_yuki_netsuite_app():
    assert UID("yuki-tan") not in _app_uids("app-netsuite")

def test_revoke_elena_deploy_group():
    assert UID("elena-rossi") not in _group_uids("g-deploy")

def test_revoke_elena_netsuite_app():
    assert UID("elena-rossi") not in _app_uids("app-netsuite")

def test_revoke_elena_collaborator_edge_gateway():
    assert "elena-rossi" not in _repo_collab_logins("edge-gateway")

def test_rightsize_marcus_org_role_member():
    assert _org_members().get("marcus-feld") == "member"

def test_rightsize_elena_org_role_member():
    assert _org_members().get("elena-rossi") == "member"

def test_residue_elena_superadmin_role_revoked():
    assert "SUPER_ADMIN" not in _okta_role_types("elena-rossi")

def test_residue_elena_deploy_key_removed():
    assert "5001" not in _repo_key_ids("payments-ledger")

def test_residue_yuki_deploy_key_removed():
    assert "5003" not in _repo_key_ids("treasury-core")

def test_residue_marcus_deploy_key_removed():
    assert "5004" not in _repo_key_ids("risk-engine")

def test_recert_request_closed():
    assert _recert_closed()
