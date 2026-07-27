import json
import urllib.error
import urllib.request

OKTA = "http://okta.local.mock:8080/api/v1"
ENTRA = "http://entra-id-governance.local.mock:8080/v1.0"
SN = "http://servicenow.local.mock:8080/api/now/table"
INC_SYS = "c080e1c439c36072eeb942f6a54f5332"

def E(k):
    return "%s@acme.example" % k

STATUS_GAPS = [E(k) for k in ("john.smith", "dana.okafor", "raj.patel", "mei.chen")]
APP_GAPS = [
    (E("leo.brand"), "Production Database Console"), (E("sara.kim"), "Finance Console"),
    (E("omar.said"), "Data Warehouse"),
    (E("carla.diaz"), "Sensitive Reports"), (E("tom.lee"), "Cloud Admin Portal"),
    (E("nina.roy"), "Production Database Console"),
    (E("ivan.petrov"), "Finance Console"), (E("lucy.wang"), "Data Warehouse"),
]
ROLE_GAPS = [(E("paul.mor"), "ORG_ADMIN"), (E("greg.hall"), "SUPER_ADMIN"), (E("ada.ncube"), "APP_ADMIN")]
POLICY_GAPS = ["pol-eng-broad", "pol-fin-broad"]

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode()
    return json.loads(raw) if raw and raw.strip()[:1] in "{[" else raw

def _user(email):
    users = _get(OKTA + "/users")
    return next((x for x in (users if isinstance(users, list) else [])
                 if str((x.get("profile") or {}).get("email")).lower() == email.lower()), None)

def _app_id(label):
    apps = _get(OKTA + "/apps")
    a = next((x for x in (apps if isinstance(apps, list) else []) if str(x.get("label")) == label), None)
    return str(a.get("id")) if a else None

def _effective_ids(app_id):
    r = _get(OKTA + "/apps/%s/users" % app_id)
    return {str(a.get("id")) for a in (r if isinstance(r, list) else [])}

def _policy_scope(name):
    pols = _get(ENTRA + "/identityGovernance/entitlementManagement/assignmentPolicies")
    pols = pols.get("value", []) if isinstance(pols, dict) else (pols if isinstance(pols, list) else [])
    p = next((x for x in pols if str(x.get("displayName")) == name), None)
    return str(p.get("allowedTargetScope")) if p else None

def _incident_state(sys_id):
    r = _get(SN + "/incident/" + sys_id)
    rec = (r or {}).get("result") if isinstance(r, dict) else None
    return str(rec.get("state")) if rec else None

def _status_removed(email):
    u = _user(email)
    return u is not None and str(u.get("status")) in ("DEPROVISIONED", "SUSPENDED")

def _app_revoked(email, label):
    u = _user(email)
    app_id = _app_id(label)
    return u is not None and app_id is not None and str(u.get("id")) not in _effective_ids(app_id)

def _role_revoked(email, rtype):
    u = _user(email)
    return u is not None and rtype not in {str(r.get("type")) for r in (u.get("roleAssignments") or [])}

for _i, _e in enumerate(STATUS_GAPS):
    def _mk(email):
        def t():
            assert _status_removed(email)
        return t
    globals()["test_status_deprovisioned_%d" % (_i + 1)] = _mk(_e)
for _i, (_e, _lab) in enumerate(APP_GAPS):
    def _mka(email, lab):
        def t():
            assert _app_revoked(email, lab)
        return t
    globals()["test_app_access_revoked_%d" % (_i + 1)] = _mka(_e, _lab)
for _i, (_e, _rt) in enumerate(ROLE_GAPS):
    def _mkr(email, rt):
        def t():
            assert _role_revoked(email, rt)
        return t
    globals()["test_role_revoked_%d" % (_i + 1)] = _mkr(_e, _rt)
_POLICY_TIGHTENED_OK = {
    "specificDirectoryUsers",
    "specificConnectedOrganizationUsers",
    "noSubjects",
    "notSpecified",
}
for _i, _pn in enumerate(POLICY_GAPS):
    def _mkp(pn):
        def t():
            assert _policy_scope(pn) in _POLICY_TIGHTENED_OK
        return t
    globals()["test_policy_tightened_%d" % (_i + 1)] = _mkp(_pn)

def test_incident_closed():
    s = str(_incident_state(INC_SYS)).lower()
    assert s in ("6", "7") or "clos" in s or "resolv" in s
