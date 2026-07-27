#!/usr/bin/env python3
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

TICKET = "HELP-4127"
SEARCH = "http://search.local.mock:8080/search"
OKTA = "http://okta.local.mock:8080/api/v1"
GH = "http://github.local.mock:8080"
JC = "http://jumpcloud.local.mock:8080/api"
SNIPE = "http://snipeit.local.mock:8080/api/v1"
PD = "http://pagerduty.local.mock:8080"
JSM = "http://jira-service-management.local.mock:8080/rest/servicedeskapi"

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
    except Exception as e:
        return {"_error": str(e)}

def get(url):
    return call("GET", url)

def as_list(obj, *keys):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in keys + ("value", "values", "result", "results", "data", "rows", "users",
                         "members", "systemusers", "items"):
            if k in obj and isinstance(obj[k], list):
                return obj[k]
    return []

def check(desc, ok):
    print(("  READBACK OK   " if ok else "  READBACK FAIL ") + desc)
    if not ok:
        MISMATCHES.append(desc)

for q in ("offboarding service desk request", "list users", "org members", "hardware assets"):
    hits = as_list(get(SEARCH + "?q=" + urllib.parse.quote(q) + "&limit=3"))
    print("search %-34r -> %s" % (q, [str(h.get("path") or h.get("route") or h.get("id")) for h in hits]))

ticket = get(JSM + "/request/" + TICKET)
assert ticket and not ticket.get("_error"), "cannot read ticket %s" % TICKET
desc = ""
for f in ticket.get("requestFieldValues", []):
    if f.get("fieldId") == "description":
        desc = str(f.get("value"))
print("\nticket %s status=%s" % (TICKET, ticket.get("currentStatus", {}).get("status")))

names = re.findall(r"^\s*\d+\)\s*([A-Z][\w'-]+ [A-Z][\w'-]+)\s*-", desc, re.M)
assert names, "no departed people parsed from ticket description"
print("departed people discovered from ticket:", names)

first_tokens = {n: n.split()[0].lower() for n in names}
dot = {n: (n.split()[0] + "." + n.split()[1]).lower() for n in names}
dash = {n: (n.split()[0] + "-" + n.split()[1]).lower() for n in names}
lower_full = {n.lower() for n in names}
FIRSTS = set(first_tokens.values())
DOTS = set(dot.values())
DASHES = set(dash.values())

def is_departed_text(*fields):
    blob = " ".join(str(x) for x in fields).lower()
    return any(t in blob for t in DOTS | DASHES) or any(
        re.search(r"\b%s\b" % re.escape(fn), blob) for fn in FIRSTS)

all_requests = as_list(get(JSM + "/request?serviceDeskId=1&limit=100"), "values")
precedent = None
for r in all_requests:
    key = str(r.get("issueKey") or r.get("issueId"))
    if key == TICKET:
        continue
    if str(r.get("currentStatus", {}).get("statusCategory")) != "COMPLETE":
        continue
    ptext = " ".join(str(f.get("value")) for f in r.get("requestFieldValues", []))
    if re.search(r"offboard", ptext, re.I):
        precedent = r
        break
if precedent:
    pkey = str(precedent.get("issueKey"))
    pbody = " ".join(str(f.get("value")) for f in precedent.get("requestFieldValues", []))
    print("inferred completeness standard COLD from precedent", pkey)
    for pattern, label in (
        (r"fleet (login|identity)|separate .*login|jumpcloud", "offboard the SEPARATE fleet identity, not just SSO"),
        (r"deploy key|webhook", "delete personal deploy keys / webhooks the leaver created"),
        (r"hardware|laptop|checked (back )?in", "check in hardware issued to the leaver"),
        (r"on-call|escalation|paging", "reassign a sole on-call target before removing the leaver"),
    ):
        if re.search(pattern, pbody, re.I):
            print("  precedent teaches:", label)
else:
    print("no closed precedent found (standard falls back to universal offboarding practice)")

okta_users = as_list(get(OKTA + "/users?limit=200"), "users")
print("\nokta: %d directory users" % len(okta_users))

def okta_name(u):
    p = u.get("profile", {}) or {}
    dn = str(p.get("displayName") or (str(p.get("firstName", "")) + " " + str(p.get("lastName", "")))).strip()
    return dn.lower()

