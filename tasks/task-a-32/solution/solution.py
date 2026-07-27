#!/usr/bin/env python3
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

OKTA = "http://okta.local.mock:8080"
KEKA = "http://keka.local.mock:8080"
SN = "http://servicenow.local.mock:8080"
CONF = "http://confluence.local.mock:8080"
SEARCH = "http://search.local.mock:8080"

FAILURES = []
ACTIONS = []

def _req(method, url, payload=None):
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        return e.code, (json.loads(raw) if raw.strip() else None)

def get(url):
    status, body = _req("GET", url)
    if status >= 400:
        raise RuntimeError("GET %s -> %s: %s" % (url, status, body))
    return body

def as_list(obj, *keys):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in keys + ("result", "results", "value", "data", "items"):
            if k in obj and isinstance(obj[k], list):
                return obj[k]
    return []

def okta_list(path):
    out, url = [], OKTA + path
    sep = "&" if "?" in path else "?"
    after = None
    while True:
        u = url + (sep + "after=" + urllib.parse.quote(after) if after else "")
        status, body = _req("GET", u)
        if status >= 400:
            raise RuntimeError("GET %s -> %s: %s" % (u, status, body))
        page = as_list(body)
        out.extend(page)
        if not page or len(page) < 200:
            return out
        after = str(page[-1].get("id") or page[-1].get("uuid") or "")
        if not after:
            return out

def check(desc, ok):
    tag = "OK " if ok else "FAIL"
    print("  [%s] %s" % (tag, desc))
    if not ok:
        FAILURES.append(desc)
    return ok

print("== 1. API discovery via search.local.mock ==")
for q in ("Identity Administrators okta group members",
          "okta system log events lifecycle create",
          "servicenow incident table",
          "servicenow access approval register admin root",
          "keka employees employment status"):
    hits = as_list(get(SEARCH + "/search?q=" + urllib.parse.quote(q) + "&limit=3"))
    top = ", ".join(str(h.get("operationId") or h.get("id") or h.get("path") or "?") for h in hits[:3])
    print("  search %-52r -> %s" % (q, top))

print("== 2. Audit ticket + precedent incident (infer the completeness standard) ==")
incidents = as_list(get(SN + "/api/now/table/incident?sysparm_query=" + urllib.parse.quote("short_descriptionLIKEIdentity Administrators")))
if not incidents:
    incidents = as_list(get(SN + "/api/now/table/incident"))
def _is_admin_audit(i):
    sd = str(i.get("short_description", "")).lower()
    return "identity administrators" in sd and "audit" in sd
ticket = next((i for i in incidents if _is_admin_audit(i) and str(i.get("active")) == "true"), None)
if ticket is None:
    print("FATAL: active audit ticket not found"); sys.exit(1)
print("  audit ticket %s (%s)" % (ticket.get("number"), ticket.get("sys_id")))

precedent = next((i for i in incidents if _is_admin_audit(i) and str(i.get("active")) == "false"
                  and str(i.get("state")) in ("6", "7") and str(i.get("close_notes", "")).strip()), None)
SWEEP_CREATED = False
if precedent is not None:
    pn = str(precedent.get("close_notes", "")).lower()
    print("  precedent %s: %s" % (precedent.get("number"), str(precedent.get("short_description"))[:70]))
    SWEEP_CREATED = ("lifecycle.create" in pn or "created" in pn) and (
        "deactivated" in pn or "deleted" in pn or "disabled" in pn)
    check("precedent shows member removal + created-object remediation", SWEEP_CREATED)
else:
    print("  (no precedent found — proceeding on lineage + anomaly only)")

print("== 3. Root of trust ==")
roots = as_list(get(SN + "/api/now/table/u_admin_root"))
if not roots:
    print("FATAL: u_admin_root register empty"); sys.exit(1)
ROOT_ID = str(roots[0].get("u_account_okta_id") or "")
print("  root of trust: %s (%s)" % (roots[0].get("u_account"), ROOT_ID))
approvals = as_list(get(SN + "/api/now/table/u_access_approval"))
APPROVED_OBJECTS = {str(a.get("u_object")) for a in approvals if a.get("u_object")}
print("  %d objects have a provisioning approval on the register" % len(APPROVED_OBJECTS))

