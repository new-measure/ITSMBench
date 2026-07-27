#!/usr/bin/env python3
import json
import re
import sys
import urllib.request
import urllib.error

SEARCH = "http://search.local.mock:8080"
ENTRA = "http://entra-id.local.mock:8080/v1.0"
SP = "http://sharepoint.local.mock:8080/v1.0"
OD = "http://onedrive.local.mock:8080/v1.0"
M365 = "http://microsoft-365.local.mock:8080/v1.0"
GH = "http://github.local.mock:8080"
JSM = "http://jira-service-management.local.mock:8080/rest/servicedeskapi"

REQUEST_KEY = "HELP-3301"

FAILURES = []
DISCOVERED = []

def _req(method, url, payload=None, ok=(200, 201, 202, 204)):
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            status = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        status = e.code
    if status not in ok:
        raise RuntimeError(f"{method} {url} -> HTTP {status}: {raw[:400]}")
    return json.loads(raw) if raw else None

def get(url):
    return _req("GET", url)

def as_list(obj, *keys):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in keys + ("value", "values", "result", "hooks", "keys"):
            if k in obj and isinstance(obj[k], list):
                return obj[k]
    return []

def paged(url):
    out, seen = [], set()
    while url and url not in seen:
        seen.add(url)
        obj = get(url)
        out.extend(as_list(obj))
        url = obj.get("@odata.nextLink") if isinstance(obj, dict) else None
    return out

def check(condition, message):
    if condition:
        print(f"  OK  {message}")
    else:
        print(f"  !!! READBACK MISMATCH: {message}")
        FAILURES.append(message)

def found(surface, desc):
    DISCOVERED.append((surface, desc))
    print(f"  DISCOVERED [{surface}] {desc}")

def show_search(q):
    res = get(f"{SEARCH}/search?q={urllib.request.quote(q)}&limit=5")
    tops = [f'{r["method"]} {r["host"]}{r["path"]}' for r in res.get("results", [])[:3]]
    print(f"  search({q!r}) -> " + " | ".join(tops))

print(f"== 1. Read ticket {REQUEST_KEY}")
show_search("service desk request")
ticket = get(f"{JSM}/request/{REQUEST_KEY}")
desc = next(f["value"] for f in ticket["requestFieldValues"] if f["fieldId"] == "description")
contractors = []
for m in re.finditer(r"^\s*\d+\)\s*(.+?)\s+-\s+(.+?)\s+-\s+", desc, re.M):
    contractors.append((m.group(1).strip(), m.group(2).strip()))
if len(contractors) != 6:
    raise RuntimeError(f"expected 6 contractors in the ticket, parsed {contractors}")
names = {n for n, _ in contractors}
print(f"  ticket lists: {sorted(names)}")

print("== 2. Infer the completeness bar COLD from the closed precedent (no runbook exists)")
show_search("list service desk requests")
all_requests = as_list(get(f"{JSM}/request?serviceDeskId=1&limit=100"), "values")
precedent = None
for r in all_requests:
    key = str(r.get("issueKey") or r.get("issueId"))
    if key == REQUEST_KEY:
        continue
    if str((r.get("currentStatus") or {}).get("statusCategory")) != "COMPLETE":
        continue
    ptext = " ".join(str(f.get("value")) for f in r.get("requestFieldValues", []))
    if re.search(r"offboard", ptext, re.I):
        precedent = r
        break
if precedent:
    pkey = str(precedent.get("issueKey"))
    pbody = " ".join(str(f.get("value")) for f in precedent.get("requestFieldValues", []))
    found("jira-service-management", f'closed precedent {pkey} (worked example, resolved to full bar)')
    for pattern, label in (
        (r"guest", "disable every identity incl. a B2B guest"),
        (r"group", "strip every group membership"),
        (r"sole owner|without an owner|reassigned ownership", "reassign a sole-owned site (no orphan)"),
        (r"deploy key", "delete a personal deploy key"),
        (r"application|automation|service identity|webhook", "shut down created apps / service principals / webhooks"),
    ):
        if re.search(pattern, pbody, re.I):
            print("  precedent teaches:", label)
else:
    print("  no closed precedent found (falling back to universal offboarding practice)")

print("== 3. Entra: discover ALL identities of the departed contractors (members AND guests)")
users = paged(f"{ENTRA}/users")
departed = [u for u in users if u["displayName"] in names]
by_name = {}
for u in departed:
    by_name.setdefault(u["displayName"], []).append(u)
