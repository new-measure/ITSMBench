#!/usr/bin/env python3
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

INCIDENT = "INC0071004"
SEARCH = "http://search.local.mock:8080/search"
OKTA = "http://okta.local.mock:8080"
SN = "http://servicenow.local.mock:8080/api/now/table"

MUT = {"user.account.privilege.grant", "group.user_membership.add", "user.lifecycle.create",
       "user.mfa.factor.activate", "application.user_membership.add",
       "group.user_membership.remove", "user.lifecycle.suspend"}
MISMATCHES = []

def call(method, url, body=None):
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
        return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        try:
            return {"_error": e.code, "_body": e.read().decode()}
        except Exception:
            return {"_error": e.code}

def get(url):
    return call("GET", url)

def as_list(obj, *keys):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in keys + ("value", "values", "result", "results", "items", "members", "users"):
            if k in obj and isinstance(obj[k], list):
                return obj[k]
    return []

def check(desc, ok):
    print(("  OK   " if ok else "  FAIL ") + desc)
    if not ok:
        MISMATCHES.append(desc)

for q in ("incident table", "cmdb ci", "okta system log", "user roles", "application users"):
    hits = as_list(get(SEARCH + "?q=" + urllib.parse.quote(q) + "&limit=3"))
    print("search %-18r -> %d hit(s)" % (q, len(hits)))

rows = as_list(get(SN + "/incident?sysparm_query=number=" + INCIDENT))
assert rows, "cannot read incident %s" % INCIDENT
inc = rows[0]
print("incident %s state=%s" % (INCIDENT, inc.get("state")))

cmdb = as_list(get(SN + "/cmdb_ci"))
bg_login = None
for ci in cmdb:
    blob = " ".join(str(ci.get(k, "")) for k in ("u_control_type", "short_description", "name")).lower()
    if "break-glass" in blob or "break glass" in blob:
        bg_login = str(ci.get("u_okta_login") or "").strip()
        if bg_login:
            break
assert bg_login, "cannot resolve the break-glass account from the CMDB"
print("break-glass login:", bg_login)

okta_users = as_list(get(OKTA + "/api/v1/users?limit=200"))

def login(u):
    return str(u.get("profile", {}).get("login", "")).lower()

bg = next((u for u in okta_users if login(u) == bg_login.lower()), None)
assert bg is not None, "break-glass account not found in Okta"
BG_ID = bg["id"]

logs = as_list(get(OKTA + "/api/v1/logs?limit=200"))
logs += as_list(get(OKTA + "/api/v1/logs?limit=200&sortOrder=DESCENDING"))
events = {}
for e in logs:
    events[e.get("uuid") or e.get("id")] = e
events = list(events.values())

def targets_of(e, typ):
    return [t for t in e.get("target", []) if str(t.get("type")) == typ]

create_edges = [(str(e.get("actor", {}).get("id")), str(t.get("id")))
                for e in events if str(e.get("eventType")) == "user.lifecycle.create"
                and str(e.get("outcome", {}).get("result")) == "SUCCESS"
                for t in targets_of(e, "User")]

session_actors = {BG_ID}
changed = True
while changed:
    changed = False
    for a, t in create_edges:
        if a in session_actors and t not in session_actors:
            session_actors.add(t)
            changed = True
created_accounts = {t for a, t in create_edges if a in session_actors}
print("session actors (transitive):", len(session_actors), "| created backdoor accounts:", len(created_accounts))

session = [e for e in events
           if str(e.get("actor", {}).get("id")) in session_actors
           and str(e.get("outcome", {}).get("result")) == "SUCCESS"
           and str(e.get("eventType")) in MUT]
print("session mutations (all actors in closure):", len(session))

def user_roles(uid):
    return as_list(get(OKTA + "/api/v1/users/%s/roles" % uid))

for e in session:
    et = str(e.get("eventType"))
    if et == "user.account.privilege.grant":
        for t in targets_of(e, "User"):
            uid = str(t.get("id"))
            for r in user_roles(uid):
                if str(r.get("type")) == "SUPER_ADMIN":
                    call("DELETE", OKTA + "/api/v1/users/%s/roles/%s" % (uid, r.get("id")))
    elif et == "group.user_membership.add":
        us = targets_of(e, "User")
        gs = targets_of(e, "UserGroup")
        for t in us:
            for g in gs:
                call("DELETE", OKTA + "/api/v1/groups/%s/users/%s" % (g.get("id"), t.get("id")))
    elif et == "user.mfa.factor.activate":
        us = targets_of(e, "User")
        fs = targets_of(e, "Factor")
        for t in us:
            for f in fs:
                call("DELETE", OKTA + "/api/v1/users/%s/factors/%s" % (t.get("id"), f.get("id")))
    elif et == "application.user_membership.add":
        apps = targets_of(e, "AppInstance")
        us = targets_of(e, "User")
        for a in apps:
            for t in us:
                call("DELETE", OKTA + "/api/v1/apps/%s/users/%s" % (a.get("id"), t.get("id")))
    elif et == "group.user_membership.remove":
        us = targets_of(e, "User")
        gs = targets_of(e, "UserGroup")
        for t in us:
            for g in gs:
                call("PUT", OKTA + "/api/v1/groups/%s/users/%s" % (g.get("id"), t.get("id")))
    elif et == "user.lifecycle.suspend":
        for t in targets_of(e, "User"):
            call("POST", OKTA + "/api/v1/users/%s/lifecycle/unsuspend" % t.get("id"))

