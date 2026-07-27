import hashlib
import json
import urllib.parse
import urllib.request

SF = "http://salesforce.local.mock:8080/services/data/v67.0"
SN = "http://servicenow.local.mock:8080/api/now/table"

def sfid(prefix, key, width=15):
    return prefix + hashlib.md5(("iam12|" + key).encode()).hexdigest()[:width]

VIOLATORS = [
    ("v01", "Create_Vendor", "Approve_Payment"),
    ("v02", "Create_Vendor", "Approve_Payment"),
    ("v03", "Approve_Payment", "Create_Vendor"),
    ("v04", "Approve_Payment", "Create_Vendor"),
    ("v05", "Manage_Users", "View_All_Data"),
    ("v06", "Manage_Users", "View_All_Data"),
    ("v07", "Manage_Users", "View_All_Data"),
    ("v08", "View_All_Data", "Manage_Users"),
    ("v09", "View_All_Data", "Manage_Users"),
    ("v10", "Submit_Expense", "Approve_Expense"),
    ("v11", "Submit_Expense", "Approve_Expense"),
    ("v12", "Approve_Expense", "Submit_Expense"),
    ("v13", "Post_Journal_Entry", "Approve_Journal_Entry"),
    ("v14", "Post_Journal_Entry", "Approve_Journal_Entry"),
    ("v15", "Approve_Journal_Entry", "Post_Journal_Entry"),
    ("v16", "Approve_Journal_Entry", "Post_Journal_Entry"),
    ("v17", "Submit_Expense", "Approve_Expense"),
    ("v18", "View_All_Data", "Manage_Users"),
    ("b01", "Create_Vendor", "Approve_Payment"),
    ("b02", "Approve_Payment", "Create_Vendor"),
    ("b03", "Manage_Users", "View_All_Data"),
    ("b04", "Post_Journal_Entry", "Approve_Journal_Entry"),
    ("b05", "Approve_Expense", "Submit_Expense"),
    ("b06", "View_All_Data", "Manage_Users"),
]
VIOLATOR_UID = {k: sfid("005", "user|" + k) for k, _keep, _toxic in VIOLATORS}
FINDING_NUMBER = "GRC0007742"

def _is_closed(state_val):
    s = str(state_val).strip().lower()
    return s in ("6", "7") or "resolv" in s or "clos" in s

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode()
    return json.loads(raw) if raw else None

def soql(q):
    doc = _get(f"{SF}/query?q={urllib.parse.quote(q)}")
    return (doc or {}).get("records", [])

def _load_state():
    users = {u["Id"]: u for u in soql("SELECT Id, ProfileId FROM User")}
    perm_sets = soql("SELECT Id, IsOwnedByProfile, ProfileId FROM PermissionSet")
    sea = soql("SELECT Id, ParentId, SetupEntityId FROM SetupEntityAccess")
    comps = soql("SELECT Id, PermissionSetGroupId, PermissionSetId FROM PermissionSetGroupComponent")
    psas = soql("SELECT Id, AssigneeId, PermissionSetId, PermissionSetGroupId FROM PermissionSetAssignment")
    cperms = soql("SELECT Id, DeveloperName FROM CustomPermission")

    prof_owned = {}
    for ps in perm_sets:
        if ps.get("IsOwnedByProfile") in (True, "true"):
            prof_owned[ps.get("ProfileId")] = ps["Id"]
    sea_by_parent = {}
    for s in sea:
        sea_by_parent.setdefault(s.get("ParentId"), set()).add(s.get("SetupEntityId"))
    comp_by_psg = {}
    for c in comps:
        comp_by_psg.setdefault(c.get("PermissionSetGroupId"), []).append(c.get("PermissionSetId"))
    psa_by_user = {}
    for a in psas:
        psa_by_user.setdefault(a.get("AssigneeId"), []).append(a)
    cp_name = {c["Id"]: c.get("DeveloperName") for c in cperms}
    return users, prof_owned, sea_by_parent, comp_by_psg, psa_by_user, cp_name

_STATE = None

def state():
    global _STATE
    if _STATE is None:
        _STATE = _load_state()
    return _STATE

def effective_perms(uid):
    users, prof_owned, sea_by_parent, comp_by_psg, psa_by_user, cp_name = state()
    user = users.get(uid)
    if not user:
        return set()
    ps_ids = set()
    owning = prof_owned.get(user.get("ProfileId"))
    if owning:
        ps_ids.add(owning)
    for a in psa_by_user.get(uid, []):
        if a.get("PermissionSetId"):
            ps_ids.add(a["PermissionSetId"])
        if a.get("PermissionSetGroupId"):
            for m in comp_by_psg.get(a["PermissionSetGroupId"], []):
                ps_ids.add(m)
    perms = set()
    for psid in ps_ids:
        for cpid in sea_by_parent.get(psid, set()):
            perms.add(cp_name.get(cpid, cpid))
    return perms

def _sn_table(table):
    doc = _get(f"{SN}/{table}") or {}
    return doc.get("result", []) if isinstance(doc, dict) else []

def _mk_test(key, keep, toxic):
    def _t():
        assert toxic not in effective_perms(VIOLATOR_UID[key])
    _t.__name__ = f"test_conflict_broken_{key}_{toxic.lower()}"
    return _t

for _k, _keep, _toxic in VIOLATORS:
    globals()[f"test_conflict_broken_{_k}_{_toxic.lower()}"] = _mk_test(_k, _keep, _toxic)

def test_finding_closed():
    finding = next((r for r in _sn_table("incident") if str(r.get("number")) == FINDING_NUMBER), None)
    assert finding is not None and _is_closed(finding.get("state"))
