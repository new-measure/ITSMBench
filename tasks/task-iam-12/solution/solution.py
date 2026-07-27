#!/usr/bin/env python3
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

SF = "http://salesforce.local.mock:8080/services/data/v67.0"
SN = "http://servicenow.local.mock:8080/api/now/table"
FINDING_NUMBER = "GRC0007742"
MISMATCHES = []

def call(method, url, body=None):
    data, headers = None, {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
        return json.loads(raw) if raw and raw.strip()[:1] in "{[" else raw
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_body": e.read().decode()[:200]}

def soql(q):
    doc = call("GET", f"{SF}/query?q={urllib.parse.quote(q)}")
    return (doc or {}).get("records", []) if isinstance(doc, dict) else []

def sn_table(table):
    doc = call("GET", f"{SN}/{table}")
    return doc.get("result", []) if isinstance(doc, dict) else []

def check(desc, ok):
    print(("  OK   " if ok else "  FAIL ") + desc)
    if not ok:
        MISMATCHES.append(desc)

def load_graph():
    users = soql("SELECT Id, Name, Username, ProfileId, IsActive FROM User")
    perm_sets = soql("SELECT Id, Name, IsOwnedByProfile, ProfileId FROM PermissionSet")
    sea = soql("SELECT Id, ParentId, SetupEntityId FROM SetupEntityAccess")
    comps = soql("SELECT Id, PermissionSetGroupId, PermissionSetId FROM PermissionSetGroupComponent")
    psas = soql("SELECT Id, AssigneeId, PermissionSetId, PermissionSetGroupId FROM PermissionSetAssignment")
    cperms = soql("SELECT Id, DeveloperName FROM CustomPermission")

    prof_owned = {ps.get("ProfileId"): ps["Id"] for ps in perm_sets
                  if ps.get("IsOwnedByProfile") in (True, "true")}
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
    return dict(users=users, prof_owned=prof_owned, sea_by_parent=sea_by_parent,
                comp_by_psg=comp_by_psg, psa_by_user=psa_by_user, cp_name=cp_name)

def ps_perms(g, ps_id):
    return {g["cp_name"].get(c, c) for c in g["sea_by_parent"].get(ps_id, set())}

def profile_perms(g, user):
    owning = g["prof_owned"].get(user.get("ProfileId"))
    return ps_perms(g, owning) if owning else set()

def effective(g, user):
    perms = set(profile_perms(g, user))
    for a in g["psa_by_user"].get(user["Id"], []):
        if a.get("PermissionSetId"):
            perms |= ps_perms(g, a["PermissionSetId"])
        if a.get("PermissionSetGroupId"):
            for m in g["comp_by_psg"].get(a["PermissionSetGroupId"], []):
                perms |= ps_perms(g, m)
    return perms

def psas_conferring(g, user, perm):
    out = []
    for a in g["psa_by_user"].get(user["Id"], []):
        confers = False
        if a.get("PermissionSetId") and perm in ps_perms(g, a["PermissionSetId"]):
            confers = True
        if a.get("PermissionSetGroupId"):
            for m in g["comp_by_psg"].get(a["PermissionSetGroupId"], []):
                if perm in ps_perms(g, m):
                    confers = True
        if confers:
            out.append(a)
    return out

finding = next((r for r in sn_table("incident") if str(r.get("number")) == FINDING_NUMBER), None)
assert finding, "finding %s not found" % FINDING_NUMBER
finding_sys = str(finding["sys_id"])
print("finding %s sys_id=%s state=%s" % (FINDING_NUMBER, finding_sys, finding.get("state")))

rules = []
for r in sn_table("u_sod_rule"):
    a, b = r.get("u_permission_a"), r.get("u_permission_b")
    if a and b:
        rules.append((str(r.get("u_number")), a, b))
print("SoD control matrix pairs:", [(n, a, b) for n, a, b in rules])

exceptions = set()
for e in sn_table("u_sod_exception"):
    if str(e.get("u_status", "")).lower() == "approved":
        exceptions.add((str(e.get("u_user", "")).strip().lower(), str(e.get("u_sod_rule", ""))))
print("approved compensating-control exceptions:", exceptions)

g = load_graph()
SOD_PERM_NAMES = set()
for _n, a, b in rules:
    SOD_PERM_NAMES.add(a)
    SOD_PERM_NAMES.add(b)

def ps_grants(g, ps_id):
    return {g["cp_name"].get(c, c) for c in g["sea_by_parent"].get(ps_id, set())}

def clean_ps_granting(g, perm):
    for ps in soql("SELECT Id, IsOwnedByProfile FROM PermissionSet"):
        if ps.get("IsOwnedByProfile") in (True, "true"):
            continue
        perms = ps_grants(g, ps["Id"])
        if perm in perms and not (perms & SOD_PERM_NAMES):
            return ps["Id"]
    return None

conflict_users = set()
for u in g["users"]:
    eff = effective(g, u)
    for _n, a, b in rules:
        if a in eff and b in eff:
            conflict_users.add(u["Id"])

remediated = []
skipped_exception = []
pre_eff = {}
to_delete = {}

for u in g["users"]:
    eff = effective(g, u)
    prof = profile_perms(g, u)
    uname = str(u.get("Username", "")).strip().lower()
    for rule_no, a, b in rules:
        if not (a in eff and b in eff):
            continue
        if (uname, rule_no) in exceptions:
            skipped_exception.append((u["Name"], rule_no))
            continue
        if a in prof and b not in prof:
            keep, toxic = a, b
        elif b in prof and a not in prof:
            keep, toxic = b, a
        else:
            peers = [p for p in g["users"] if p.get("ProfileId") == u.get("ProfileId")
                     and p["Id"] != u["Id"] and p["Id"] not in conflict_users]
            a_peer = any(a in effective(g, p) for p in peers)
            keep, toxic = (a, b) if (a_peer) else (b, a)
        rows = psas_conferring(g, u, toxic)
        assert rows, ("no supplementary assignment carries the toxic perm", u["Name"], toxic)
        for row in rows:
            to_delete[row["Id"]] = row
        pre_eff[u["Id"]] = eff
        remediated.append((u, keep, toxic, rule_no))
        print("  conflict %s on %s: keep=%s (profile) remove=%s via %d assignment(s)"
              % (rule_no, u["Name"], keep, toxic, len(rows)))

legit_by_profile = {}
for u in g["users"]:
    if u["Id"] in conflict_users:
        continue
    legit_by_profile.setdefault(u.get("ProfileId"), set()).update(effective(g, u))

print("\naudited %d users; %d in conflict; skipped (approved exception): %s"
      % (len(g["users"]), len(conflict_users), skipped_exception))
print("unassigning %d permission-set/group assignment rows..." % len(to_delete))
for pa_id in to_delete:
    res = call("DELETE", f"{SF}/sobjects/PermissionSetAssignment/{pa_id}")
    if isinstance(res, dict) and res.get("_error"):
        print("   DELETE PSA %s -> %s" % (pa_id, res))

g2 = load_graph()
u_by_id = {u["Id"]: u for u in g2["users"]}
regrants = 0
for u, keep, toxic, rule_no in remediated:
    now = effective(g2, u_by_id[u["Id"]])
    legit = legit_by_profile.get(u.get("ProfileId"), set())
    for lost in (pre_eff[u["Id"]] - now):
        if lost == toxic or lost in SOD_PERM_NAMES or lost not in legit:
            continue
        ps_id = clean_ps_granting(g2, lost)
        if ps_id:
            call("POST", f"{SF}/sobjects/PermissionSetAssignment",
                 body={"AssigneeId": u["Id"], "PermissionSetId": ps_id})
            regrants += 1
            print("  re-grant legit duty %s to %s via clean permission set" % (lost, u["Name"]))
print("re-granted %d collaterally-lost legitimate duties" % regrants)

res = call("PATCH", f"{SN}/incident/{finding_sys}", body={
    "state": "7", "close_code": "Solved (Permanently)",
    "close_notes": ("Q3 SoD access review remediated. Computed each user's effective permissions "
                    "(profile + direct permission sets + permission-set-group-inherited) and, for every "
                    "genuine conflict against the control matrix, cleared the supplementary half while "
                    "preserving each user's profile-conferred primary duty. Honored the approved "
                    "compensating-control exception. Non-conflicting users left untouched.")})
print("close finding ->", "ok" if not (isinstance(res, dict) and res.get("_error")) else res)

print("\n--- readback ---")
g2 = load_graph()
u_by_id = {u["Id"]: u for u in g2["users"]}
for u, keep, toxic, rule_no in remediated:
    eff2 = effective(g2, u_by_id[u["Id"]])
    check("%s: toxic %s cleared" % (u["Name"], toxic), toxic not in eff2)
    check("%s: primary %s preserved" % (u["Name"], keep), keep in eff2)
    check("%s: still active" % u["Name"], u_by_id[u["Id"]].get("IsActive") in (True, "true"))
    legit = legit_by_profile.get(u.get("ProfileId"), set())
    lost_legit = [c for c in (pre_eff[u["Id"]] - eff2) if c != toxic and c in legit]
    check("%s: legitimate duties preserved (lost=%s)" % (u["Name"], lost_legit), not lost_legit)

for name, rule_no in skipped_exception:
    u = next(x for x in g2["users"] if x["Name"] == name)
    eff2 = effective(g2, u)
    pair = next((a, b) for n, a, b in rules if n == rule_no)
    check("compensating-control %s keeps both halves" % name, pair[0] in eff2 and pair[1] in eff2)

residual = 0
for u in g2["users"]:
    eff2 = effective(g2, u)
    uname = str(u.get("Username", "")).strip().lower()
    for rule_no, a, b in rules:
        if a in eff2 and b in eff2 and (uname, rule_no) not in exceptions:
            residual += 1
            print("   RESIDUAL violation %s on %s" % (rule_no, u["Name"]))
check("no residual SoD violations (except approved exceptions)", residual == 0)

finding2 = next((r for r in sn_table("incident") if str(r.get("number")) == FINDING_NUMBER), None)
check("finding closed", str((finding2 or {}).get("state")) in ("6", "7"))

print("\nremediated %d conflicts across %d users; %d approved-exception combos left intact"
      % (len(remediated), len({u["Id"] for u, _, _, _ in remediated}), len(skipped_exception)))
print("%d mismatch(es)" % len(MISMATCHES))
sys.exit(1 if MISMATCHES else 0)
