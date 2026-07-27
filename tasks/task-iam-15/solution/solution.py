#!/usr/bin/env python3
import datetime
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

TICKET = "INC0045001"
SEARCH = "http://search.local.mock:8080/search"
OKTA = "http://okta.local.mock:8080"
GH = "http://github.local.mock:8080"
GH_ORG = "kestrel-data"
SN = "http://servicenow.local.mock:8080/api/now/table"

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

def ts(value):
    s = str(value or "").strip()
    if not s:
        return None
    s = s.replace("Z", "").replace("T", " ")
    s = re.split(r"\.", s)[0]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(s, fmt).replace(tzinfo=datetime.timezone.utc).timestamp()
        except ValueError:
            continue
    return None

for q in ("incident table", "change request", "okta users roles", "org members", "deploy keys"):
    hits = as_list(get(SEARCH + "?q=" + urllib.parse.quote(q) + "&limit=3"))
    print("search %-18r -> %s" % (q, [str(h.get("path") or h.get("route") or h.get("id")) for h in hits][:3]))

rows = as_list(get(SN + "/incident?sysparm_query=number=" + TICKET))
assert rows, "cannot read ticket %s" % TICKET
tk = rows[0]
print("\nticket %s state=%s" % (TICKET, tk.get("state")))

okta_users = as_list(get(OKTA + "/api/v1/users?limit=200"))

def login(u):
    return str(u.get("profile", {}).get("login", "")).lower()

def roles_of(u):
    return as_list(get(OKTA + "/api/v1/users/%s/roles" % u["id"]))

def is_admin_user(u):
    return any(str(r.get("type")) == "SUPER_ADMIN" and str(r.get("status", "ACTIVE")).upper() == "ACTIVE"
               for r in roles_of(u))

current_admins = [u for u in okta_users if is_admin_user(u)]
def grant_ts(u):
    cands = [ts(r.get("created")) for r in roles_of(u)
             if str(r.get("type")) == "SUPER_ADMIN" and ts(r.get("created")) is not None]
    return min(cands) if cands else None

print("current SUPER_ADMIN holders:", sorted(login(u) for u in current_admins))

changes = as_list(get(SN + "/change_request?sysparm_query=" + urllib.parse.quote("state=3")))
if not changes:
    changes = as_list(get(SN + "/change_request"))
best = None
for c in changes:
    w0, w1 = ts(c.get("work_start") or c.get("start_date")), ts(c.get("work_end") or c.get("end_date"))
    if w0 is None or w1 is None:
        continue
    batch = [u for u in current_admins if grant_ts(u) is not None and w0 <= grant_ts(u) <= w1]
    if best is None or len(batch) > len(best[1]):
        best = (c, batch, w0, w1)
assert best and best[1], "no closed change window captures a batch of admin grants"
chg, cohort_admins, W0, W1 = best
print("project change %s window [%s .. %s] captured %d admin grants"
      % (chg.get("number"), chg.get("work_start"), chg.get("work_end"), len(cohort_admins)))

def provisioned_in_window(u):
    t = ts(u.get("created"))
    return t is not None and W0 <= t <= W1

cohort = list({u["id"]: u for u in cohort_admins}.values())
cohort_ids = {u["id"] for u in cohort}
print("cohort (excess Atlas admins):", sorted(login(u) for u in cohort))

logs = as_list(get(OKTA + "/api/v1/logs?limit=200"))
logs += as_list(get(OKTA + "/api/v1/logs?limit=200&sortOrder=DESCENDING"))
admin_group_ids = {}
for ev in logs:
    if str(ev.get("eventType")) != "group.user_membership.add":
        continue
    t = ts(ev.get("published"))
    if t is None or not (W0 <= t <= W1):
        continue
    ut = {str(x.get("id")) for x in ev.get("target", []) if str(x.get("type")) == "User"}
    if not (ut & cohort_ids):
        continue
    for x in ev.get("target", []):
        if str(x.get("type")) == "UserGroup":
            admin_group_ids[str(x.get("id"))] = admin_group_ids.get(str(x.get("id")), 0) + 1
ADMIN_GID = max(admin_group_ids, key=admin_group_ids.get) if admin_group_ids else None
admin_group = next((g for g in as_list(get(OKTA + "/api/v1/groups?limit=200")) if g["id"] == ADMIN_GID), None)
print("admin group (from lineage):", admin_group and admin_group.get("profile", {}).get("name"), ADMIN_GID)

def okta_uid_to_ghlogin(u):
    return str(u.get("profile", {}).get("githubLogin", "")).strip().lower()

