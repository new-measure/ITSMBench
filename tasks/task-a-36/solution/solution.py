#!/usr/bin/env python3
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

TICKET_NUMBER = "INC0407721"
SEARCH = "http://search.local.mock:8080"

FAILURES = []

def log(msg):
    print(msg, flush=True)

def fail(msg):
    FAILURES.append(msg)
    log("READBACK MISMATCH / ORACLE FAILURE: " + msg)

def _req(method, url, payload=None):
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, None

def get(url):
    status, body = _req("GET", url)
    return body if status < 400 else None

def must(method, url, payload=None, ok=(200, 201, 204)):
    status, body = _req(method, url, payload)
    if status not in ok:
        fail("%s %s -> HTTP %s" % (method, url, status))
    return body

def values(obj):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in ("value", "values", "result"):
            if isinstance(obj.get(k), list):
                return obj[k]
    return []

def list_all(url):
    sep = "&" if "?" in url else "?"
    page = url + sep + "$top=999"
    out = []
    while page:
        body = get(page)
        if body is None:
            break
        out.extend(values(body))
        page = body.get("@odata.nextLink") if isinstance(body, dict) else None
    return out

def discover_hosts():
    hosts = {}
    for term in ("user account", "group members", "directory role", "application owners",
                 "managed device", "security incident", "team members", "site permissions",
                 "servicenow incident"):
        body = get(SEARCH + "/search?q=%s&limit=10" % urllib.parse.quote(term))
        for r in values((body or {}).get("results")):
            hosts[r.get("provider", "")] = r.get("host", "")
    return hosts

HOSTS = discover_hosts()

def base(provider, default_host):
    host = HOSTS.get(provider) or default_host
    return "http://%s:8080" % host

SN = base("servicenow", "servicenow.local.mock")
ENTRA = base("entra-id", "entra-id.local.mock") + "/v1.0"
M365 = base("microsoft-365", "microsoft-365.local.mock") + "/v1.0"
INTUNE = base("microsoft-intune", "microsoft-intune.local.mock") + "/v1.0"
DEFENDER = base("microsoft-defender", "microsoft-defender.local.mock") + "/v1.0"
TEAMS = base("microsoft-teams", "microsoft-teams.local.mock") + "/v1.0"
SP = base("sharepoint", "sharepoint.local.mock") + "/v1.0"
log("discovered hosts: " + json.dumps(HOSTS, indent=None, sort_keys=True))

all_incidents = values(get(SN + "/api/now/table/incident"))
ticket = next((t for t in all_incidents if str(t.get("number")) == TICKET_NUMBER), None)
if ticket is None:
    sys.exit("cannot discover ticket %s" % TICKET_NUMBER)
ticket_sys_id = ticket["sys_id"]
log("ticket %s sys_id=%s state=%s" % (TICKET_NUMBER, ticket_sys_id, ticket.get("state")))

precedent = None
for inc in all_incidents:
    if str(inc.get("number")) == TICKET_NUMBER:
        continue
    if str(inc.get("state")) not in ("6", "7"):
        continue
    blob = " ".join(str(inc.get(f, "")) for f in ("short_description", "description", "close_notes"))
    if re.search(r"offboard", blob, re.I):
        precedent = inc
        break
if precedent:
    pblob = " ".join(str(precedent.get(f, "")) for f in ("short_description", "description", "close_notes"))
    log("inferred completeness standard COLD from precedent %s" % precedent.get("number"))
    for pat, label in (
        (r"could no longer authenticate|both of their logins|every .*account", "offboard every identity"),
        (r"group|role|team|site", "strip every group/role/team/site grant"),
        (r"retired|wiped|device", "retire/wipe enrolled devices"),
        (r"sole owner|handed over|orphaned", "hand over a sole-owned resource (do not orphan)"),
    ):
        if re.search(pat, pblob, re.I):
            log("  precedent teaches: " + label)
else:
    log("no closed precedent found; falling back to universal offboarding practice")

names = []
for line in str(ticket.get("description", "")).splitlines():
    m = re.match(r"\s*\d+\)\s*(.+?)\s+-\s", line)
    if m:
        names.append(m.group(1).strip())
if not names:
    sys.exit("no departed individuals parsed from the ticket description")
log("departed individuals on ticket: %s" % names)
lnames = {n.casefold() for n in names}

entra_users = list_all(ENTRA + "/users")
m365_users = list_all(M365 + "/users")

def departed_of(users):
    return [u for u in users if str(u.get("displayName", "")).casefold() in lnames]