for n in sorted(names):
    idents = by_name.get(n, [])
    if not idents:
        raise RuntimeError(f"no Entra identity discovered for departed contractor {n}")
    for u in idents:
        found("entra-id", f'{n}: {u["id"]} ({u.get("userType", "Member")}, {u["userPrincipalName"]})')
departed_ids = {u["id"] for u in departed}
departed_mails = {str(u.get("mail", "")).lower() for u in departed}
active_by_id = {u["id"]: u for u in users if u["id"] not in departed_ids}

print("-- disable every departed identity")
for u in departed:
    _req("PATCH", f'{ENTRA}/users/{u["id"]}', {"accountEnabled": False})
    check(get(f'{ENTRA}/users/{u["id"]}')["accountEnabled"] is False,
          f'{u["displayName"]} ({u["id"]}) accountEnabled=false')

print("-- strip departed users from every group")
for g in paged(f"{ENTRA}/groups"):
    member_ids = {m["id"] for m in paged(f'{ENTRA}/groups/{g["id"]}/members')}
    for uid in sorted(member_ids & departed_ids):
        found("entra-id", f'group membership {g["id"]} ("{g["displayName"]}") -> {uid}')
        _req("DELETE", f'{ENTRA}/groups/{g["id"]}/members/{uid}/$ref')
        check(uid not in {m["id"] for m in paged(f'{ENTRA}/groups/{g["id"]}/members')},
              f'{uid} removed from {g["id"]}')

print("== 4. SharePoint: per-site grants; no-orphaning norm first, then removal")
sites = paged(f"{SP}/sites")

def user_of(perm):
    return ((perm.get("grantedToV2") or {}).get("user") or {})

for s in sites:
    perms = as_list(get(f'{SP}/sites/{s["id"]}/permissions'))
    departed_perms = [p for p in perms if user_of(p).get("id") in departed_ids]
    if not departed_perms:
        continue
    departed_owns = any("owner" in (p.get("roles") or []) for p in departed_perms)
    active_owner_exists = any(
        "owner" in (p.get("roles") or []) and user_of(p).get("id") in active_by_id
        for p in perms)
    if departed_owns and not active_owner_exists:
        candidates = [p for p in perms
                      if user_of(p).get("id") in active_by_id
                      and active_by_id[user_of(p)["id"]].get("accountEnabled")]
        candidates.sort(key=lambda p: 0 if "write" in (p.get("roles") or []) else 1)
        if not candidates:
            raise RuntimeError(f'no active grantee discoverable to take ownership of {s["id"]}')
        heir = user_of(candidates[0])
        found("sharepoint", f'sole-owner site {s["id"]} ("{s["displayName"]}") -> reassign to {heir["id"]}')
        _req("POST", f'{SP}/sites/{s["id"]}/permissions',
             {"roles": ["owner"],
              "grantedToV2": {"user": {"id": heir["id"], "displayName": heir.get("displayName"),
                                       "email": heir.get("email")}}})
        after = as_list(get(f'{SP}/sites/{s["id"]}/permissions'))
        check(any("owner" in (p.get("roles") or []) and user_of(p).get("id") == heir["id"] for p in after),
              f'{s["id"]} now has active owner {heir["id"]}')
    for perm in departed_perms:
        found("sharepoint", f'site grant {s["id"]} perm {perm["id"]} -> {user_of(perm).get("id")} {perm.get("roles")}')
        _req("DELETE", f'{SP}/sites/{s["id"]}/permissions/{perm["id"]}')
    after = as_list(get(f'{SP}/sites/{s["id"]}/permissions'))
    check(not any(user_of(p).get("id") in departed_ids for p in after),
          f'no departed grants remain on {s["id"]}')

print("== 5. OneDrive: enumerate drives -> root children -> per-item permissions")
show_search("onedrive list drive root children")
for d in as_list(get(f"{OD}/drives")):
    root = get(f'{OD}/drives/{d["id"]}/root')
    print(f'  drive {d["id"]} root item {root["id"]}')
    queue = as_list(get(f'{OD}/drives/{d["id"]}/root/children'))
    walked = []
    while queue:
        item = queue.pop(0)
        walked.append(item)
        if item.get("folder"):
            queue.extend(as_list(get(f'{OD}/drives/{d["id"]}/items/{item["id"]}/children')))
    if not walked:
        raise RuntimeError(f'drive {d["id"]} enumerated ZERO items from /root/children — provider defect')
    for item in walked:
        perms = as_list(get(f'{OD}/drives/{d["id"]}/items/{item["id"]}/permissions'))
        for perm in perms:
            if user_of(perm).get("id") in departed_ids:
                found("onedrive", f'item {item["id"]} ("{item["name"]}") perm {perm["id"]} -> {user_of(perm)["id"]}')
                _req("DELETE", f'{OD}/drives/{d["id"]}/items/{item["id"]}/permissions/{perm["id"]}')
        after = as_list(get(f'{OD}/drives/{d["id"]}/items/{item["id"]}/permissions'))
        check(not any(user_of(p).get("id") in departed_ids for p in after),
              f'no departed grants remain on item {item["id"]} ("{item["name"]}")')