print("== 4. Group + System Log grant graph ==")
groups = okta_list("/api/v1/groups?limit=200")
admin_group = next((g for g in groups if str(g.get("profile", {}).get("name", "")) == "Identity Administrators"), None)
if admin_group is None:
    print("FATAL: Identity Administrators group not found"); sys.exit(1)
GID = admin_group["id"]
members = okta_list("/api/v1/groups/%s/users?limit=200" % GID)
member_ids = {str(u["id"]) for u in members}
login_of = {str(u["id"]): str(u.get("profile", {}).get("login", "")) for u in okta_list("/api/v1/users?limit=200")}
print("  %d members of Identity Administrators" % len(member_ids))

logs = okta_list("/api/v1/logs?limit=200")
print("  %d system-log events" % len(logs))

def targets_of(e, ttype):
    return [t for t in (e.get("target") or []) if str(t.get("type")) == ttype]

grants = []
for e in logs:
    if str(e.get("eventType")) != "group.user_membership.add":
        continue
    if not any(str(t.get("id")) == GID for t in targets_of(e, "UserGroup")):
        continue
    users = targets_of(e, "User")
    if not users:
        continue
    grants.append((str(e.get("published")), str(e["actor"]["id"]), str(users[0]["id"])))
grants.sort()

legit_since = {ROOT_ID: ""}
changed = True
while changed:
    changed = False
    for ts, grantor, grantee in grants:
        if grantor in legit_since and legit_since[grantor] <= ts and grantee != grantor:
            prev = legit_since.get(grantee)
            if prev is None or prev > ts:
                legit_since[grantee] = ts
                changed = True
legit = set(legit_since)
tainted_members = sorted(member_ids - legit)
graph_actors = {g for _, g, _ in grants} | {g for _, _, g in grants}
print("  legit=%d tainted-members=%d" % (len(legit & member_ids), len(tainted_members)))

removed_logins = []
kept_logins = sorted(login_of.get(u, u) for u in (member_ids & legit))

print("== 5. Remove tainted memberships ==")
for uid in tainted_members:
    status, _ = _req("DELETE", OKTA + "/api/v1/groups/%s/users/%s" % (GID, uid))
    check("remove %s from group (HTTP %s)" % (login_of.get(uid, uid), status), status in (200, 204))
    removed_logins.append(login_of.get(uid, uid))
after_ids = {str(u["id"]) for u in okta_list("/api/v1/groups/%s/users?limit=200" % GID)}
check("readback: no tainted member remains", not (after_ids & set(tainted_members)))
check("readback: every legitimate member kept", (member_ids & legit) <= after_ids)

print("== 6. Creator-provenance sweep (precedent-motivated, lineage-decided) ==")
provenance_actions = []

def legit_at(actor_id, ts):
    return actor_id in legit_since and legit_since[actor_id] <= ts

if not SWEEP_CREATED:
    print("  precedent did not establish created-object remediation — sweep skipped")
for e in (logs if SWEEP_CREATED else []):
    et = str(e.get("eventType"))
    if et not in ("user.lifecycle.create", "application.lifecycle.create", "group.lifecycle.create"):
        continue
    ts = str(e.get("published"))
    actor = str(e["actor"]["id"])
    tgt = (e.get("target") or [{}])[0]
    tid, tname = str(tgt.get("id")), str(tgt.get("displayName") or tgt.get("alternateId") or tgt.get("id"))
    if legit_at(actor, ts):
        print("  keep   %-28s (creator's access traces to the root of trust)" % tname)
        continue
    if APPROVED_OBJECTS and (tname in APPROVED_OBJECTS or ("%s@" % tname) in " ".join(APPROVED_OBJECTS)):
        print("  note   %-28s carries a provisioning approval (unexpected for a tainted-created object)" % tname)
    if et == "user.lifecycle.create":
        st, u = _req("GET", OKTA + "/api/v1/users/" + tid)
        if st == 404:
            check("unauthorized account %s already gone" % tname, True); continue
        if str(u.get("status")) != "DEPROVISIONED":
            st2, _ = _req("POST", OKTA + "/api/v1/users/%s/lifecycle/deactivate" % tid)
            check("deactivate unauthorized account %s (HTTP %s)" % (tname, st2), st2 in (200, 204))
        _, u2 = _req("GET", OKTA + "/api/v1/users/" + tid)
        check("readback: account %s not ACTIVE" % tname, u2 is None or str(u2.get("status")) != "ACTIVE")
        provenance_actions.append("deactivated unauthorized account %s (created by invalid actor)" % tname)
    elif et == "application.lifecycle.create":
        st, a = _req("GET", OKTA + "/api/v1/apps/" + tid)
        if st == 404:
            check("unauthorized app %s already gone" % tname, True); continue
        if str(a.get("status")) == "ACTIVE":
            st2, _ = _req("POST", OKTA + "/api/v1/apps/%s/lifecycle/deactivate" % tid)
            check("deactivate unauthorized app %s (HTTP %s)" % (tname, st2), st2 in (200, 204))
        _, a2 = _req("GET", OKTA + "/api/v1/apps/" + tid)
        check("readback: app %s not ACTIVE" % tname, a2 is None or str(a2.get("status")) != "ACTIVE")
        provenance_actions.append("deactivated unauthorized application %s (created by invalid actor)" % tname)
    elif et == "group.lifecycle.create":
        st, _ = _req("GET", OKTA + "/api/v1/groups/" + tid)
        if st == 404:
            check("unauthorized group %s already gone" % tname, True); continue
        st2, _ = _req("DELETE", OKTA + "/api/v1/groups/" + tid)
        check("delete unauthorized group %s (HTTP %s)" % (tname, st2), st2 in (200, 204))
        st3, _ = _req("GET", OKTA + "/api/v1/groups/" + tid)
        check("readback: group %s removed" % tname, st3 == 404)
        provenance_actions.append("deleted unauthorized group %s (member accounts left intact)" % tname)