dep_entra = departed_of(entra_users)
dep_m365 = departed_of(m365_users)
DEP_IDS = {str(u["id"]) for u in dep_entra} | {str(u["id"]) for u in dep_m365}
DEP_UPNS = {str(u.get("userPrincipalName", "")) for u in dep_entra + dep_m365}
DEP_MAILS = {str(u.get("mail", "")) for u in dep_entra + dep_m365}
log("discovered %d departed identities (Entra) / %d (M365): %s"
    % (len(dep_entra), len(dep_m365), sorted(DEP_IDS)))
if len(dep_entra) < len(names):
    fail("fewer Entra identities (%d) than ticket names (%d)" % (len(dep_entra), len(names)))

def replacement(users):
    cands = [u for u in users
             if u.get("accountEnabled") is True
             and str(u["id"]) not in DEP_IDS
             and str(u.get("userType", "Member")) != "Guest"
             and str(u.get("employeeType", "")) == "Employee"]
    dep_depts = {str(u.get("department", "")) for u in dep_entra}
    same = [u for u in cands if str(u.get("department", "")) in dep_depts]
    pool = same or cands
    return sorted(pool, key=lambda u: str(u.get("userPrincipalName", "")))[0]

repl = replacement(entra_users)
log("handover target (active staff): %s (%s)" % (repl["id"], repl.get("userPrincipalName")))

for base_url, users in ((ENTRA, dep_entra), (M365, dep_m365)):
    for u in users:
        uid = str(u["id"])
        must("PATCH", "%s/users/%s" % (base_url, uid), {"accountEnabled": False})
        back = get("%s/users/%s" % (base_url, uid))
        if not back or back.get("accountEnabled") is not False:
            fail("disable did not stick for %s at %s" % (uid, base_url))
log("disabled %d Entra + %d M365 identities (readback ok)" % (len(dep_entra), len(dep_m365)))

def strip_membership(list_url, member_url_fmt, del_url_fmt, kind):
    removed = 0
    for holder in list_all(list_url):
        hid = str(holder["id"])
        members = {str(m.get("id")) for m in values(get(member_url_fmt % hid))}
        for uid in sorted(members & DEP_IDS):
            must("DELETE", del_url_fmt % (hid, uid))
            back = {str(m.get("id")) for m in values(get(member_url_fmt % hid))}
            if uid in back:
                fail("%s member %s still present in %s after delete" % (kind, uid, hid))
            removed += 1
    log("removed %d departed %s memberships (readback ok)" % (removed, kind))

strip_membership(ENTRA + "/groups", ENTRA + "/groups/%s/members",
                 ENTRA + "/groups/%s/members/%s/$ref", "Entra group")
strip_membership(M365 + "/directoryRoles", M365 + "/directoryRoles/%s/members",
                 M365 + "/directoryRoles/%s/members/%s/$ref", "M365 directory-role")

reverse_owned = {}
for uid in sorted(DEP_IDS):
    reverse_owned[uid] = {str(o.get("id")) for o in values(get(M365 + "/users/%s/ownedObjects" % uid))}

forward_owned = {uid: set() for uid in DEP_IDS}
ownables = [("applications", list_all(M365 + "/applications")),
            ("servicePrincipals", list_all(M365 + "/servicePrincipals")),
            ("groups", list_all(M365 + "/groups"))]
for _, records in ownables:
    for rec in records:
        for uid in {str(o) for o in rec.get("owners", [])} & DEP_IDS:
            forward_owned[uid].add(str(rec["id"]))

for uid in sorted(DEP_IDS):
    if not forward_owned[uid] <= reverse_owned[uid]:
        fail("PROVIDER DEFECT: /users/%s/ownedObjects (%s) omits forward-owned objects (%s)"
             % (uid, sorted(reverse_owned[uid]), sorted(forward_owned[uid])))

owned_targets = sorted({(oid) for uid in DEP_IDS for oid in forward_owned[uid] | reverse_owned[uid]})
log("owned-object discovery: reverse lookup consistent with forward owners; targets=%s" % owned_targets)

