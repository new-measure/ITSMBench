#!/usr/bin/env python3
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

OKTA = "http://okta.local.mock:8080/api/v1"
GH = "http://github.local.mock:8080"
SN = "http://servicenow.local.mock:8080/api/now/table"
REQ = "REQ0071001"
MISMATCHES = []

def call(method, url, body=None, form=False):
    data, hdrs = None, {"Accept": "application/json"}
    if form:
        data = urllib.parse.urlencode(body or {}).encode()
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
        return json.loads(raw) if raw and raw.strip()[:1] in "{[" else raw
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_body": e.read().decode()[:200]}

def get(url):
    return call("GET", url)

def as_list(obj, *keys):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in keys + ("result", "value", "values", "results", "data", "rows"):
            if isinstance(obj.get(k), list):
                return obj[k]
    return []

def check(desc, ok):
    print(("  OK   " if ok else "  FAIL ") + desc)
    if not ok:
        MISMATCHES.append(desc)

def login_key(email_or_login):
    local = str(email_or_login).split("@")[0]
    return local.replace(".", "-").lower()

reqs = as_list(get(SN + "/sc_request?sysparm_query=number=" + REQ))
if not reqs:
    reqs = [r for r in as_list(get(SN + "/sc_request")) if str(r.get("number")) == REQ]
assert reqs, "recert request %s not found" % REQ
req_sysid = str(reqs[0]["sys_id"])
print("recert %s sys_id=%s state=%s" % (REQ, req_sysid, reqs[0].get("request_state")))

ritms = as_list(get(SN + "/sc_req_item?sysparm_limit=500"))
print("access-request records: %d" % len(ritms))

def descriptor(r):
    return (login_key(r.get("u_user") or r.get("requested_for")), str(r.get("u_system")).lower(),
            str(r.get("u_access_type")).lower(), str(r.get("u_target")), str(r.get("u_permission") or ""))

APPROVED = [r for r in ritms if str(r.get("approval")).lower() == "approved"]
approved_desc = {descriptor(r)[:4] for r in APPROVED}
approved_users = {descriptor(r)[0] for r in APPROVED}
print("approved requests: %d | approved actors: %d" % (len(APPROVED), len(approved_users)))

okta_users = as_list(get(OKTA + "/users?limit=500"), "value")
uid_to_key, key_to_uid, key_to_title = {}, {}, {}
for u in okta_users:
    prof = u.get("profile", {})
    key = login_key(prof.get("login") or prof.get("email"))
    uid_to_key[str(u["id"])] = key
    key_to_uid[key] = str(u["id"])
    key_to_title[key] = str(prof.get("title"))

groups = as_list(get(OKTA + "/groups?limit=500"), "value")
gid_to_name = {str(g["id"]): str(g.get("profile", {}).get("name")) for g in groups}
group_members = {}
for g in groups:
    members = as_list(get(OKTA + "/groups/%s/users?limit=500" % g["id"]))
    group_members[str(g["id"])] = {login_key(m.get("profile", {}).get("login")) for m in members}

user_group_names = {}
for gid, keys in group_members.items():
    for k in keys:
        user_group_names.setdefault(k, set()).add(gid_to_name[gid])

title_members = {}
for k, t in key_to_title.items():
    title_members.setdefault(t, []).append(k)
birthright = {}
for t, members in title_members.items():
    sets = [user_group_names.get(k, set()) for k in members]
    birthright[t] = set.intersection(*sets) if sets else set()
print("birthright:", {t: sorted(v) for t, v in birthright.items() if v})

def is_birthright(key, group_name):
    return group_name in birthright.get(key_to_title.get(key, ""), set())

name_to_gid = {v: k for k, v in gid_to_name.items()}
apps = as_list(get(OKTA + "/apps?limit=500"), "value")
label_to_app = {str(a.get("label")): str(a["id"]) for a in apps}
app_users = {str(a["id"]): {login_key(uu.get("profile", {}).get("login") or "")
                            for uu in as_list(get(OKTA + "/apps/%s/users?limit=500" % a["id"]))}
             for a in apps}
app_user_ids = {str(a["id"]): {str(uu.get("id"))
                               for uu in as_list(get(OKTA + "/apps/%s/users?limit=500" % a["id"]))} for a in apps}

gh_members = {str(m.get("login")): m for m in as_list(get(GH + "/orgs/meridian-ledger/members?per_page=100"))}
ORG = "meridian-ledger"
for r in APPROVED:
    if descriptor(r)[2] == "org_member":
        ORG = descriptor(r)[3]