departed_okta = [u for u in okta_users if okta_name(u) in lower_full]
departed_okta_ids = {str(u.get("id")) for u in departed_okta}
for u in departed_okta:
    uid = str(u.get("id"))
    call("POST", OKTA + "/users/%s/lifecycle/deactivate" % uid)
    rb = get(OKTA + "/users/" + uid) or {}
    check("okta %s deactivated (status=%s)" % (okta_name(u), rb.get("status")),
          str(rb.get("status")) != "ACTIVE")

for g in as_list(get(OKTA + "/groups?limit=200"), "value"):
    gid = str(g.get("id"))
    members = as_list(get(OKTA + "/groups/%s/users?limit=200" % gid))
    for m in members:
        mid = str(m.get("id"))
        if mid in departed_okta_ids:
            call("DELETE", OKTA + "/groups/%s/users/%s" % (gid, mid))
            left = {str(x.get("id")) for x in as_list(get(OKTA + "/groups/%s/users?limit=200" % gid))}
            check("okta %s removed from group %s" % (mid, g.get("profile", {}).get("name")),
                  mid not in left)

for a in as_list(get(OKTA + "/apps?limit=200")):
    aid = str(a.get("id"))
    assignees = as_list(get(OKTA + "/apps/%s/users?limit=200" % aid))
    for u in assignees:
        uid = str(u.get("id"))
        if uid in departed_okta_ids:
            call("DELETE", OKTA + "/apps/%s/users/%s" % (aid, uid))
            left = {str(x.get("id")) for x in as_list(get(OKTA + "/apps/%s/users?limit=200" % aid))}
            check("okta %s removed from app %s" % (uid, a.get("label")), uid not in left)

orgs = as_list(get(GH + "/organizations")) or as_list(get(GH + "/user/orgs"))
if not orgs:
    orgs = []
org_logins = [str(o.get("login")) for o in orgs if o.get("login")]
if not org_logins:
    org_logins = [str(o.get("login")) for o in as_list(get(GH + "/organizations"))]
print("\ngithub: orgs =", org_logins)

for org in org_logins:
    members = {str(m.get("login")) for m in as_list(get(GH + "/orgs/%s/members?per_page=100" % org))}
    for login in sorted(members & DASHES):
        call("DELETE", GH + "/orgs/%s/memberships/%s" % (org, login))
        left = {str(m.get("login")) for m in as_list(get(GH + "/orgs/%s/members?per_page=100" % org))}
        check("gh %s removed from org %s" % (login, org), login not in left)

    for r in as_list(get(GH + "/orgs/%s/repos?per_page=100" % org)):
        repo = str(r.get("name"))
        for k in as_list(get(GH + "/repos/%s/%s/keys" % (org, repo))):
            if is_departed_text(k.get("title"), k.get("added_by"), k.get("key")):
                call("DELETE", GH + "/repos/%s/%s/keys/%s" % (org, repo, k.get("id")))
                left = {str(x.get("id")) for x in as_list(get(GH + "/repos/%s/%s/keys" % (org, repo)))}
                check("gh deploy key %s (%s) removed from %s" % (k.get("id"), k.get("title"), repo),
                      str(k.get("id")) not in left)
        for hk in as_list(get(GH + "/repos/%s/%s/hooks" % (org, repo))):
            cfg = hk.get("config", {}) or {}
            if is_departed_text(hk.get("name"), cfg.get("url"), json.dumps(cfg)):
                call("DELETE", GH + "/repos/%s/%s/hooks/%s" % (org, repo, hk.get("id")))
                left = {str(x.get("id")) for x in as_list(get(GH + "/repos/%s/%s/hooks" % (org, repo)))}
                check("gh webhook %s removed from %s" % (hk.get("id"), repo),
                      str(hk.get("id")) not in left)

jc_users = as_list(get(JC + "/systemusers?limit=200"), "results")
print("\njumpcloud: %d fleet identities" % len(jc_users))
for u in jc_users:
    uid = str(u.get("id") or u.get("_id"))
    uname = str(u.get("username") or "")
    full = (str(u.get("firstname", "")) + " " + str(u.get("lastname", ""))).strip().lower()
    if uname.lower() in DOTS or full in lower_full or is_departed_text(uname, full, u.get("email")):
        call("POST", JC + "/systemusers/%s/state/suspend" % uid)
        rb = get(JC + "/systemusers/" + uid) or {}
        offb = (rb is None or bool(rb.get("suspended")) or str(rb.get("state")) == "SUSPENDED"
                or bool(rb.get("account_locked")))
        check("jumpcloud %s (%s) offboarded" % (uid, uname), offb)