group_members = {m for m in (admin_group.get("members", []) if admin_group else [])}
for u in cohort:
    uid, lg = u["id"], login(u)
    if uid in group_members or lg in {login(x) for x in as_list(get(OKTA + "/api/v1/groups/%s/users?limit=200" % ADMIN_GID))}:
        call("DELETE", OKTA + "/api/v1/groups/%s/users/%s" % (ADMIN_GID, uid))
    for r in roles_of(u):
        if str(r.get("type")) == "SUPER_ADMIN":
            call("DELETE", OKTA + "/api/v1/users/%s/roles/%s" % (uid, r.get("id")))
    if provisioned_in_window(u):
        call("POST", OKTA + "/api/v1/users/%s/lifecycle/deactivate" % uid)

cohort_gh = {okta_uid_to_ghlogin(u) for u in cohort if okta_uid_to_ghlogin(u)}
for m in as_list(get(GH + "/orgs/%s/members" % GH_ORG)):
    if str(m.get("login", "")).lower() in cohort_gh and str(m.get("role", "")).lower() == "admin" and not m.get("team_slug"):
        call("PUT", GH + "/orgs/%s/memberships/%s" % (GH_ORG, m["login"]), {"role": "member"})
for team in as_list(get(GH + "/orgs/%s/teams" % GH_ORG)):
    slug = team.get("slug")
    for m in as_list(get(GH + "/orgs/%s/teams/%s/members" % (GH_ORG, slug))):
        if str(m.get("login", "")).lower() in cohort_gh and str(m.get("role", "")).lower() == "maintainer":
            call("PUT", GH + "/orgs/%s/teams/%s/memberships/%s" % (GH_ORG, slug, m["login"]), {"role": "member"})
for repo in as_list(get(GH + "/orgs/%s/repos" % GH_ORG)):
    rname = repo.get("name")
    for key in as_list(get(GH + "/repos/%s/%s/keys" % (GH_ORG, rname))):
        t = ts(key.get("created_at"))
        if t is not None and W0 <= t <= W1:
            call("DELETE", GH + "/repos/%s/%s/keys/%s" % (GH_ORG, rname, key.get("id")))

call("PATCH", SN + "/incident/%s" % tk["sys_id"],
     {"state": "7", "close_code": "Closed complete",
      "close_notes": "Reduced standing platform admins to least privilege: wound back the project "
                     "temporary elevated access across Okta (group + directly-assigned admin roles), "
                     "GitHub (org owner + team maintainer stepped down, project deploy keys removed), "
                     "and deactivated the project deployment service account. Standing admins, the "
                     "recent on-call admin, and the break-glass account were retained."})

print("\n--- readback ---")
grp_logins = {login(u): u for u in as_list(get(OKTA + "/api/v1/groups/%s/users?limit=200" % ADMIN_GID))}
users2 = {u["id"]: u for u in as_list(get(OKTA + "/api/v1/users?limit=200"))}

def active_roles(uid):
    return {str(r.get("type")) for r in as_list(get(OKTA + "/api/v1/users/%s/roles" % uid))
            if str(r.get("status", "ACTIVE")).upper() == "ACTIVE"}

for u in cohort:
    lg = login(u)
    check("%s not in admin group" % lg, lg not in grp_logins)
    check("%s SUPER_ADMIN revoked" % lg, "SUPER_ADMIN" not in active_roles(u["id"]))
    if provisioned_in_window(u):
        st = str((users2.get(u["id"]) or {}).get("status"))
        check("service account %s deactivated" % lg, u["id"] not in users2 or st != "ACTIVE")

for m in as_list(get(GH + "/orgs/%s/members" % GH_ORG)):
    if str(m.get("login", "")).lower() in cohort_gh and not m.get("team_slug"):
        check("gh org %s not owner" % m["login"], str(m.get("role", "")).lower() != "admin")
for team in as_list(get(GH + "/orgs/%s/teams" % GH_ORG)):
    slug = team.get("slug")
    for m in as_list(get(GH + "/orgs/%s/teams/%s/members" % (GH_ORG, slug))):
        if str(m.get("login", "")).lower() in cohort_gh:
            check("gh team %s/%s not maintainer" % (slug, m["login"]), str(m.get("role", "")).lower() != "maintainer")
for repo in as_list(get(GH + "/orgs/%s/repos" % GH_ORG)):
    rname = repo.get("name")
    for key in as_list(get(GH + "/repos/%s/%s/keys" % (GH_ORG, rname))):
        t = ts(key.get("created_at"))
        check("no in-window deploy key on %s (%s)" % (rname, key.get("title")), not (t is not None and W0 <= t <= W1))

rb = as_list(get(SN + "/incident?sysparm_query=number=" + TICKET))
check("ticket %s closed" % TICKET, rb and str(rb[0].get("state")) in ("6", "7"))

print("\n%d readback mismatch(es)" % len(MISMATCHES))
for m in MISMATCHES:
    print("  FAILED:", m)
sys.exit(1 if MISMATCHES else 0)