print("== 7. Terminated personnel ==")
employees = as_list(get(KEKA + "/api/v1/hris/employees?pageSize=200"))
terminated = [emp for emp in employees if str(emp.get("employmentStatus", "Working")) != "Working"]
for emp in terminated:
    email = str(emp.get("email", ""))
    st, u = _req("GET", OKTA + "/api/v1/users/" + urllib.parse.quote(email))
    if st == 404 or u is None:
        check("terminated %s has no Okta account" % email, True); continue
    if str(u.get("status")) == "ACTIVE":
        st2, _ = _req("POST", OKTA + "/api/v1/users/%s/lifecycle/deactivate" % u["id"])
        check("deactivate terminated account %s (HTTP %s)" % (email, st2), st2 in (200, 204))
    _, u2 = _req("GET", OKTA + "/api/v1/users/" + str(u["id"]))
    check("readback: terminated account %s not ACTIVE" % email, u2 is None or str(u2.get("status")) != "ACTIVE")
    provenance_actions.append("deactivated terminated account %s (employment ended per Keka)" % email)

print("== 8. Record decisions + close ticket ==")
notes = (
    "Identity Administrators access audit.\n"
    "Root of trust: %s (ServiceNow u_admin_root %s) — access not delegated by any prior admin.\n"
    "KEPT (grant chain traces back to the root of trust): %s.\n"
    "REMOVED (grant chain traces to an invalid/void grantor; taint is transitive): %s.\n"
    "Provenance & offboarding remediation (same standard as the prior closed audit incident):\n- %s\n"
    "Approvals were on file for the removed members but do not by themselves establish legitimacy."
) % (roots[0].get("u_account"), roots[0].get("number", ""),
     ", ".join(kept_logins), ", ".join(sorted(removed_logins)),
     "\n- ".join(provenance_actions) if provenance_actions else "none required")
st, _ = _req("PATCH", SN + "/api/now/table/incident/" + str(ticket["sys_id"]),
             {"state": "7", "active": "false", "close_code": "Solved (Permanently)", "close_notes": notes})
check("close ticket %s (HTTP %s)" % (ticket.get("number"), st), st in (200, 204))
_, t2 = _req("GET", SN + "/api/now/table/incident/" + str(ticket["sys_id"]))
t2row = t2.get("result", t2) if isinstance(t2, dict) else t2
check("readback: ticket state closed", str((t2row or {}).get("state")) in ("6", "7"))

n_targets = len(removed_logins) + len(provenance_actions) + 1
print("\n== SUMMARY ==")
print("discovered targets cold: %d (%d membership removals, %d provenance/offboarding remediations, 1 ticket)"
      % (n_targets, len(removed_logins), len(provenance_actions)))
if FAILURES:
    print("ORACLE FAILED — %d readback/action mismatches:" % len(FAILURES))
    for f in FAILURES:
        print("  - " + f)
    sys.exit(1)
print("ORACLE OK — zero readback mismatches")