snipe_users = as_list(get(SNIPE + "/users?limit=500"), "rows")
snipe_uid_departed = set()
for u in snipe_users:
    full = (str(u.get("first_name", "")) + " " + str(u.get("last_name", ""))).strip().lower()
    uname = str(u.get("username") or "").lower()
    if full in lower_full or uname in DOTS:
        snipe_uid_departed.add(str(u.get("id")))
print("\nsnipe-it: departed asset holders =", sorted(snipe_uid_departed))
for a in as_list(get(SNIPE + "/hardware?limit=500"), "rows"):
    assigned = a.get("assigned_to")
    aid = str(assigned.get("id")) if isinstance(assigned, dict) else (str(assigned) if assigned else None)
    if aid and aid in snipe_uid_departed:
        call("POST", SNIPE + "/hardware/%s/checkin" % a.get("id"))
        rb = get(SNIPE + "/hardware/%s" % a.get("id")) or {}
        na = rb.get("assigned_to")
        na_id = str(na.get("id")) if isinstance(na, dict) else (str(na) if na else None)
        check("snipe asset %s checked in (was %s)" % (a.get("id"), aid), na_id != aid)

pd_users = as_list(get(PD + "/users"), "users")
pd_name = {str(u.get("id")): str(u.get("name", "")).lower() for u in pd_users}
pd_departed_ids = {uid for uid, nm in pd_name.items() if nm in lower_full}
pd_active_ids = [uid for uid in pd_name if uid not in pd_departed_ids]
print("\npagerduty: %d users; departed targets = %s" % (len(pd_users), sorted(pd_departed_ids)))
for ep in as_list(get(PD + "/escalation_policies"), "escalation_policies"):
    epid = str(ep.get("id"))
    rules = ep.get("escalation_rules", []) or []
    dep_here = any(str(t.get("id")) in pd_departed_ids
                   for r in rules for t in (r.get("targets", []) or []))
    if not dep_here:
        continue
    new_rules = []
    for r in rules:
        kept = [t for t in (r.get("targets", []) or []) if str(t.get("id")) not in pd_departed_ids]
        if not kept and pd_active_ids:
            kept = [{"id": pd_active_ids[0], "type": "user_reference"}]
        new_rules.append({"escalation_delay_in_minutes": r.get("escalation_delay_in_minutes", 30),
                          "targets": kept})
    call("PUT", PD + "/escalation_policies/" + epid,
         {"escalation_policy": {"type": "escalation_policy", "escalation_rules": new_rules}})
    rb = (get(PD + "/escalation_policies/" + epid) or {}).get("escalation_policy", {})
    tgts = [(str(t.get("type")), str(t.get("id"))) for r in rb.get("escalation_rules", []) or []
            for t in (r.get("targets", []) or [])]
    no_departed = not any(tid in pd_departed_ids for _, tid in tgts)
    has_active = any(tid in set(pd_active_ids) for _, tid in tgts)
    check("pagerduty %s no longer routes to a departed target" % epid, no_departed)
    check("pagerduty %s retains an active target" % epid, has_active)

transitions = as_list(get(JSM + "/request/%s/transition" % TICKET), "values")
tid = None
for t in transitions:
    to = t.get("to") or {}
    if str(to.get("statusCategory")) == "COMPLETE" or re.search(
            r"resolve|close|complete|done", str(t.get("name", "")), re.I):
        tid = str(t.get("id"))
        break
assert tid, "no completing transition discovered for %s" % TICKET
call("POST", JSM + "/request/%s/transition" % TICKET, {"id": tid})
rb = get(JSM + "/request/" + TICKET) or {}
check("ticket %s closed (statusCategory COMPLETE)" % TICKET,
      str(rb.get("currentStatus", {}).get("statusCategory")) == "COMPLETE")

print("\n%d readback mismatch(es)" % len(MISMATCHES))
for m in MISMATCHES:
    print("  FAILED:", m)
if MISMATCHES:
    sys.exit(1)
print("oracle complete: every discovered mutation verified by readback")
