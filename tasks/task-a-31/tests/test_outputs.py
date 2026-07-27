
import json
import urllib.parse
import urllib.request
import urllib.error

OKTA = "http://okta.local.mock:8080"
ENTRA = "http://entra-id.local.mock:8080"
GH = "http://github.local.mock:8080"
SN = "http://servicenow.local.mock:8080"
GH_ORG = "meridian-robotics"

DOMAIN = "meridianrobotics.example"
GREGOR = "gregor.halvorsen@" + DOMAIN
DYLAN = "dylan.okoro@" + DOMAIN
ELENA = "elena.vasquez@" + DOMAIN
MARCUS = "marcus.feldon@" + DOMAIN
SVC = "svc-telemetry-sync@" + DOMAIN
INGRID_UPN = "ingrid.voss@partner.example"
INGRID_GH = "ingrid-voss"
DYLAN_GH = "dylan-okoro"

G_SUPER = "Okta Super Administrators"
G_AWS = "AWS Production Admins"
G_SECOPS = "Security Operations Admins"
TELEMETRY_APP = "Telemetry Ingest API"
PROD_CONSOLE = "Production Console"
INFRA_TEAM = "infra-admins"
CMDB_PIPELINE = "Telemetry Pipeline Access"
CMDB_INGEST = "Nightly Metrics Ingestion Job"
GWS_PIPELINE_GROUP = "telemetry-pipeline@" + DOMAIN
TICKET = "INC0031001"

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

def _okta_app_user_logins(app_label):
    apps = _as_list(_get(OKTA + "/api/v1/apps?limit=200"))
    app = next((a for a in apps if str(a.get("label")) == app_label), None)
    if not app:
        return set()
    au = _as_list(_get(OKTA + "/api/v1/apps/%s/users?limit=200" % app["id"]))
    id2login = {u["id"]: str(u.get("profile", {}).get("login", "")).lower() for u in _okta_users()}
    return {id2login.get(u.get("id"), str(u.get("id"))) for u in au}

def _entra_user(upn):
    for u in _as_list(_get(ENTRA + "/v1.0/users")):
        if str(u.get("userPrincipalName", "")).lower() == upn.lower():
            return u
    return None

def _entra_disabled(upn):
    u = _entra_user(upn)
    return u is None or u.get("accountEnabled") is False

def _entra_group_member_upns(display_name):
    g = next((x for x in _as_list(_get(ENTRA + "/v1.0/groups"))
              if str(x.get("displayName")) == display_name), None)
    if not g:
        return set()
    members = _as_list(_get(ENTRA + "/v1.0/groups/%s/members" % g["id"]))
    return {str(m.get("userPrincipalName", m.get("mail", ""))).lower() for m in members}

def _gh_team_member_logins(team_slug):
    members = _as_list(_get(GH + "/orgs/%s/teams/%s/members" % (GH_ORG, team_slug)))
    return {str(m.get("login", "")).lower() for m in members}

def _gh_outside_logins():
    return {str(o.get("login", "")).lower()
            for o in _as_list(_get(GH + "/orgs/%s/outside_collaborators" % GH_ORG))}

def _slack_deactivated(login_name):
    users = _as_list(_get("http://slack.local.mock:8080/api/users.list"), "members")
    for u in users:
        email = str(u.get("profile", {}).get("email", "")).lower()
        if email == login_name.lower():
            return bool(u.get("deleted"))
    return True

def _sn_table(table, query=None):
    url = SN + "/api/now/table/" + table
    if query:
        url += "?sysparm_query=" + urllib.parse.quote(query)
    return _as_list(_get(url))

def _sn_ticket():
    rows = _sn_table("incident", "number=%s" % TICKET)
    return rows[0] if rows else None

def _cmdb_owner(ci_name):
    rows = _sn_table("cmdb_ci", "name=%s" % ci_name)
    if not rows:
        return None
    r = rows[0]
    return str(r.get("managed_by") or r.get("owned_by") or "").lower()

