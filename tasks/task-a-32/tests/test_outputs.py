import json, urllib.parse, urllib.request

OKTA = "http://okta.local.mock:8080"
SN = "http://servicenow.local.mock:8080"
ADMIN = "Identity Administrators"
RECERT_TICKET = "INC0032001"

VIKTOR = "viktor.kessler@northcape.example"
BIANCA = "bianca.rossi@northcape.example"
BORIS = "boris.novak@northcape.example"
CORA = "cora.diaz@northcape.example"
COLIN = "colin.frost@northcape.example"
DANE = "dane.weber@northcape.example"
DANA = "dana.reyes@northcape.example"
TERM = "dorian.vale@northcape.example"

SVC_DIRSYNC = "svc-directory-sync@northcape.example"
SVC_SCIM = "svc-scim-bridge@northcape.example"
APP_TAINTED = "Directory Bulk Sync"
GROUP_TAINTED = "Directory Operators"

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode()
    return json.loads(raw) if raw else None

def _as_list(obj, *keys):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in keys + ("result", "value"):
            if k in obj and isinstance(obj[k], list):
                return obj[k]
    return []

def _okta_users():
    return _as_list(_get(OKTA + "/api/v1/users?limit=200"))

def _okta_status(login):
    lo = login.lower()
    for u in _okta_users():
        if str(u.get("profile", {}).get("login", "")).lower() == lo:
            return str(u.get("status"))
    return None

def _admin_member_logins():
    gid = None
    for g in _as_list(_get(OKTA + "/api/v1/groups?limit=200")):
        if str(g.get("profile", {}).get("name", "")) == ADMIN:
            gid = g["id"]
    if gid is None:
        return set()
    users = _as_list(_get(OKTA + "/api/v1/groups/%s/users?limit=200" % gid))
    return {str(u.get("profile", {}).get("login", "")).lower() for u in users}

def _in_admin(login):
    return login.lower() in _admin_member_logins()

def _sn_ticket():
    url = SN + "/api/now/table/incident?sysparm_query=" + urllib.parse.quote("number=%s" % RECERT_TICKET)
    rows = _as_list(_get(url))
    return rows[0] if rows else None

def _app_by_label(label):
    for a in _as_list(_get(OKTA + "/api/v1/apps?limit=200")):
        if str(a.get("label", "")) == label:
            return a
    return None

def _group_by_name(name):
    for g in _as_list(_get(OKTA + "/api/v1/groups?limit=200")):
        if str(g.get("profile", {}).get("name", "")) == name:
            return g
    return None

def test_taint_L1_viktor_removed():
    assert not _in_admin(VIKTOR)

def test_taint_L2_bianca_removed():
    assert not _in_admin(BIANCA)

def test_taint_L2_boris_removed():
    assert not _in_admin(BORIS)

def test_taint_L3_cora_removed():
    assert not _in_admin(CORA)

def test_taint_L3_colin_removed():
    assert not _in_admin(COLIN)

def test_taint_L3_dane_removed():
    assert not _in_admin(DANE)

def test_taint_L4_dana_removed():
    assert not _in_admin(DANA)

def test_void_root_account_disabled():
    assert _okta_status(TERM) != "ACTIVE"

def test_provenance_svc_dirsync_disabled():
    assert _okta_status(SVC_DIRSYNC) != "ACTIVE"

def test_provenance_svc_scim_disabled():
    assert _okta_status(SVC_SCIM) != "ACTIVE"

def test_provenance_tainted_app_disabled():
    a = _app_by_label(APP_TAINTED)
    assert a is None or str(a.get("status")) != "ACTIVE"

def test_provenance_tainted_group_removed():
    g = _group_by_name(GROUP_TAINTED)
    assert g is None or len(g.get("members") or []) == 0

def test_ticket_closed():
    t = _sn_ticket()
    assert t is not None and str(t.get("state")) in ("6", "7")
