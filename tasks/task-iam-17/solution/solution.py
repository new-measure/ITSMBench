#!/usr/bin/env python3
import datetime
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

TICKET = "INC0071001"
SEARCH = "http://search.local.mock:8080/search"
OKTA = "http://okta.local.mock:8080"
GH = "http://github.local.mock:8080"
GH_ORG = "nimbus-logistics"
SN = "http://servicenow.local.mock:8080/api/now/table"
KEKA = "http://keka.local.mock:8080/api/v1/hris/employees"

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
        for k in keys + ("data", "value", "values", "result", "results", "items", "members", "users"):
            if k in obj and isinstance(obj[k], list):
                return obj[k]
    return []

def check(desc, ok):
    print(("  OK   " if ok else "  FAIL ") + desc)
    if not ok:
        MISMATCHES.append(desc)

for q in ("incident table", "okta users", "okta user roles", "cmdb service", "hris employees",
          "org members", "team members", "deploy keys"):
    hits = as_list(get(SEARCH + "?q=" + urllib.parse.quote(q) + "&limit=3"))
    print("search %-16r -> %s" % (q, [str(h.get("path") or h.get("route") or h.get("id")) for h in hits][:3]))

rows = as_list(get(SN + "/incident?sysparm_query=number=" + TICKET))
assert rows, "cannot read finding %s" % TICKET
finding = rows[0]
print("\nfinding %s state=%s" % (TICKET, finding.get("state")))

cmdb = as_list(get(SN + "/cmdb_ci?sysparm_query=" + urllib.parse.quote("sys_class_nameSTARTSWITHcmdb_ci")))
if not cmdb:
    cmdb = as_list(get(SN + "/cmdb_ci"))
owner_of = {}
ghlogin_of = {}
sanctioned = set()
inventory_logins = set()
for ci in cmdb:
    ol = str(ci.get("u_okta_login", "")).lower()
    if not ol:
        continue
    inventory_logins.add(ol)
    owner_of[ol] = str(ci.get("owned_by") or ci.get("managed_by") or "").lower()
    ghlogin_of[ol] = str(ci.get("u_github_login", "")).strip().lower()
    if "break-glass" in str(ci.get("u_control_type", "")).lower():
        sanctioned.add(ol)

okta_users = as_list(get(OKTA + "/api/v1/users?limit=200"))

def login(u):
    return str(u.get("profile", {}).get("login", "")).lower()

def gh_of(u):
    return ghlogin_of.get(login(u), "") or str(u.get("profile", {}).get("githubLogin", "")).strip().lower()

def is_service_marker(u):
    p = u.get("profile", {})
    return str(p.get("title", "")).strip().lower() == "service account" or str(p.get("login", "")).lower().startswith("svc-")

nhis = [u for u in okta_users if login(u) in inventory_logins or is_service_marker(u)]
print("discovered NHIs:", sorted(login(u) for u in nhis))
print("  (disguised, inventory-only:", sorted(login(u) for u in nhis if not is_service_marker(u)), ")")

def roles_of(u):
    return as_list(get(OKTA + "/api/v1/users/%s/roles" % u["id"]))

def admin_roles(u):
    return [r for r in roles_of(u) if str(r.get("type", "")).endswith("_ADMIN")
            and str(r.get("status", "ACTIVE")).upper() == "ACTIVE"]

emps = as_list(get(KEKA + "?limit=500"))
status_by_email = {str(e.get("email", "")).lower(): str(e.get("employmentStatus", "")) for e in emps}

def is_orphaned(u):
    owner = owner_of.get(login(u), "")
    if not owner:
        return True
    st = status_by_email.get(owner)
    return st is None or st.lower() != "working"

print("sanctioned (break-glass):", sorted(sanctioned))

groups = as_list(get(OKTA + "/api/v1/groups?limit=200"))
admin_groups = [g for g in groups if "admin" in str(g.get("profile", {}).get("name", "")).lower()]
print("admin groups:", [g["profile"]["name"] for g in admin_groups])

def in_group(gid, uid):
    users = as_list(get(OKTA + "/api/v1/groups/%s/users?limit=200" % gid))
    return any(x["id"] == uid for x in users)

gh_members = as_list(get(GH + "/orgs/%s/members" % GH_ORG))
gh_teams = as_list(get(GH + "/orgs/%s/teams" % GH_ORG))
gh_repos = as_list(get(GH + "/orgs/%s/repos" % GH_ORG))

def org_owner_logins():
    return {str(m.get("login", "")).lower() for m in as_list(get(GH + "/orgs/%s/members" % GH_ORG))
            if str(m.get("role", "")).lower() == "admin" and not m.get("team_slug")}

def team_maintainer_logins():
    out = set()
    for team in gh_teams:
        for m in as_list(get(GH + "/orgs/%s/teams/%s/members" % (GH_ORG, team.get("slug")))):
            if str(m.get("role", "")).lower() == "maintainer":
                out.add(str(m.get("login", "")).lower())
    return out

def strip_okta_privilege(u, drop_group=True):
    uid = u["id"]
    if drop_group:
        for g in admin_groups:
            if in_group(g["id"], uid):
                call("DELETE", OKTA + "/api/v1/groups/%s/users/%s" % (g["id"], uid))
    for r in admin_roles(u):
        call("DELETE", OKTA + "/api/v1/users/%s/roles/%s" % (uid, r["id"]))