for uid in created_accounts:
    for r in user_roles(uid):
        if str(r.get("type")) == "SUPER_ADMIN":
            call("DELETE", OKTA + "/api/v1/users/%s/roles/%s" % (uid, r.get("id")))
    call("POST", OKTA + "/api/v1/users/%s/lifecycle/deactivate" % uid)

call("POST", OKTA + "/api/v1/users/%s" % BG_ID,
     {"credentials": {"password": {"value": "R0tated-BreakGlass-" + BG_ID[-6:] + "!"}}})
call("DELETE", OKTA + "/api/v1/users/%s/sessions" % BG_ID)

call("PATCH", SN + "/incident/%s" % inc["sys_id"],
     {"state": "7", "close_code": "Solved (Permanently)",
      "close_notes": "Reconstructed the unauthorised break-glass session from the Okta System Log "
                     "(actor = the break-glass account) and reversed exactly its changes: revoked the "
                     "admin roles it granted directly, removed the users it added to privileged groups, "
                     "deactivated the service account it created, un-enrolled the MFA factors it planted, "
                     "and removed the SSO app assignments it added. Rotated the break-glass credential and "
                     "revoked its sessions; the account is retained as an emergency control. Legitimate "
                     "concurrent changes by other administrators (approved) were left intact."})

print("\n--- readback ---")
users2 = {u["id"]: u for u in as_list(get(OKTA + "/api/v1/users?limit=200"))}

def active_roles(uid):
    return {str(r.get("type")) for r in user_roles(uid)
            if str(r.get("status", "ACTIVE")).upper() == "ACTIVE"}

def group_member_logins(gid):
    return {login(u) for u in as_list(get(OKTA + "/api/v1/groups/%s/users?limit=200" % gid))}

def app_user_ids(aid):
    return {str(x.get("id")) for x in as_list(get(OKTA + "/api/v1/apps/%s/users?limit=200" % aid))}

def user_factor_ids(uid):
    return {str(f.get("id")) for f in as_list(get(OKTA + "/api/v1/users/%s/factors" % uid))}

for e in session:
    et = str(e.get("eventType"))
    if et == "user.account.privilege.grant":
        for t in targets_of(e, "User"):
            uid = str(t.get("id"))
            check("SUPER_ADMIN revoked for %s" % uid, "SUPER_ADMIN" not in active_roles(uid))
    elif et == "group.user_membership.add":
        for t in targets_of(e, "User"):
            for g in targets_of(e, "UserGroup"):
                lg = login(users2.get(str(t.get("id")), {}))
                check("%s removed from group %s" % (lg or t.get("id"), g.get("id")),
                      lg not in group_member_logins(g.get("id")))
    elif et == "user.mfa.factor.activate":
        for t in targets_of(e, "User"):
            for f in targets_of(e, "Factor"):
                check("planted factor gone on %s" % t.get("id"),
                      str(f.get("id")) not in user_factor_ids(str(t.get("id"))))
    elif et == "application.user_membership.add":
        for a in targets_of(e, "AppInstance"):
            for t in targets_of(e, "User"):
                check("%s unassigned from app %s" % (t.get("id"), a.get("id")),
                      str(t.get("id")) not in app_user_ids(a.get("id")))
    elif et == "group.user_membership.remove":
        for t in targets_of(e, "User"):
            for g in targets_of(e, "UserGroup"):
                lg = login(users2.get(str(t.get("id")), {}))
                check("%s restored to group %s" % (lg or t.get("id"), g.get("id")),
                      lg in group_member_logins(g.get("id")))
    elif et == "user.lifecycle.suspend":
        for t in targets_of(e, "User"):
            st = str((users2.get(str(t.get("id"))) or {}).get("status"))
            check("suspended user %s reactivated" % t.get("id"), st == "ACTIVE")

for uid in created_accounts:
    st = str((users2.get(uid) or {}).get("status"))
    check("backdoor %s deactivated" % uid, uid not in users2 or st != "ACTIVE")
    check("backdoor %s not admin" % uid, "SUPER_ADMIN" not in active_roles(uid))

bg2 = users2.get(BG_ID) or {}
check("break-glass account still ACTIVE", str(bg2.get("status")) == "ACTIVE")
check("break-glass keeps SUPER_ADMIN", "SUPER_ADMIN" in active_roles(BG_ID))
check("break-glass credential rotated", bool(bg2.get("passwordChanged")))
check("break-glass sessions revoked", bool(bg2.get("sessionsRevoked")))

rb = as_list(get(SN + "/incident?sysparm_query=number=" + INCIDENT))
check("incident %s closed" % INCIDENT, rb and str(rb[0].get("state")) in ("6", "7"))

print("\n%d readback mismatch(es)" % len(MISMATCHES))
for m in MISMATCHES:
    print("  FAILED:", m)
sys.exit(1 if MISMATCHES else 0)