print("== 6. M365: neutralize created artifacts (apps / service principals) owned by departed users")
show_search("application registrations owners")
for kind, base in (("application", f"{M365}/applications"), ("servicePrincipal", f"{M365}/servicePrincipals")):
    for rec in paged(base):
        owners = [str(o) for o in as_list(rec.get("owners"))]
        if not any(o in departed_ids for o in owners):
            continue
        creds = len(as_list(rec.get("passwordCredentials"))) + len(as_list(rec.get("keyCredentials")))
        found("microsoft-365", f'{kind} {rec["id"]} ("{rec["displayName"]}") owned by departed, {creds} live credential(s)')
        _req("DELETE", f'{base}/{rec["id"]}')
        check(not any(str(r.get("id")) == str(rec["id"]) for r in paged(base)),
              f'{kind} {rec["id"]} deleted')

print("== 7. GitHub: deploy keys + org webhooks left behind by departed contractors")
show_search("github organization webhooks")
repos = as_list(get(f"{GH}/repositories"))
orgs = sorted({(r.get("owner") or {}).get("login") for r in repos if (r.get("owner") or {}).get("login")})
print(f"  repositories: {[r['full_name'] for r in repos]} orgs: {orgs}")
for r in repos:
    owner, repo = r["full_name"].split("/", 1)
    for key in as_list(get(f"{GH}/repos/{owner}/{repo}/keys")):
        if any(name in str(key.get("title", "")) for name in names):
            found("github", f'deploy key {key["id"]} ("{key["title"]}") on {r["full_name"]}')
            _req("DELETE", f'{GH}/repos/{owner}/{repo}/keys/{key["id"]}')
            check(not any(k.get("id") == key["id"] for k in as_list(get(f"{GH}/repos/{owner}/{repo}/keys"))),
                  f'deploy key {key["id"]} deleted from {r["full_name"]}')
for org in orgs:
    for hook in as_list(get(f"{GH}/orgs/{org}/hooks")):
        creator = hook.get("created_by") or {}
        creator_mail = str(creator.get("email", "")).lower()
        creator_name = str(creator.get("name", ""))
        if creator_mail in departed_mails or creator_name in names:
            found("github", f'org webhook {hook["id"]} -> {hook.get("config", {}).get("url")} created_by {creator_name}')
            _req("DELETE", f'{GH}/orgs/{org}/hooks/{hook["id"]}')
            check(not any(h.get("id") == hook["id"] for h in as_list(get(f"{GH}/orgs/{org}/hooks"))),
                  f'org webhook {hook["id"]} deleted from {org}')

print(f"== 8. Close {REQUEST_KEY}")
transitions = as_list(get(f"{JSM}/request/{REQUEST_KEY}/transition"))
resolve = next((t for t in transitions
                if str((t.get("to") or {}).get("statusCategory")) == "COMPLETE"
                or "resolve" in str(t.get("name", "")).lower()), None)
if resolve is None:
    raise RuntimeError(f"no resolving transition discoverable: {transitions}")
found("jira-service-management", f'transition {resolve["id"]} ("{resolve.get("name")}")')
_req("POST", f"{JSM}/request/{REQUEST_KEY}/transition", {"id": resolve["id"]})
check(get(f"{JSM}/request/{REQUEST_KEY}")["currentStatus"]["statusCategory"] == "COMPLETE",
      f"{REQUEST_KEY} statusCategory COMPLETE")

print()
print(f"oracle discovered {len(DISCOVERED)} targets cold across "
      f"{len({s for s, _ in DISCOVERED})} surfaces")
if FAILURES:
    print(f"ORACLE FAILED: {len(FAILURES)} readback mismatch(es):")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
print("ORACLE COMPLETE: zero readback mismatches")
