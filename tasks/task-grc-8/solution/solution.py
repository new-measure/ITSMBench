#!/usr/bin/env python3
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

GH = "http://github.local.mock:8080"
SN = "http://servicenow.local.mock:8080/api/now/table"
INCIDENT_NUMBER = "INC0030001"
NOW_DATE = "2026-07-20"
MISMATCHES = []

def call(method, url, body=None, bodyless=False):
    data, headers = None, {"Accept": "application/json"}
    if body is not None and not bodyless:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
        return resp.status, (json.loads(raw) if raw and raw.strip()[:1] in "{[" else raw)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]

def get(url):
    return call("GET", url)[1]

def sn_list(table):
    d = get("%s/%s" % (SN, table))
    return (d or {}).get("result", []) if isinstance(d, dict) else []

def gh_list(path):
    d = get(GH + path)
    return d if isinstance(d, list) else []

def check(desc, ok):
    print(("  OK   " if ok else "  FAIL ") + desc)
    if not ok:
        MISMATCHES.append(desc)

incidents = sn_list("incident")
cur = next((i for i in incidents if str(i.get("number")) == INCIDENT_NUMBER), None)
assert cur, "incident not found"
inc_sys = str(cur["sys_id"])
choices = sn_list("sys_choice")
closed = [str(c.get("value")) for c in choices if str(c.get("name")) == "incident"
          and str(c.get("element")) == "state" and str(c.get("label", "")).lower() in ("resolved", "closed")]
CLOSED = closed[-1] if closed else "7"
print("incident %s sys_id=%s -> close state %s" % (INCIDENT_NUMBER, inc_sys, CLOSED))

repo_rows = sn_list("u_repo")
production_names = {str(r.get("u_name")) for r in repo_rows if str(r.get("u_tier")) == "production"}

exc_rows = sn_list("u_access_exception")
approved_grantees = {str(e.get("u_grantee")) for e in exc_rows
                     if str(e.get("u_state")) == "approved" and str(e.get("u_expires_on"))[:10] >= NOW_DATE}
svc_rows = sn_list("u_service_account")
svc_key_titles = {str(s.get("u_key_title")) for s in svc_rows if s.get("u_key_title")}
print("production repos:", sorted(production_names))
print("current approved grantees:", sorted(approved_grantees))
print("authorized service-key titles:", sorted(svc_key_titles))

orgs = gh_list("/organizations") or gh_list("/user/orgs")
org = str((orgs[0] if orgs else {}).get("login") or "acme-cloud")
members = gh_list("/orgs/%s/members" % org)
member_logins = {str(m.get("login")) for m in members}
print("org=%s members=%s" % (org, sorted(member_logins)))

repos = gh_list("/orgs/%s/repos" % org)
repo_by_name = {str(r.get("name")): r for r in repos}
print("github repos:", sorted(repo_by_name))

def review_count(prot):
    if not isinstance(prot, dict):
        return -1
    rpr = prot.get("required_pull_request_reviews") or {}
    return int(rpr.get("required_approving_review_count") or 0)

for name in sorted(production_names & set(repo_by_name)):
    branch = str(repo_by_name[name].get("default_branch") or "main")
    code, prot = call("GET", "%s/repos/%s/%s/branches/%s/protection" % (GH, org, name, branch))
    if code == 404 or review_count(prot) < 1:
        call("PUT", "%s/repos/%s/%s/branches/%s/protection" % (GH, org, name, branch),
             body={"required_pull_request_reviews": {"required_approving_review_count": 2,
                                                     "dismiss_stale_reviews": True},
                   "enforce_admins": True, "required_status_checks": None, "restrictions": None})
        print("  protect %s@%s (required reviews)" % (name, branch))

for name in sorted(repo_by_name):
    for c in gh_list("/repos/%s/%s/collaborators" % (org, name)):
        login = str(c.get("login"))
        if login not in member_logins and login not in approved_grantees:
            call("DELETE", "%s/repos/%s/%s/collaborators/%s" % (GH, org, name, login), bodyless=True)
            print("  remove collaborator %s from %s" % (login, name))

for name in sorted(repo_by_name):
    for k in gh_list("/repos/%s/%s/keys" % (org, name)):
        added_by = str(k.get("added_by"))
        title = str(k.get("title"))
        if added_by not in member_logins and title not in svc_key_titles:
            call("DELETE", "%s/repos/%s/%s/keys/%s" % (GH, org, name, k.get("id")), bodyless=True)
            print("  delete deploy key %s (%s) on %s" % (k.get("id"), title, name))

for oc in gh_list("/orgs/%s/outside_collaborators" % org):
    login = str(oc.get("login"))
    if login not in approved_grantees:
        call("DELETE", "%s/orgs/%s/outside_collaborators/%s" % (GH, org, login), bodyless=True)
        print("  remove outside collaborator %s" % login)

call("PATCH", "%s/incident/%s" % (SN, inc_sys),
     body={"state": CLOSED, "close_code": "Solved (Permanently)",
           "close_notes": "Reconciled GitHub source-control state to the ServiceNow registers: enabled "
                          "required-review protection on production repositories, removed repository "
                          "collaborators and deploy keys left behind by departed contributors, removed "
                          "outside collaborators with no approved grant, and left documented/approved "
                          "and service-account items in place. Vanta monitor untouched."})

print("\n--- readback ---")
for name in sorted(production_names & set(repo_by_name)):
    branch = str(repo_by_name[name].get("default_branch") or "main")
    _, prot = call("GET", "%s/repos/%s/%s/branches/%s/protection" % (GH, org, name, branch))
    check("protection+review on %s@%s" % (name, branch), review_count(prot) >= 1)

remaining_collabs = {(name, str(c.get("login")))
                     for name in repo_by_name for c in gh_list("/repos/%s/%s/collaborators" % (org, name))}
for name, login in sorted(remaining_collabs):
    check("remaining collaborator %s@%s is authorized" % (login, name),
          login in member_logins or login in approved_grantees)

remaining_keys = [(name, k) for name in repo_by_name for k in gh_list("/repos/%s/%s/keys" % (org, name))]
for name, k in remaining_keys:
    ab, title = str(k.get("added_by")), str(k.get("title"))
    check("remaining key %s on %s is authorized" % (k.get("id"), name),
          ab in member_logins or title in svc_key_titles)

remaining_outside = {str(o.get("login")) for o in gh_list("/orgs/%s/outside_collaborators" % org)}
for login in sorted(remaining_outside):
    check("remaining outside collaborator %s is granted" % login, login in approved_grantees)

inc2 = (get("%s/incident/%s" % (SN, inc_sys)) or {}).get("result", {})
check("incident closed", str(inc2.get("state")) == CLOSED)

print("\n%d mismatch(es)" % len(MISMATCHES))
for m in MISMATCHES:
    print("  FAILED:", m)
sys.exit(1 if MISMATCHES else 0)
