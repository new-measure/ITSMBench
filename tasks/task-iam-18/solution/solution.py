#!/usr/bin/env python3
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

ENTRA = "http://entra-id.local.mock:8080/v1.0"
GH = "http://github.local.mock:8080"
SLACK = "http://slack.local.mock:8080/api"
SN = "http://servicenow.local.mock:8080/api/now/table"
REQ = "REQ0090012"
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
        for k in keys + ("value", "members", "result", "results", "values", "data", "rows"):
            if isinstance(obj.get(k), list):
                return obj[k]
    return []

def check(desc, ok):
    print(("  OK   " if ok else "  FAIL ") + desc)
    if not ok:
        MISMATCHES.append(desc)

def login_of(name):
    return str(name).strip().lower().replace(" ", "-")

reqs = as_list(get(SN + "/sc_request?sysparm_query=number=" + REQ))
if not reqs:
    reqs = [r for r in as_list(get(SN + "/sc_request")) if str(r.get("number")) == REQ]
assert reqs, "review request %s not found" % REQ
req_sysid = str(reqs[0]["sys_id"])
TODAY = str(reqs[0].get("opened_at") or reqs[0].get("sys_created_on") or "")[:10]
print("review %s sys_id=%s state=%s ref-date=%s" % (REQ, req_sysid, reqs[0].get("request_state"), TODAY))

sys_users = as_list(get(SN + "/sys_user?sysparm_limit=500"))
active_emp_emails = {str(u.get("email")).lower() for u in sys_users if str(u.get("active")).lower() == "true"}
active_emp_names = {str(u.get("name")) for u in sys_users if str(u.get("active")).lower() == "true"}
print("employee directory: %d rows (%d active)" % (len(sys_users), len(active_emp_names)))

entra_users = as_list(get(ENTRA + "/users?$top=500"))
guest_domains = {str(u.get("mail") or u.get("userPrincipalName")).split("@")[-1].lower()
                 for u in entra_users if str(u.get("userType")).lower() == "guest"}
partner_status = {}
table_names = [str(t.get("name") or t.get("u_name")) for t in as_list(get(SN + "/sys_db_object?sysparm_limit=1000"))]
for tbl in table_names:
    if not tbl or tbl in ("sc_request", "sys_user", "sys_choice", "sys_db_object"):
        continue
    rows = as_list(get(SN + "/%s?sysparm_limit=500" % tbl))
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        dom = next((str(v).lower() for v in r.values() if str(v).lower() in guest_domains), None)
        st = next((str(v).lower() for v in r.values() if str(v).lower() in ("active", "decommissioned",
                                                                            "inactive", "retired")), None)
        if dom and st:
            partner_status[dom] = st
print("partner register: %s" % partner_status)

guests = [u for u in entra_users if str(u.get("userType")).lower() == "guest"]
print("guests discovered: %d" % len(guests))

def reasons(g):
    email = str(g.get("mail") or g.get("userPrincipalName")).lower()
    domain = email.split("@")[-1]
    out = []
    exp = str(g.get("accountExpires") or "")[:10]
    if exp and TODAY and exp < TODAY:
        out.append("expired")
    sponsor = str(g.get("sponsor") or "").lower()
    if sponsor and sponsor not in active_emp_emails:
        out.append("orphaned")
    if partner_status.get(domain) not in (None, "active"):
        out.append("decommissioned-partner")
    if str(g.get("displayName")) in active_emp_names:
        out.append("duplicate-of-employee")
    return out

stale, keep = [], []
for g in guests:
    rs = reasons(g)
    (stale if rs else keep).append(g)
    print("  %-16s %-40s %s" % (g.get("displayName"), g.get("mail"), rs or "KEEP"))
print("STALE=%d KEEP=%d" % (len(stale), len(keep)))

org = None
for u in (get(GH + "/user/orgs"), get(GH + "/organizations")):
    for o in as_list(u):
        if o.get("login"):
            org = str(o["login"])
            break
    if org:
        break
assert org, "could not discover github org slug"
print("github org: %s" % org)
outside_before = {str(c.get("login")) for c in as_list(get(GH + "/orgs/%s/outside_collaborators?per_page=100" % org))}
slack_users = as_list(get(SLACK + "/users.list"), "members")
slack_by_email = {str(u.get("profile", {}).get("email")).lower(): str(u.get("id")) for u in slack_users}

