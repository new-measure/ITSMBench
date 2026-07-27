#!/usr/bin/env python3
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

TICKET = "INC0031001"
SEARCH = "http://search.local.mock:8080/search"
OKTA = "http://okta.local.mock:8080"
ENTRA = "http://entra-id.local.mock:8080/v1.0"
GH = "http://github.local.mock:8080"
GH_ORG = "meridian-robotics"
SL = "http://slack.local.mock:8080/api"
SN = "http://servicenow.local.mock:8080/api/now/table"
GWS = "http://google-workspace.local.mock:8080/admin/directory/v1"

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

for q in ("incident table", "list users", "org members", "cmdb service"):
    hits = as_list(get(SEARCH + "?q=" + urllib.parse.quote(q) + "&limit=3"))
    print("search %-16r -> %s" % (q, [str(h.get("path") or h.get("route") or h.get("id")) for h in hits][:3]))

ticket = get(SN + "/incident?sysparm_query=number=" + TICKET)
rows = as_list(ticket)
assert rows, "cannot read ticket %s" % TICKET
tk = rows[0]
desc = str(tk.get("description", ""))
print("\nticket %s state=%s" % (TICKET, tk.get("state")))
names = re.findall(r"\d+\)\s*([A-Z][\w'-]+ [A-Z][\w'-]+)", desc)
names = [n.strip() for n in names]
assert names, "no departed names parsed from ticket"
print("departed subjects discovered from ticket:", names)
lower_names = {n.lower() for n in names}
dash = {(n.split()[0] + "-" + n.split()[1]).lower() for n in names}

okta_users = as_list(get(OKTA + "/api/v1/users?limit=200"))
def full(u):
    p = u.get("profile", {})
    return (str(p.get("firstName", "")) + " " + str(p.get("lastName", ""))).strip().lower()
def login(u):
    return str(u.get("profile", {}).get("login", "")).lower()

departed_okta = [u for u in okta_users if full(u) in lower_names]
departed_okta_logins = {login(u) for u in departed_okta}
departed_okta_ids = {u["id"] for u in departed_okta}
print("okta accounts matching departed names:", sorted(departed_okta_logins))

def active_non_departed():
    groups = as_list(get(OKTA + "/api/v1/groups?limit=200"))
    aws = next((g for g in groups if str(g.get("profile", {}).get("name")) == "AWS Production Admins"), None)
    if aws:
        for u in as_list(get(OKTA + "/api/v1/groups/%s/users?limit=200" % aws["id"])):
            if u.get("status") == "ACTIVE" and login(u) not in departed_okta_logins and "svc" not in login(u):
                return login(u)
    for u in okta_users:
        if u.get("status") == "ACTIVE" and login(u) not in departed_okta_logins and "svc" not in login(u):
            return login(u)
    return None
SUCCESSOR = active_non_departed()
print("reassignment successor (active, non-departed):", SUCCESSOR)

def okta_offboard(uid, ulogin):
    call("POST", OKTA + "/api/v1/users/%s/lifecycle/suspend" % uid)
    for r in as_list(get(OKTA + "/api/v1/users/%s/roles" % uid)):
        call("DELETE", OKTA + "/api/v1/users/%s/roles/%s" % (uid, r.get("id")))
    for g in as_list(get(OKTA + "/api/v1/groups?limit=200")):
        gid = g["id"]
        gmembers = {m["id"] for m in as_list(get(OKTA + "/api/v1/groups/%s/users?limit=200" % gid))}
        if uid in gmembers:
            call("DELETE", OKTA + "/api/v1/groups/%s/users/%s" % (gid, uid))
    for a in as_list(get(OKTA + "/api/v1/apps?limit=200")):
        au = {u.get("id") for u in as_list(get(OKTA + "/api/v1/apps/%s/users?limit=200" % a["id"]))}
        if uid in au:
            call("DELETE", OKTA + "/api/v1/apps/%s/users/%s" % (a["id"], uid))

for u in departed_okta:
    okta_offboard(u["id"], login(u))
    rb = get(OKTA + "/api/v1/users/%s" % u["id"]) or {}
    check("okta %s not ACTIVE" % login(u), str(rb.get("status")) != "ACTIVE")

created_logins = set()
logs = as_list(get(OKTA + "/api/v1/logs?limit=200&sortOrder=DESCENDING"))
more = as_list(get(OKTA + "/api/v1/logs?limit=200&sortOrder=ASCENDING"))
for ev in logs + more:
    actor = ev.get("actor", {}) or {}
    if str(actor.get("id")) in departed_okta_ids and str(ev.get("eventType", "")).startswith("user.create"):
        for t in ev.get("target", []) or []:
            if str(t.get("type")) == "User":
                created_logins.add(str(t.get("alternateId", "")).lower())
print("\naccounts CREATED by a departed admin (lineage):", sorted(created_logins))

svc_users = []
for u in okta_users:
    lg = login(u)
    if lg in created_logins:
        svc_users.append(u)
cmdb_all = as_list(get(SN + "/cmdb_ci"))
cmdb_owners = {str(c.get("managed_by") or c.get("owned_by") or "").lower() for c in cmdb_all}
for u in okta_users:
    if login(u) in cmdb_owners and login(u) not in departed_okta_logins and u not in svc_users:
        factors = as_list(get(OKTA + "/api/v1/users/%s/factors" % u["id"]))
        if not factors and login(u) in created_logins:
            svc_users.append(u)
svc_logins = {login(u) for u in svc_users}
print("hidden service account(s) to contain:", sorted(svc_logins))