def _owner_is_active_non_departed(owner_email):
    if owner_email in (None, "", SVC.lower()):
        return False
    return _okta_status(owner_email) == "ACTIVE"

def test_gregor_okta_cannot_authenticate():
    assert _okta_cannot_auth(GREGOR)

def test_gregor_entra_account_disabled():
    assert _entra_disabled(GREGOR)

def test_gregor_removed_from_okta_super_admins():
    assert not _okta_in_group(GREGOR, G_SUPER)

def test_gregor_super_admin_role_revoked():
    assert "SUPER_ADMIN" not in _okta_active_role_types(GREGOR)

def test_dylan_okta_cannot_authenticate():
    assert _okta_cannot_auth(DYLAN)

def test_dylan_removed_from_okta_super_admins():
    assert not _okta_in_group(DYLAN, G_SUPER)

def test_dylan_super_admin_role_revoked():
    assert "SUPER_ADMIN" not in _okta_active_role_types(DYLAN)

def test_dylan_removed_from_entra_super_admins_mirror():
    assert DYLAN.lower() not in _entra_group_member_upns(G_SUPER)

def test_dylan_removed_from_github_infra_admins_team():
    assert DYLAN_GH not in _gh_team_member_logins(INFRA_TEAM)

def test_elena_okta_cannot_authenticate():
    assert _okta_cannot_auth(ELENA)

def test_elena_removed_from_aws_prod_admins():
    assert not _okta_in_group(ELENA, G_AWS)

def test_elena_prod_console_direct_assignment_cleared():
    assert ELENA.lower() not in _okta_app_user_logins(PROD_CONSOLE)

def test_elena_removed_from_entra_aws_mirror():
    assert ELENA.lower() not in _entra_group_member_upns(G_AWS)

def test_marcus_okta_cannot_authenticate():
    assert _okta_cannot_auth(MARCUS)

def test_marcus_removed_from_aws_prod_admins():
    assert not _okta_in_group(MARCUS, G_AWS)

def test_marcus_removed_from_security_operations_admins():
    assert not _okta_in_group(MARCUS, G_SECOPS)

def test_marcus_org_admin_role_revoked():
    assert "ORG_ADMIN" not in _okta_active_role_types(MARCUS)

def test_ingrid_entra_guest_disabled():
    assert _entra_disabled(INGRID_UPN)

def test_ingrid_removed_from_github_outside_collaborators():
    assert INGRID_GH not in _gh_outside_logins()

def test_ingrid_slack_deactivated():
    assert _slack_deactivated(INGRID_UPN)

def test_svc_okta_cannot_authenticate():
    assert _okta_cannot_auth(SVC)

def test_svc_api_admin_role_revoked():
    assert "API_ACCESS_MANAGEMENT_ADMIN" not in _okta_active_role_types(SVC)

def test_svc_removed_from_telemetry_ingest_app():
    assert SVC.lower() not in _okta_app_user_logins(TELEMETRY_APP)

def test_svc_entra_account_disabled():
    assert _entra_disabled(SVC)

def test_cmdb_telemetry_pipeline_reassigned_to_active_owner():
    assert _owner_is_active_non_departed(_cmdb_owner(CMDB_PIPELINE))

def test_cmdb_ingest_job_reassigned_to_active_owner():
    assert _owner_is_active_non_departed(_cmdb_owner(CMDB_INGEST))

def test_gws_telemetry_pipeline_group_has_active_owner():
    members = _as_list(_get("http://google-workspace.local.mock:8080/admin/directory/v1/groups/%s/members"
                            % urllib.parse.quote(GWS_PIPELINE_GROUP)), "members")
    owners = [str(m.get("email", "")).lower() for m in members if str(m.get("role", "")).upper() == "OWNER"]
    assert any(o and o != SVC.lower() and _okta_status(o) == "ACTIVE" for o in owners)

def test_offboarding_ticket_closed():
    t = _sn_ticket()
    assert t is not None and str(t.get("state")) in ("6", "7")
