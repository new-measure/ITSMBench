
import json
import urllib.error
import urllib.parse
import urllib.request

OKTA = "http://okta.local.mock:8080"
GH = "http://github.local.mock:8080"
SN = "http://servicenow.local.mock:8080"
GH_ORG = "nimbus-logistics"
DOMAIN = "nimbuslogistics.example"

ADMIN_GROUP = "Automation Admins"
ADMIN_TEAM = "automation"
TICKET = "INC0071001"

N1 = "svc-legacy-backup@" + DOMAIN
N2 = "svc-reporting-sync@" + DOMAIN
N5 = "svc-data-exporter@" + DOMAIN
N6 = "svc-legacy-sso-bridge@" + DOMAIN
N8 = "svc-batch-archiver@" + DOMAIN
N9 = "ci-runner-prod@" + DOMAIN
N3 = "svc-ci-deployer@" + DOMAIN
N7 = "svc-metrics-pusher@" + DOMAIN
N10 = "svc-artifact-cache@" + DOMAIN

N5_GH = "svc-data-exporter"
N8_GH = "svc-batch-archiver"
N3_GH = "svc-ci-deployer"
N10_GH = "svc-artifact-cache"

KEY_N1 = ("backups", "legacy-backup-deploy")
KEY_N2 = ("data-warehouse", "reporting-sync-deploy")
KEY_N8 = ("archive", "batch-archiver-deploy")
KEY_N9 = ("deploy-tools", "ci-runner-deploy")
KEY_N4_STALE = ("infra", "terraform-deploy-2024")

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

def _okta_user(login):
    lo = login.lower()
    for u in _as_list(_get(OKTA + "/api/v1/users?limit=200")):
        if str(u.get("profile", {}).get("login", "")).lower() == lo:
            return u
    return None

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

def _has_admin_role(login):
    return any(str(t).endswith("_ADMIN") for t in _okta_active_role_types(login))

def _gh_org_role(login):
    for m in _as_list(_get(GH + "/orgs/%s/members" % GH_ORG)):
        if str(m.get("login", "")).lower() == login.lower() and not m.get("team_slug"):
            return str(m.get("role", "member"))
    return None

def _gh_team_role(login):
    for m in _as_list(_get(GH + "/orgs/%s/teams/%s/members" % (GH_ORG, ADMIN_TEAM))):
        if str(m.get("login", "")).lower() == login.lower():
            return str(m.get("role", "member"))
    return None

def _gh_repo_key_titles(repo):
    return {str(k.get("title", "")) for k in _as_list(_get(GH + "/repos/%s/%s/keys" % (GH_ORG, repo)))}

def _sn_ticket():
    rows = _as_list(_get(SN + "/api/now/table/incident?sysparm_query=" + urllib.parse.quote("number=%s" % TICKET)))
    return rows[0] if rows else None

def test_n1_account_deactivated():
    assert _okta_cannot_auth(N1)

def test_n1_admin_role_revoked():
    assert not _has_admin_role(N1)

def test_n1_removed_from_admin_group():
    assert not _okta_in_group(N1, ADMIN_GROUP)

def test_n1_deploy_key_deleted():
    assert KEY_N1[1] not in _gh_repo_key_titles(KEY_N1[0])

def test_n2_account_deactivated():
    assert _okta_cannot_auth(N2)

def test_n2_admin_role_revoked():
    assert not _has_admin_role(N2)

def test_n2_deploy_key_deleted():
    assert KEY_N2[1] not in _gh_repo_key_titles(KEY_N2[0])

def test_n5_account_deactivated():
    assert _okta_cannot_auth(N5)

def test_n5_admin_role_revoked():
    assert not _has_admin_role(N5)

def test_n5_github_org_owner_downgraded():
    assert _gh_org_role(N5_GH) != "admin"

def test_n5_github_team_maintainer_removed():
    assert _gh_team_role(N5_GH) != "maintainer"

def test_n6_account_deactivated():
    assert _okta_cannot_auth(N6)

def test_n6_admin_role_revoked():
    assert not _has_admin_role(N6)

def test_n6_removed_from_admin_group():
    assert not _okta_in_group(N6, ADMIN_GROUP)

def test_n8_account_deactivated():
    assert _okta_cannot_auth(N8)

def test_n8_admin_role_revoked():
    assert not _has_admin_role(N8)

def test_n8_removed_from_admin_group():
    assert not _okta_in_group(N8, ADMIN_GROUP)

def test_n8_github_org_owner_downgraded():
    assert _gh_org_role(N8_GH) != "admin"

def test_n8_deploy_key_deleted():
    assert KEY_N8[1] not in _gh_repo_key_titles(KEY_N8[0])

def test_n9_account_deactivated():
    assert _okta_cannot_auth(N9)

def test_n9_admin_role_revoked():
    assert not _has_admin_role(N9)

def test_n9_removed_from_admin_group():
    assert not _okta_in_group(N9, ADMIN_GROUP)

def test_n9_deploy_key_deleted():
    assert KEY_N9[1] not in _gh_repo_key_titles(KEY_N9[0])

def test_n3_admin_role_revoked():
    assert not _has_admin_role(N3)

def test_n3_removed_from_admin_group():
    assert not _okta_in_group(N3, ADMIN_GROUP)

def test_n3_github_org_owner_downgraded():
    assert _gh_org_role(N3_GH) != "admin"

def test_n7_removed_from_admin_group():
    assert not _okta_in_group(N7, ADMIN_GROUP)

def test_n10_github_team_maintainer_removed():
    assert _gh_team_role(N10_GH) != "maintainer"

def test_n4_superseded_deploy_key_deleted():
    assert KEY_N4_STALE[1] not in _gh_repo_key_titles(KEY_N4_STALE[0])

def test_finding_ticket_closed():
    t = _sn_ticket()
    assert t is not None
    s = str(t.get("state")).lower()
    assert s in ("6", "7") or "clos" in s or "resolv" in s