for g in stale:
    uid = str(g["id"])
    email = str(g.get("mail") or g.get("userPrincipalName")).lower()
    login = login_of(g.get("displayName"))
    call("PATCH", ENTRA + "/users/" + uid, body={"accountEnabled": False})
    for grp in as_list(get(ENTRA + "/users/%s/memberOf" % uid)):
        gid = str(grp.get("id"))
        if gid and gid != "None":
            call("DELETE", ENTRA + "/groups/%s/members/%s/$ref" % (gid, uid))
    if login in outside_before:
        call("DELETE", GH + "/orgs/%s/outside_collaborators/%s" % (org, login))
    sid = slack_by_email.get(email)
    if sid:
        call("POST", SLACK + "/admin.users.remove", body={"user_id": sid})
    print("  remediated %s (%s)" % (g.get("displayName"), email))

call("PATCH", SN + "/sc_request/%s" % req_sysid,
     body={"request_state": "closed_complete", "state": "3",
           "close_notes": "Reviewed the external-identity estate: disabled and removed the standing access "
                          "of the stale external identities (expired, orphaned-sponsor, decommissioned-"
                          "partner, and duplicate-of-employee) across the directory, source-control org and "
                          "messaging workspace; preserved the legitimately-active external identities and "
                          "the employee identities."})

print("\n--- readback ---")

def entra_enabled(uid):
    u = get(ENTRA + "/users/" + uid)
    return u.get("accountEnabled") if isinstance(u, dict) else None

def egroup_ids(gid):
    return {str(m.get("id")) for m in as_list(get(ENTRA + "/groups/%s/members" % gid))}

def outside_now():
    return {str(c.get("login")) for c in as_list(get(GH + "/orgs/%s/outside_collaborators?per_page=100" % org))}

def slack_deleted(email):
    sid = slack_by_email.get(email.lower())
    if not sid:
        return True
    u = get(SLACK + "/users.info?user=" + sid)
    return bool((u or {}).get("user", {}).get("deleted")) if isinstance(u, dict) else True

all_groups = as_list(get(ENTRA + "/groups?$top=500"))
gname_ids = {str(gr.get("displayName")): str(gr.get("id")) for gr in all_groups}
oc = outside_now()
for g in stale:
    uid = str(g["id"])
    email = str(g.get("mail") or g.get("userPrincipalName")).lower()
    login = login_of(g.get("displayName"))
    nm = g.get("displayName")
    check("%s entra disabled" % nm, entra_enabled(uid) is False)
    in_any_group = any(uid in egroup_ids(gid) for gid in gname_ids.values())
    check("%s removed from all entra groups" % nm, not in_any_group)
    if login in outside_before:
        check("%s github outside-collab removed" % nm, login not in oc)
    if slack_by_email.get(email):
        check("%s slack deactivated" % nm, slack_deleted(email))

req2 = [r for r in as_list(get(SN + "/sc_request")) if str(r.get("number")) == REQ][0]
check("review request closed", str(req2.get("request_state")).startswith("closed") or str(req2.get("state")) == "3")

keep_by_name = {str(g.get("displayName")): g for g in keep}
for nm, g in keep_by_name.items():
    check("[ctrl] %s (keep guest) still enabled" % nm, entra_enabled(str(g["id"])) is True)
    email = str(g.get("mail") or g.get("userPrincipalName")).lower()
    if slack_by_email.get(email):
        check("[ctrl] %s (keep guest) slack active" % nm, not slack_deleted(email))
emp_priya = next((u for u in entra_users if str(u.get("userType")).lower() == "member"
                  and str(u.get("displayName")) in active_emp_names
                  and any(str(gg.get("displayName")) == str(u.get("displayName")) for gg in stale)), None)
if emp_priya:
    check("[ctrl] guest-now-employee's EMPLOYEE identity still enabled", entra_enabled(str(emp_priya["id"])) is True)
    check("[ctrl] employee %s still a github org member" % emp_priya.get("displayName"),
          login_of(emp_priya.get("displayName")) in {str(m.get("login")) for m in as_list(get(GH + "/orgs/%s/members?per_page=100" % org))})
check("[ctrl] marco keep-guest still an outside collaborator", "marco-bianchi" in oc)

print("\n%d mismatch(es)" % len(MISMATCHES))
for m in MISMATCHES:
    print("  FAILED:", m)
sys.exit(1 if MISMATCHES else 0)
