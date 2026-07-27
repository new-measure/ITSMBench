
import json
import urllib.error
import urllib.parse
import urllib.request

OKTA = "http://okta.local.mock:8080"
GH = "http://github.local.mock:8080"
SN = "http://servicenow.local.mock:8080"
GH_ORG = "kestrel-data"
DOMAIN = "kestreldata.example"

ADMIN_GROUP = "Cloud Platform Admins"
ADMIN_ROLE = "SUPER_ADMIN"
ADMIN_TEAM = "platform-admins"
TICKET = "INC0045001"

C1 = "gregor.halvorsen@" + DOMAIN
C2 = "dylan.okoro@" + DOMAIN
C3 = "elena.vasquez@" + DOMAIN
C4 = "marcus.feldon@" + DOMAIN
C5 = "yuki.tanaka@" + DOMAIN
C6 = "priya.raman@" + DOMAIN
C7 = "liam.nguyen@" + DOMAIN
SVC = "svc-atlas-deploy@" + DOMAIN

C2_GH = "dylan-okoro"
C4_GH = "marcus-feldon"
C5_GH = "yuki-tanaka"

KEY_C3_TITLE = "atlas-ci-infra"
KEY_C3_REPO = "infra"
KEY_SVC_TITLE = "atlas-deploy-platform"
KEY_SVC_REPO = "platform"

def _get(url, allow_404=True):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        if allow_404 and e.code == 404:
            return None
        raise
    return json.loads(raw) if raw else None

def _as_list(obj, *keys):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in keys + ("value", "values", "result", "results", "items", "members", "users"):
            if k in obj and isinstance(obj[k], list):
                return obj[k]
    return []

def _okta_users():
    return _as_list(_get(OKTA + "/api/v1/users?limit=200"))

def _okta_user(login):
    lo = login.lower()
    for u in _okta_users():
        if str(u.get("profile", {}).get("login", "")).lower() == lo:
            return u
    return None

def _okta_status(login):
    u = _okta_user(login)
    return str(u.get("status")) if u else None

def _okta_cannot_auth(login):
    u = _okta_user(login)
    return u is None or str(u.get("status")) != "ACTIVE"

def _okta_group_id(name):
    for g in _as_list(_get(OKTA + "/api/v1/groups?limit=200")):
        if str(g.get("profile", {}).get("name", "")) == name:
            return g["id"]
    return None

def _okta_in_group(login, group_name):
    gid = _okta_group_id(group_name)
    if gid is None:
        return False
    users = _as_list(_get(OKTA + "/api/v1/groups/%s/users?limit=200" % gid))
    return login.lower() in {str(u.get("profile", {}).get("login", "")).lower() for u in users}

def _okta_active_role_types(login):
    u = _okta_user(login)
    if not u:
        return set()
    roles = _as_list(_get(OKTA + "/api/v1/users/%s/roles" % u["id"]))
    return {str(r.get("type")) for r in roles if str(r.get("status", "ACTIVE")).upper() == "ACTIVE"}

def _gh_team_role(login):
    for m in _as_list(_get(GH + "/orgs/%s/teams/%s/members" % (GH_ORG, ADMIN_TEAM))):
        if str(m.get("login", "")).lower() == login.lower():
            return str(m.get("role", "member"))
    return None

def _gh_org_role(login):
    for m in _as_list(_get(GH + "/orgs/%s/members" % GH_ORG)):
        if str(m.get("login", "")).lower() == login.lower() and not m.get("team_slug"):
            return str(m.get("role", "member"))
    return None

def _gh_repo_key_titles(repo):
    keys = _as_list(_get(GH + "/repos/%s/%s/keys" % (GH_ORG, repo)))
    return {str(k.get("title", "")) for k in keys}

def _sn_ticket():
    rows = _as_list(_get(SN + "/api/now/table/incident?sysparm_query=" + urllib.parse.quote("number=%s" % TICKET)))
    return rows[0] if rows else None

def test_c1_removed_from_admin_group():
    assert not _okta_in_group(C1, ADMIN_GROUP)

def test_c1_admin_role_revoked():
    assert ADMIN_ROLE not in _okta_active_role_types(C1)

def test_c2_removed_from_admin_group():
    assert not _okta_in_group(C2, ADMIN_GROUP)

def test_c2_admin_role_revoked():
    assert ADMIN_ROLE not in _okta_active_role_types(C2)

def test_c2_github_team_maintainer_removed():
    assert _gh_team_role(C2_GH) != "maintainer"

def test_c3_removed_from_admin_group():
    assert not _okta_in_group(C3, ADMIN_GROUP)

def test_c3_admin_role_revoked():
    assert ADMIN_ROLE not in _okta_active_role_types(C3)

def test_c3_stale_deploy_key_removed():
    assert KEY_C3_TITLE not in _gh_repo_key_titles(KEY_C3_REPO)

def test_c4_removed_from_admin_group():
    assert not _okta_in_group(C4, ADMIN_GROUP)

def test_c4_admin_role_revoked():
    assert ADMIN_ROLE not in _okta_active_role_types(C4)

def test_c4_github_org_owner_downgraded():
    assert _gh_org_role(C4_GH) != "admin"

def test_c5_admin_role_revoked():
    assert ADMIN_ROLE not in _okta_active_role_types(C5)

def test_c5_github_team_maintainer_removed():
    assert _gh_team_role(C5_GH) != "maintainer"

def test_c6_removed_from_admin_group():
    assert not _okta_in_group(C6, ADMIN_GROUP)

def test_c6_admin_role_revoked():
    assert ADMIN_ROLE not in _okta_active_role_types(C6)

def test_c7_removed_from_admin_group():
    assert not _okta_in_group(C7, ADMIN_GROUP)

def test_c7_admin_role_revoked():
    assert ADMIN_ROLE not in _okta_active_role_types(C7)

def test_svc_account_deactivated():
    assert _okta_cannot_auth(SVC)

def test_svc_admin_role_revoked():
    assert ADMIN_ROLE not in _okta_active_role_types(SVC)

def test_svc_deploy_key_removed():
    assert KEY_SVC_TITLE not in _gh_repo_key_titles(KEY_SVC_REPO)

def test_audit_ticket_closed():
    t = _sn_ticket()
    assert t is not None
    s = str(t.get("state")).lower()
    assert s in ("6", "7") or "clos" in s or "resolv" in s
