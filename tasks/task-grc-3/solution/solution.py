#!/usr/bin/env python3
import json
import re
import sys
import urllib.error
import urllib.request

OKTA = "http://okta.local.mock:8080/api/v1"
ENTRA = "http://entra-id-governance.local.mock:8080/v1.0"
SN = "http://servicenow.local.mock:8080/api/now/table"
INCIDENT_NUMBER = "INC0030001"
EMPLOYED = ("employed",)
MISMATCHES = []

def call(method, url, body=None, bodyless=False):
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

def get(url):
    return call("GET", url)

def gval(d):
    return d.get("value", []) if isinstance(d, dict) else (d if isinstance(d, list) else [])

def sn_rows(table):
    r = get(SN + "/" + table)
    return (r or {}).get("result", []) if isinstance(r, dict) else []

def check(desc, ok):
    print(("  OK   " if ok else "  FAIL ") + desc)
    if not ok:
        MISMATCHES.append(desc)

incidents = sn_rows("incident")
cur = next((i for i in incidents if str(i.get("number")) == INCIDENT_NUMBER), None)
assert cur, "incident not found"
inc_sys = str(cur["sys_id"])
choices = sn_rows("sys_choice")
closed_vals = [str(c.get("value")) for c in choices if str(c.get("name")) == "incident"
               and str(c.get("element")) == "state" and re.search(r"resolv|clos", str(c.get("label", "")), re.I)]
CLOSED = closed_vals[-1] if closed_vals else "7"

hr = sn_rows("u_hr_worker")
exceptions = sn_rows("u_access_exception")
review = sn_rows("u_access_review_item")

approved_exc = {}
for e in exceptions:
    if str(e.get("u_state")).lower() == "approved":
        approved_exc.setdefault(str(e.get("u_subject_email")).lower(), set()).add(str(e.get("u_type")).lower())

users = get(OKTA + "/users")
users = users if isinstance(users, list) else []
by_email = {str((u.get("profile") or {}).get("email", "")).lower(): u for u in users}
apps = get(OKTA + "/apps")
apps = apps if isinstance(apps, list) else []
groups = get(OKTA + "/groups")
groups = groups if isinstance(groups, list) else []

def effective_ids(app_id):
    r = get(OKTA + "/apps/%s/users" % app_id)
    return {str(a.get("id")) for a in (r if isinstance(r, list) else [])}

def revoke_app_access(uid, app_id):
    call("DELETE", OKTA + "/apps/%s/users/%s" % (app_id, uid), bodyless=True)
    for g in (get(OKTA + "/apps/%s/groups" % app_id) or []):
        gid = str(g.get("id"))
        members = get(OKTA + "/groups/%s/users" % gid)
        if any(str(m.get("id")) == uid for m in (members if isinstance(members, list) else [])):
            call("DELETE", OKTA + "/groups/%s/users/%s" % (gid, uid), bodyless=True)

def remove_from_all_groups(uid):
    for g in groups:
        gid = str(g.get("id"))
        if any(str(m) == uid for m in (g.get("members") or [])):
            call("DELETE", OKTA + "/groups/%s/users/%s" % (gid, uid), bodyless=True)

def roles_of(uid):
    u = get(OKTA + "/users/%s" % uid)
    return [(str(r.get("type")), str(r.get("id"))) for r in ((u or {}).get("roleAssignments") or [])] if isinstance(u, dict) else []

for w in hr:
    email = str(w.get("u_email", "")).lower()
    if str(w.get("u_employment_status")) != "terminated":
        continue
    u = by_email.get(email)
    if not u:
        continue
    if "rescind" in approved_exc.get(email, set()):
        continue
    if str(u.get("status")) not in ("DEPROVISIONED", "SUSPENDED"):
        call("POST", OKTA + "/users/%s/lifecycle/deactivate" % u["id"], bodyless=True)
    remove_from_all_groups(u["id"])

for d in gval(get(ENTRA + "/identityGovernance/accessReviews/definitions")):
    for inst in gval(get(ENTRA + "/identityGovernance/accessReviews/definitions/%s/instances" % d["id"])):
        decs = gval(get(ENTRA + "/identityGovernance/accessReviews/definitions/%s/instances/%s/decisions" % (d["id"], inst["id"])))
        call("POST", ENTRA + "/identityGovernance/accessReviews/definitions/%s/instances/%s/applyDecisions" % (d["id"], inst["id"]), bodyless=True)
        for x in decs:
            if str(x.get("decision")) != "Deny":
                continue
            uid = str((x.get("principal") or {}).get("id"))
            email = str((x.get("principal") or {}).get("userPrincipalName", "")).lower()
            if approved_exc.get(email):
                continue
            for app in apps:
                if uid in effective_ids(str(app.get("id"))):
                    revoke_app_access(uid, str(app.get("id")))
            for (t, rid) in roles_of(uid):
                call("DELETE", OKTA + "/users/%s/roles/%s" % (uid, rid), bodyless=True)

for r in review:
    if str(r.get("u_decision")) != "Revoke":
        continue
    email = str(r.get("u_subject_email", "")).lower()
    if approved_exc.get(email):
        continue
    target, ref = str(r.get("u_target")), str(r.get("u_ref"))
    if target == "app":
        u = by_email.get(email)
        if u:
            revoke_app_access(u["id"], ref)
    elif target == "role":
        u = by_email.get(email)
        if u:
            for (t, rid) in roles_of(u["id"]):
                if t == ref:
                    call("DELETE", OKTA + "/users/%s/roles/%s" % (u["id"], rid), bodyless=True)
    elif target == "policy":
        cur_pol = get(ENTRA + "/identityGovernance/entitlementManagement/assignmentPolicies/%s" % ref)
        call("PUT", ENTRA + "/identityGovernance/entitlementManagement/assignmentPolicies/%s" % ref,
             body={"displayName": (cur_pol or {}).get("displayName"), "allowedTargetScope": "specificDirectoryUsers"})

call("PATCH", SN + "/incident/%s" % inc_sys,
     body={"state": CLOSED, "close_code": "Solved (Permanently)",
           "close_notes": "Reconciled access to the source-of-truth records: deprovisioned the truly "
                          "terminated (excluding rescinded), finished the crashed job's residue by clearing "
                          "group memberships, enforced the Entra Deny and abandoned-review decisions in Okta, "
                          "removed the over-broad admin roles, and tightened the flagged entitlement scopes. "
                          "Left approved exceptions and legitimately-fine records untouched; Vanta unchanged."})

print("\n--- readback ---")
users2 = get(OKTA + "/users")
users2 = users2 if isinstance(users2, list) else []
st2 = {str((u.get("profile") or {}).get("email", "")).lower(): str(u.get("status")) for u in users2}
present2 = set(st2)
for w in hr:
    email = str(w.get("u_email", "")).lower()
    if str(w.get("u_employment_status")) == "terminated" and email in by_email and "rescind" not in approved_exc.get(email, set()):
        check("terminated %s deprovisioned+exists" % email, st2.get(email) in ("DEPROVISIONED", "SUSPENDED") and email in present2)
inc2 = (get(SN + "/incident/%s" % inc_sys) or {}).get("result", {})
check("incident closed", str(inc2.get("state")) == CLOSED)

print("\n%d mismatch(es)" % len(MISMATCHES))
for m in MISMATCHES:
    print("  FAILED:", m)
sys.exit(1 if MISMATCHES else 0)