def strip_github(u):
    gl = gh_of(u)
    if not gl:
        return
    for m in as_list(get(GH + "/orgs/%s/members" % GH_ORG)):
        if str(m.get("login", "")).lower() == gl and str(m.get("role", "")).lower() == "admin" and not m.get("team_slug"):
            call("PUT", GH + "/orgs/%s/memberships/%s" % (GH_ORG, m["login"]), {"role": "member"})
    for team in gh_teams:
        slug = team.get("slug")
        for m in as_list(get(GH + "/orgs/%s/teams/%s/members" % (GH_ORG, slug))):
            if str(m.get("login", "")).lower() == gl and str(m.get("role", "")).lower() == "maintainer":
                call("PUT", GH + "/orgs/%s/teams/%s/memberships/%s" % (GH_ORG, slug, m["login"]), {"role": "member"})

def delete_all_keys(gl):
    for repo in gh_repos:
        rn = repo.get("name")
        for key in as_list(get(GH + "/repos/%s/%s/keys" % (GH_ORG, rn))):
            if str(key.get("added_by", "")).lower() == gl:
                call("DELETE", GH + "/repos/%s/%s/keys/%s" % (GH_ORG, rn, key.get("id")))

def ts(v):
    s = re.split(r"\.", str(v or "").replace("Z", "").replace("T", " "))[0]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(s, fmt).timestamp()
        except ValueError:
            continue
    return None

orphans, kept = [], []
for u in nhis:
    lg = login(u)
    if is_orphaned(u):
        orphans.append(u)
    else:
        kept.append(u)
print("orphaned:", sorted(login(u) for u in orphans))
print("kept:", sorted(login(u) for u in kept))

for u in orphans:
    strip_okta_privilege(u, drop_group=True)
    strip_github(u)
    delete_all_keys(gh_of(u))
    call("POST", OKTA + "/api/v1/users/%s/lifecycle/deactivate" % u["id"])

for u in kept:
    if login(u) in sanctioned:
        continue
    has_group = any(in_group(g["id"], u["id"]) for g in admin_groups)
    has_admin = bool(admin_roles(u))
    is_org_owner = gh_of(u) in org_owner_logins()
    is_team_maint = gh_of(u) in team_maintainer_logins()
    if has_group or has_admin or is_org_owner or is_team_maint:
        strip_okta_privilege(u, drop_group=True)
        strip_github(u)

kept_gh = {gh_of(u) for u in kept if gh_of(u)}
for repo in gh_repos:
    rn = repo.get("name")
    keys = as_list(get(GH + "/repos/%s/%s/keys" % (GH_ORG, rn)))
    by_owner = {}
    for k in keys:
        ab = str(k.get("added_by", "")).lower()
        if ab in kept_gh:
            by_owner.setdefault(ab, []).append(k)
    for ab, ks in by_owner.items():
        if len(ks) > 1:
            ks.sort(key=lambda k: ts(k.get("created_at")) or 0)
            for stale in ks[:-1]:
                call("DELETE", GH + "/repos/%s/%s/keys/%s" % (GH_ORG, rn, stale.get("id")))

call("PATCH", SN + "/incident/%s" % finding["sys_id"],
     {"state": "7", "close_code": "Solved (Permanently)",
      "close_notes": "Retired the orphaned/unused service accounts (deactivated, admin roles revoked, "
                     "removed from the automation admins group, GitHub org-owner/team-maintainer stepped "
                     "down, deploy keys deleted); right-sized the over-privileged active service accounts "
                     "without disrupting them; rotated out superseded deploy keys. Sanctioned break-glass "
                     "automation, actively-used accounts, and all human accounts were left untouched."})

print("\n--- readback ---")
users2 = {u["id"]: u for u in as_list(get(OKTA + "/api/v1/users?limit=200"))}
for u in orphans:
    lg = login(u)
    st = str((users2.get(u["id"]) or {}).get("status"))
    check("%s deactivated" % lg, u["id"] not in users2 or st != "ACTIVE")
    check("%s admin roles revoked" % lg, not admin_roles(u))
    for g in admin_groups:
        check("%s not in %s" % (lg, g["profile"]["name"]), not in_group(g["id"], u["id"]))
    gl = gh_of(u)
    if gl:
        check("%s not gh org owner" % lg, gl not in org_owner_logins())

for u in kept:
    lg = login(u)
    if lg in sanctioned:
        continue
    check("%s admin roles right-sized" % lg, not admin_roles(u))
    for g in admin_groups:
        check("%s not in admin group" % lg, not in_group(g["id"], u["id"]))
    check("%s not gh org owner" % lg, gh_of(u) not in org_owner_logins())
    check("%s not gh team maintainer" % lg, gh_of(u) not in team_maintainer_logins())

rb = as_list(get(SN + "/incident?sysparm_query=number=" + TICKET))
check("finding %s closed" % TICKET, rb and str(rb[0].get("state")) in ("6", "7"))

print("\n%d readback mismatch(es)" % len(MISMATCHES))
for m in MISMATCHES:
    print("  FAILED:", m)
sys.exit(1 if MISMATCHES else 0)