repos = as_list(get(GH + "/orgs/%s/repos?per_page=100" % ORG))
repo_collabs = {str(r.get("name")): {str(c.get("login")): c
                                     for c in as_list(get(GH + "/repos/%s/%s/collaborators?per_page=100" % (ORG, r.get("name"))))}
                for r in repos}

for r in APPROVED:
    key, system, typ, target, perm = descriptor(r)
    if system == "okta" and typ == "group":
        gid = name_to_gid.get(target)
        if gid and key not in group_members.get(gid, set()):
            call("PUT", OKTA + "/groups/%s/users/%s" % (gid, key_to_uid[key]))
            print("  +okta group %s <- %s" % (target, key))
    elif system == "okta" and typ == "app":
        aid = label_to_app.get(target)
        if aid and key_to_uid[key] not in app_user_ids.get(aid, set()):
            call("POST", OKTA + "/apps/%s/users" % aid, body={"id": key_to_uid[key], "scope": "USER"})
            print("  +okta app %s <- %s" % (target, key))
    elif system == "github" and typ == "org_member":
        if key not in gh_members:
            call("PUT", GH + "/orgs/%s/memberships/%s" % (ORG, key), body={"role": "member"})
            print("  +github org member %s" % key)
    elif system == "github" and typ == "collaborator":
        if key not in repo_collabs.get(target, {}):
            call("PUT", GH + "/repos/%s/%s/collaborators/%s" % (ORG, target, key),
                 body={"permission": perm or "push"})
            print("  +github collaborator %s <- %s (%s)" % (target, key, perm or "push"))

for gid, keys in group_members.items():
    gname = gid_to_name[gid]
    for key in sorted(keys):
        if is_birthright(key, gname):
            continue
        if (key, "okta", "group", gname) in approved_desc:
            continue
        call("DELETE", OKTA + "/groups/%s/users/%s" % (gid, key_to_uid[key]))
        print("  -okta group %s -> %s (drift)" % (gname, key))

for aid, ids in app_user_ids.items():
    label = next((lb for lb, i in label_to_app.items() if i == aid), aid)
    for u in okta_users:
        if str(u["id"]) not in ids:
            continue
        key = uid_to_key[str(u["id"])]
        if (key, "okta", "app", label) in approved_desc:
            continue
        call("DELETE", OKTA + "/apps/%s/users/%s" % (aid, str(u["id"])))
        print("  -okta app %s -> %s (drift)" % (label, key))

for u in okta_users:
    key = uid_to_key[str(u["id"])]
    for ra in as_list(get(OKTA + "/users/%s/roles" % u["id"])):
        rtype = str(ra.get("type"))
        if (key, "okta", "role", rtype) in approved_desc:
            continue
        call("DELETE", OKTA + "/users/%s/roles/%s" % (u["id"], ra.get("id")))
        print("  -okta role %s -> %s (drift)" % (rtype, key))

for login, m in gh_members.items():
    key = login_key(login)
    if str(m.get("role")) == "admin" and (key, "github", "org_role", "admin") not in approved_desc:
        call("PUT", GH + "/orgs/%s/memberships/%s" % (ORG, login), body={"role": "member"})
        print("  ~github org role %s admin->member (right-size)" % login)

for repo, collabs in repo_collabs.items():
    for login in list(collabs):
        key = login_key(login)
        if (key, "github", "collaborator", repo) in approved_desc:
            continue
        call("DELETE", GH + "/repos/%s/%s/collaborators/%s" % (ORG, repo, login))
        print("  -github collaborator %s -> %s (drift)" % (repo, login))

directory = set(uid_to_key.values())
for repo in repo_collabs:
    for k in as_list(get(GH + "/repos/%s/%s/keys?per_page=100" % (ORG, repo))):
        added_by = login_key(k.get("added_by") or "")
        if added_by in directory and added_by not in approved_users:
            call("DELETE", GH + "/repos/%s/%s/keys/%s" % (ORG, repo, k.get("id")))
            print("  -github deploy key %s#%s (added_by %s, unauthorized) " % (repo, k.get("id"), added_by))

call("PATCH", SN + "/sc_request/%s" % req_sysid,
     body={"request_state": "closed_complete", "state": "3",
           "close_notes": "Reconciled live access to the approved-request baseline (applied approved-but-"
                          "unprovisioned access, removed unapproved drift, right-sized over-privilege, and "
                          "cleared the residual standing power); kept birthright, the approved exception and "
                          "the break-glass owner."})

print("\n--- readback ---")

def okta_group_has(gid_name, key):
    gid = name_to_gid.get(gid_name)
    members = {login_key(m.get("profile", {}).get("login")) for m in as_list(get(OKTA + "/groups/%s/users?limit=500" % gid))}
    return key in members