for kind, records in ownables:
    for rec in records:
        oid = str(rec["id"])
        owners = {str(o) for o in rec.get("owners", [])}
        dep_owners = owners & DEP_IDS
        if not dep_owners:
            continue
        item = "%s/%s/%s" % (M365, kind, oid)
        if not (owners - DEP_IDS):
            must("POST", item + "/owners/$ref",
                 {"@odata.id": "https://graph.microsoft.com/v1.0/directoryObjects/%s" % repl["id"]})
        for uid in sorted(dep_owners):
            must("DELETE", item + "/owners/%s/$ref" % uid)
        back = {str(o.get("id")) for o in values(get(item + "/owners"))}
        if back & DEP_IDS or not (back - DEP_IDS):
            fail("handover failed for %s %s: owners now %s" % (kind, oid, sorted(back)))
        else:
            log("handed over %s %s: owners now %s (readback ok)" % (kind, oid, sorted(back)))

devices = list_all(INTUNE + "/deviceManagement/managedDevices")
for dev in devices:
    if str(dev.get("userId")) not in DEP_IDS:
        continue
    did = str(dev["id"])
    action = "wipe" if str(dev.get("managedDeviceOwnerType")) == "personal" else "retire"
    must("POST", "%s/deviceManagement/managedDevices/%s/%s" % (INTUNE, did, action))
    back = get("%s/deviceManagement/managedDevices/%s" % (INTUNE, did))
    state = str((back or {}).get("managementState"))
    if back is not None and state not in ("retirePending", "wipePending"):
        fail("device %s not offboarded after %s (state=%s)" % (did, action, state))
    else:
        log("device %s -> %s (state=%s, readback ok)" % (did, action, state))

repl_upn = str(repl.get("userPrincipalName"))
for path in ("/security/incidents", "/security/alerts_v2"):
    for case in list_all(DEFENDER + path):
        owner = str(case.get("assignedTo") or "")
        if owner not in (DEP_UPNS | DEP_MAILS | DEP_IDS):
            continue
        cid = str(case["id"])
        must("PATCH", DEFENDER + path + "/" + cid, {"assignedTo": repl_upn})
        back = get(DEFENDER + path + "/" + cid)
        if str((back or {}).get("assignedTo")) != repl_upn:
            fail("case %s%s still assigned to %s" % (path, cid, (back or {}).get("assignedTo")))
        else:
            log("reassigned %s/%s -> %s (readback ok)" % (path.rsplit("/", 1)[-1], cid, repl_upn))

for team in list_all(TEAMS + "/teams"):
    tid = str(team["id"])
    for m in values(get(TEAMS + "/teams/%s/members" % tid)):
        if str(m.get("userId")) not in DEP_IDS:
            continue
        must("DELETE", "%s/teams/%s/members/%s" % (TEAMS, tid, m["id"]))
        back = {str(x.get("userId")) for x in values(get(TEAMS + "/teams/%s/members" % tid))}
        if str(m.get("userId")) in back:
            fail("team %s still has departed member %s" % (tid, m.get("userId")))
        else:
            log("removed %s from team %s (readback ok)" % (m.get("userId"), tid))

def grant_user_ids(perm):
    ids = set()
    for node in (perm.get("grantedToV2"), perm.get("grantedTo")):
        ids.add(str(((node or {}).get("user") or {}).get("id")))
    for ident in values(perm.get("grantedToIdentitiesV2")) + values(perm.get("grantedToIdentities")):
        ids.add(str(((ident or {}).get("user") or {}).get("id")))
    return ids

for site in list_all(SP + "/sites"):
    sid = str(site["id"])
    for perm in values(get(SP + "/sites/%s/permissions" % sid)):
        if not (grant_user_ids(perm) & DEP_IDS):
            continue
        pid = str(perm["id"])
        must("DELETE", "%s/sites/%s/permissions/%s" % (SP, sid, pid))
        left = [p for p in values(get(SP + "/sites/%s/permissions" % sid))
                if grant_user_ids(p) & DEP_IDS]
        if any(str(p["id"]) == pid for p in left):
            fail("site %s grant %s survived delete" % (sid, pid))
        else:
            log("removed grant %s on site %s (readback ok)" % (pid, sid))

must("PATCH", "%s/api/now/table/incident/%s" % (SN, ticket_sys_id), {"state": "6"})
back = get("%s/api/now/table/incident/%s" % (SN, ticket_sys_id))
state = str(((back or {}).get("result") or {}).get("state"))
if state not in ("6", "7"):
    fail("ticket not closed (state=%s)" % state)
else:
    log("ticket %s closed (state=%s, readback ok)" % (TICKET_NUMBER, state))

if FAILURES:
    log("\nORACLE FAILED: %d readback/consistency failure(s)" % len(FAILURES))
    for f in FAILURES:
        log("  - " + f)
    sys.exit(1)
log("\nORACLE OK: all targets discovered cold from ticket %s; every mutation read back." % TICKET_NUMBER)
