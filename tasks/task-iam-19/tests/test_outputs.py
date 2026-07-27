
import json
import urllib.error
import urllib.parse
import urllib.request

OKTA = "http://okta.local.mock:8080"
SN = "http://servicenow.local.mock:8080"
DOMAIN = "harborline.example"

ADMIN_GROUP = "Platform Superadmins"
PAY_GROUP = "Payments Data Admins"
VPN_GROUP = "VPN - Privileged"
SUPER = "SUPER_ADMIN"
INCIDENT = "INC0071004"

V1 = "marcus.feldon@" + DOMAIN
V2 = "yuki.tanaka@" + DOMAIN
V6 = "priya.raman@" + DOMAIN
V8 = "mia.silva@" + DOMAIN
V3 = "gregor.halvorsen@" + DOMAIN
V4 = "dylan.okoro@" + DOMAIN
V9 = "noah.kim@" + DOMAIN
V5 = "nadia.cho@" + DOMAIN
V7 = "liam.nguyen@" + DOMAIN
V10 = "zoe.falk@" + DOMAIN
V11 = "nora.moss@" + DOMAIN
V12 = "omar.ford@" + DOMAIN
V13 = "lena.wolf@" + DOMAIN
A5 = "ethan.klein@" + DOMAIN
A6 = "ava.adler@" + DOMAIN
PA2 = "emma.voss@" + DOMAIN
B1 = "svc-monitoring-sync@" + DOMAIN
B2 = "svc-log-shipper@" + DOMAIN
BG = "svc-breakglass@" + DOMAIN

A1 = "tomas.vidal@" + DOMAIN
A2 = "elena.vasquez@" + DOMAIN
A3 = "raj.patel@" + DOMAIN
A4 = "olivia.reyes@" + DOMAIN
PLANTED = {A1: "sms", A2: "webauthn", A3: "token:software:totp", A4: "call"}

APP_AWS = "AWS Production Console"
APP_GH = "GitHub Enterprise"
APP_SNOW = "Snowflake Prod"

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

def _user(login):
    lo = login.lower()
    for u in _okta_users():
        if str(u.get("profile", {}).get("login", "")).lower() == lo:
            return u
    return None

def _cannot_auth(login):
    u = _user(login)
    return u is None or str(u.get("status")) != "ACTIVE"

def _active_role_types(login):
    u = _user(login)
    if not u:
        return set()
    roles = _as_list(_get(OKTA + "/api/v1/users/%s/roles" % u["id"]))
    return {str(r.get("type")) for r in roles if str(r.get("status", "ACTIVE")).upper() == "ACTIVE"}

def _group_id(name):
    for g in _as_list(_get(OKTA + "/api/v1/groups?limit=200")):
        if str(g.get("profile", {}).get("name", "")) == name:
            return g["id"]
    return None

def _in_group(login, name):
    gid = _group_id(name)
    if gid is None:
        return False
    users = _as_list(_get(OKTA + "/api/v1/groups/%s/users?limit=200" % gid))
    return login.lower() in {str(u.get("profile", {}).get("login", "")).lower() for u in users}

def _factor_types(login):
    u = _user(login)
    if not u:
        return set()
    return {str(f.get("factorType")) for f in _as_list(_get(OKTA + "/api/v1/users/%s/factors" % u["id"]))}

def _app_id(label):
    for a in _as_list(_get(OKTA + "/api/v1/apps?limit=200")):
        if str(a.get("label", "")) == label:
            return a["id"]
    return None

def _app_has_user(label, login):
    aid = _app_id(label)
    if aid is None:
        return False
    u = _user(login)
    if u is None:
        return False
    ids = {str(x.get("id")) for x in _as_list(_get(OKTA + "/api/v1/apps/%s/users?limit=200" % aid))}
    return u["id"] in ids

def _bg_field(field):
    u = _user(BG)
    return bool(u.get(field)) if u else False

def _incident():
    rows = _as_list(_get(SN + "/api/now/table/incident?sysparm_query=" + urllib.parse.quote("number=%s" % INCIDENT)))
    return rows[0] if rows else None

def test_v1_admin_role_revoked():
    assert SUPER not in _active_role_types(V1)

def test_v2_admin_role_revoked():
    assert SUPER not in _active_role_types(V2)

def test_v6_admin_role_revoked():
    assert SUPER not in _active_role_types(V6)

def test_v8_admin_role_revoked():
    assert SUPER not in _active_role_types(V8)

def test_v10_admin_role_revoked():
    assert SUPER not in _active_role_types(V10)

def test_v12_admin_role_revoked():
    assert SUPER not in _active_role_types(V12)

def test_v3_removed_from_admin_group():
    assert not _in_group(V3, ADMIN_GROUP)

def test_v4_removed_from_admin_group():
    assert not _in_group(V4, ADMIN_GROUP)

def test_v9_removed_from_admin_group():
    assert not _in_group(V9, ADMIN_GROUP)

def test_v11_removed_from_admin_group():
    assert not _in_group(V11, ADMIN_GROUP)

def test_v5_removed_from_payments_group():
    assert not _in_group(V5, PAY_GROUP)

def test_v7_removed_from_vpn_group():
    assert not _in_group(V7, VPN_GROUP)

def test_b1_backdoor_cannot_auth():
    assert _cannot_auth(B1)

def test_b2_backdoor_cannot_auth():
    assert _cannot_auth(B2)

def test_a1_planted_factor_removed():
    assert PLANTED[A1] not in _factor_types(A1)

def test_a2_planted_factor_removed():
    assert PLANTED[A2] not in _factor_types(A2)

def test_a3_planted_factor_removed():
    assert PLANTED[A3] not in _factor_types(A3)

def test_a4_planted_factor_removed():
    assert PLANTED[A4] not in _factor_types(A4)

def test_aws_app_v1_unassigned():
    assert not _app_has_user(APP_AWS, V1)

def test_github_app_v2_unassigned():
    assert not _app_has_user(APP_GH, V2)

def test_snowflake_app_v6_unassigned():
    assert not _app_has_user(APP_SNOW, V6)

def test_github_app_v13_unassigned():
    assert not _app_has_user(APP_GH, V13)

def test_a5_restored_to_admin_group():
    assert _in_group(A5, ADMIN_GROUP)

def test_a6_restored_to_admin_group():
    assert _in_group(A6, ADMIN_GROUP)

def test_pa2_reactivated():
    u = _user(PA2)
    assert u is not None and str(u.get("status")) == "ACTIVE"

def test_breakglass_credential_rotated():
    assert _bg_field("passwordChanged")

def test_breakglass_sessions_revoked():
    assert _bg_field("sessionsRevoked")

def test_incident_closed():
    t = _incident()
    assert t is not None
    s = str(t.get("state")).lower()
    assert s in ("6", "7") or "clos" in s or "resolv" in s