def okta_app_has(label, key):
    aid = label_to_app.get(label)
    ids = {str(uu.get("id")) for uu in as_list(get(OKTA + "/apps/%s/users?limit=500" % aid))}
    return key_to_uid.get(key) in ids

def okta_roles(key):
    return {str(r.get("type")) for r in as_list(get(OKTA + "/users/%s/roles" % key_to_uid[key]))}

def gh_role(key):
    ms = {str(m.get("login")): m for m in as_list(get(GH + "/orgs/%s/members?per_page=100" % ORG))}
    return str(ms[key].get("role")) if key in ms else None

def gh_collab(repo, key):
    return key in {str(c.get("login")) for c in as_list(get(GH + "/repos/%s/%s/collaborators?per_page=100" % (ORG, repo)))}

def gh_key_ids(repo):
    return {str(k.get("id")) for k in as_list(get(GH + "/repos/%s/%s/keys?per_page=100" % (ORG, repo)))}

check("priya added to Prod Deploy Approvers", okta_group_has("Prod Deploy Approvers", "priya-nair"))
check("priya assigned Spinnaker", okta_app_has("Spinnaker", "priya-nair"))
check("diego is github org member", "diego-santos" in {str(m.get("login")) for m in as_list(get(GH + "/orgs/%s/members?per_page=100" % ORG))})
check("diego collaborator on payments-ledger", gh_collab("payments-ledger", "diego-santos"))
check("diego assigned Grafana", okta_app_has("Grafana", "diego-santos"))
check("priya collaborator on edge-gateway", gh_collab("edge-gateway", "priya-nair"))
check("marcus removed from Payments Platform Admins", not okta_group_has("Payments Platform Admins", "marcus-feld"))
check("marcus NetSuite removed", not okta_app_has("NetSuite", "marcus-feld"))
check("marcus collaborator treasury-core removed", not gh_collab("treasury-core", "marcus-feld"))
check("yuki removed from Payments Platform Admins", not okta_group_has("Payments Platform Admins", "yuki-tan"))
check("yuki NetSuite removed", not okta_app_has("NetSuite", "yuki-tan"))
check("elena removed from Prod Deploy Approvers", not okta_group_has("Prod Deploy Approvers", "elena-rossi"))
check("elena NetSuite removed", not okta_app_has("NetSuite", "elena-rossi"))
check("elena collaborator edge-gateway removed", not gh_collab("edge-gateway", "elena-rossi"))
check("marcus github org role downgraded to member", gh_role("marcus-feld") == "member")
check("elena github org role downgraded to member", gh_role("elena-rossi") == "member")
check("elena SUPER_ADMIN okta role revoked", "SUPER_ADMIN" not in okta_roles("elena-rossi"))
check("elena deploy key removed (payments-ledger 5001)", "5001" not in gh_key_ids("payments-ledger"))
check("yuki deploy key removed (treasury-core 5003)", "5003" not in gh_key_ids("treasury-core"))
check("marcus deploy key removed (risk-engine 5004)", "5004" not in gh_key_ids("risk-engine"))
req2 = [r for r in as_list(get(SN + "/sc_request")) if str(r.get("number")) == REQ][0]
check("recert request closed", str(req2.get("request_state")).startswith("closed") or str(req2.get("state")) == "3")

check("[ctrl] tomas kept in Payments Platform Admins (exception)", okta_group_has("Payments Platform Admins", "tomas-alvarez"))
check("[ctrl] dana kept github org admin (break-glass)", gh_role("dana-whitfield") == "admin")
check("[ctrl] dana kept SUPER_ADMIN (break-glass)", "SUPER_ADMIN" in okta_roles("dana-whitfield"))
check("[ctrl] karan still absent from admins (rejected)", not okta_group_has("Payments Platform Admins", "karan-shah"))
check("[ctrl] marcus keeps engineer birthright (Payments Engineering)", okta_group_has("Payments Engineering", "marcus-feld"))
check("[ctrl] ravi keeps approved deploy group", okta_group_has("Prod Deploy Approvers", "ravi-mehta"))
check("[ctrl] ravi keeps approved collaborator payments-ledger", gh_collab("payments-ledger", "ravi-mehta"))
check("[ctrl] ci-bot deploy key kept", "5002" in gh_key_ids("payments-ledger"))
check("[ctrl] ravi deploy key kept (approved owner)", "5005" in gh_key_ids("risk-engine"))
check("[ctrl] lena keeps approved NetSuite", okta_app_has("NetSuite", "lena-brooks"))

print("\n%d mismatch(es)" % len(MISMATCHES))
for m in MISMATCHES:
    print("  FAILED:", m)
sys.exit(1 if MISMATCHES else 0)