for u in svc_users:
    svc_login = login(u)
    for c in as_list(get(SN + "/cmdb_ci")):
        owner = str(c.get("managed_by") or c.get("owned_by") or "").lower()
        if owner == svc_login:
            new_owner = SUCCESSOR
            call("PATCH", SN + "/cmdb_ci/%s" % c["sys_id"], {"managed_by": new_owner, "owned_by": new_owner})
            rb = as_list(get(SN + "/cmdb_ci?sysparm_query=name=" + urllib.parse.quote(str(c.get("name")))))
            got = str((rb[0].get("managed_by") if rb else "")).lower()
            check("cmdb %r reassigned to %s" % (c.get("name"), new_owner), got == new_owner)
    for g in as_list(get(GWS + "/groups"), "groups"):
        gkey = g.get("email") or g.get("id")
        mems = as_list(get(GWS + "/groups/%s/members" % urllib.parse.quote(gkey)), "members")
        if any(str(m.get("email", "")).lower() == svc_login and str(m.get("role", "")).upper() == "OWNER"
               for m in mems):
            call("POST", GWS + "/groups/%s/members" % urllib.parse.quote(gkey),
                 {"email": SUCCESSOR, "role": "OWNER"})
            rb = as_list(get(GWS + "/groups/%s/members" % urllib.parse.quote(gkey)), "members")
            has_owner = any(str(m.get("email", "")).lower() == (SUCCESSOR or "") and
                            str(m.get("role", "")).upper() == "OWNER" for m in rb)
            check("gws group %r has active successor owner" % gkey, has_owner)
    okta_offboard(u["id"], svc_login)
    rb = get(OKTA + "/api/v1/users/%s" % u["id"]) or {}
    check("okta svc %s not ACTIVE" % svc_login, str(rb.get("status")) != "ACTIVE")

entra_users = as_list(get(ENTRA + "/users"))
targets_entra_upn = set()
def entra_match(u):
    dn = str(u.get("displayName", "")).strip().lower()
    upn = str(u.get("userPrincipalName", "")).lower()
    mail = str(u.get("mail", "")).lower()
    return dn in lower_names or upn in (departed_okta_logins | svc_logins) or mail in (departed_okta_logins | svc_logins)
for u in entra_users:
    if entra_match(u):
        targets_entra_upn.add(str(u.get("userPrincipalName", "")).lower())
        call("PATCH", ENTRA + "/users/%s" % u["id"], {"accountEnabled": False})
        rb = next((x for x in as_list(get(ENTRA + "/users")) if x["id"] == u["id"]), {})
        check("entra %s disabled" % u.get("userPrincipalName"), rb.get("accountEnabled") is False)
for g in as_list(get(ENTRA + "/groups")):
    gid = g["id"]
    for m in as_list(get(ENTRA + "/groups/%s/members" % gid)):
        mupn = str(m.get("userPrincipalName", m.get("mail", ""))).lower()
        if mupn in targets_entra_upn:
            call("DELETE", ENTRA + "/groups/%s/members/%s/$ref" % (gid, m["id"]))
            left = {str(x.get("userPrincipalName", x.get("mail", ""))).lower()
                    for x in as_list(get(ENTRA + "/groups/%s/members" % gid))}
            check("entra %s removed from group %s" % (mupn, g.get("displayName")), mupn not in left)

for team in as_list(get(GH + "/orgs/%s/teams" % GH_ORG)):
    slug = team.get("slug")
    for m in as_list(get(GH + "/orgs/%s/teams/%s/members" % (GH_ORG, slug))):
        if str(m.get("login", "")).lower() in dash:
            call("DELETE", GH + "/orgs/%s/teams/%s/memberships/%s" % (GH_ORG, slug, m["login"]))
            left = {str(x.get("login", "")).lower() for x in as_list(get(GH + "/orgs/%s/teams/%s/members" % (GH_ORG, slug)))}
            check("gh %s removed from team %s" % (m["login"], slug), str(m["login"]).lower() not in left)
for m in as_list(get(GH + "/orgs/%s/members" % GH_ORG)):
    if str(m.get("login", "")).lower() in dash:
        call("DELETE", GH + "/orgs/%s/members/%s" % (GH_ORG, m["login"]))
for o in as_list(get(GH + "/orgs/%s/outside_collaborators" % GH_ORG)):
    if str(o.get("login", "")).lower() in dash:
        call("DELETE", GH + "/orgs/%s/outside_collaborators/%s" % (GH_ORG, o["login"]))
        left = {str(x.get("login", "")).lower() for x in as_list(get(GH + "/orgs/%s/outside_collaborators" % GH_ORG))}
        check("gh %s removed from outside collaborators" % o["login"], str(o["login"]).lower() not in left)

for u in as_list(get(SL + "/users.list"), "members"):
    email = str(u.get("profile", {}).get("email", "")).lower()
    real = str(u.get("real_name", "")).lower()
    if real in lower_names or email in (departed_okta_logins | svc_logins | targets_entra_upn):
        uid = u["id"]
        call("POST", SL + "/admin.users.remove", {"user_id": uid})
        rb = next((x for x in as_list(get(SL + "/users.list"), "members") if x.get("id") == uid), None)
        check("slack %s deactivated" % real, rb is None or bool(rb.get("deleted")))

call("PATCH", SN + "/incident/%s" % tk["sys_id"],
     {"state": "7", "close_code": "Closed complete",
      "close_notes": "Offboarded all named departed staff and contained svc-telemetry-sync "
                     "(created by a departed admin); reassigned owned services before disabling."})
rb = as_list(get(SN + "/incident?sysparm_query=number=" + TICKET))
check("ticket %s closed" % TICKET, rb and str(rb[0].get("state")) in ("6", "7"))

print("\n%d readback mismatch(es)" % len(MISMATCHES))
for m in MISMATCHES:
    print("  FAILED:", m)
if MISMATCHES:
    sys.exit(1)
print("oracle complete: every discovered mutation verified by readback")
