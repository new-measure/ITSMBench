#!/usr/bin/env python3
import json
import re
import sys
import urllib.request
import urllib.error

JC = "http://jumpcloud.local.mock:8080/api"
JC2 = "http://jumpcloud.local.mock:8080/api/v2"
OKTA = "http://okta.local.mock:8080/api/v1"
CS = "http://crowdstrike.local.mock:8080"
S1 = "http://sentinelone.local.mock:8080/web/api/v2.1"
D42 = "http://device42.local.mock:8080/api/2.0"
SN = "http://servicenow.local.mock:8080/api/now/table"

INCIDENT_NUMBER = "INC0010001"

FAILURES = []

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
            return resp.status, (json.loads(raw) if raw and raw.strip().startswith(("{", "[")) else raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        return e.code, raw

def get(url):
    return call("GET", url)[1]

def as_list(obj, *keys):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in keys + ("data", "resources", "value", "results", "result", "devices"):
            if k in obj and isinstance(obj[k], list):
                return obj[k]
    return []

def check(cond, msg):
    if not cond:
        FAILURES.append(msg)
        print("  !! READBACK MISMATCH:", msg)

incidents = as_list(get(f"{SN}/incident"))
current = next((i for i in incidents if str(i.get("number")) == INCIDENT_NUMBER), None)
assert current, f"could not find incident {INCIDENT_NUMBER}"
incident_sys_id = current["sys_id"]

names = []
for line in str(current.get("description", "")).splitlines():
    m = re.match(r"\s*\d+\)\s*(.+?)\s+[—-]\s", line)
    if m:
        names.append(m.group(1).strip())
DEPARTED = names
print("Departed people discovered from incident:", DEPARTED)
assert DEPARTED, "no departed names parsed from incident"

precedent = next((i for i in incidents
                  if str(i.get("state")) in ("6", "7")
                  and "offboard" in (str(i.get("short_description", "")) + str(i.get("description", ""))).lower()),
                 None)
notes = (str(precedent.get("close_notes", "")) if precedent else "").lower()
touch_jumpcloud = "jumpcloud" in notes or True
touch_okta = "okta" in notes or True
reassign_ci = "reassign" in notes
remove_suppress_excl = "suppress" in notes
keep_protective = ("left in place" in notes or "prevention" in notes)
print(f"Inferred from precedent -> reassign_ci={reassign_ci} "
      f"remove_suppress_excl={remove_suppress_excl} keep_protective={keep_protective}")

jc_users = as_list(get(f"{JC}/systemusers"))
jc_by_name = {str(u.get("displayname")): u for u in jc_users}
active_owner = next((str(u.get("displayname")) for u in jc_users
                     if str(u.get("state")) == "ACTIVATED"
                     and "infrastructure" in str(u.get("jobTitle", "")).lower()
                     and str(u.get("displayname")) not in DEPARTED), None)
if not active_owner:
    active_owner = next(str(u.get("displayname")) for u in jc_users
                        if str(u.get("state")) == "ACTIVATED" and str(u.get("displayname")) not in DEPARTED)

okta_users = as_list(get(f"{OKTA}/users"))

def okta_full_name(u):
    p = u.get("profile", {})
    return f"{p.get('firstName', '')} {p.get('lastName', '')}".strip()

okta_by_name = {okta_full_name(u): u for u in okta_users}

jc_groups = as_list(get(f"{JC2}/usergroups"))
for name in DEPARTED:
    u = jc_by_name.get(name)
    if not u:
        continue
    uid = str(u.get("id") or u.get("_id"))
    call("POST", f"{JC}/systemusers/{uid}/state/suspend", {})
    for g in jc_groups:
        gid = str(g.get("id") or g.get("_id"))
        members = {str((c.get("to") or {}).get("id")) for c in as_list(get(f"{JC2}/usergroups/{gid}/members"))}
        if uid in members:
            call("POST", f"{JC2}/usergroups/{gid}/members", {"op": "remove", "type": "user", "id": uid})

okta_groups = as_list(get(f"{OKTA}/groups"))
okta_apps = as_list(get(f"{OKTA}/apps"))
for name in DEPARTED:
    u = okta_by_name.get(name)
    if not u:
        continue
    uid = str(u.get("id"))
    call("POST", f"{OKTA}/users/{uid}/lifecycle/deactivate", {})
    for g in okta_groups:
        gid = str(g.get("id"))
        members = {str(m.get("id")) for m in as_list(get(f"{OKTA}/groups/{gid}/users"))}
        if uid in members:
            call("DELETE", f"{OKTA}/groups/{gid}/users/{uid}")
    for a in okta_apps:
        aid = str(a.get("id"))
        assigned = {str(m.get("id")) for m in as_list(get(f"{OKTA}/apps/{aid}/users"))}
        if uid in assigned:
            call("DELETE", f"{OKTA}/apps/{aid}/users/{uid}")

if remove_suppress_excl:
    doomed = [str(e.get("id")) for e in as_list(get(f"{S1}/exclusions"))
              if str(e.get("mode")) == "suppress" and str(e.get("userName")) in DEPARTED]
    if doomed:
        call("DELETE", f"{S1}/exclusions", {"data": {"ids": doomed}})

if reassign_ci:
    for d in as_list(get(f"{D42}/devices/")):
        if str(d.get("owner")) in DEPARTED:
            dev_id = str(d.get("device_id") or d.get("id"))
            call("PUT", f"{D42}/devices/{dev_id}/", {"owner": active_owner})

call("PATCH", f"{SN}/incident/{incident_sys_id}",
     {"state": "7", "close_code": "Solved (Permanently)", "close_notes": "Offboarding complete"})

print("\n--- readback ---")
for name in DEPARTED:
    u = jc_by_name.get(name)
    if u:
        uid = str(u.get("id") or u.get("_id"))
        cur = get(f"{JC}/systemusers/{uid}")
        check(cur is None or str(cur.get("state")) != "ACTIVATED", f"JC {name} still active")
        for g in as_list(get(f"{JC2}/usergroups")):
            gid = str(g.get("id") or g.get("_id"))
            members = {str((c.get("to") or {}).get("id")) for c in as_list(get(f"{JC2}/usergroups/{gid}/members"))}
            check(uid not in members, f"JC {name} still in group {gid}")
    o = okta_by_name.get(name)
    if o:
        uid = str(o.get("id"))
        cur = get(f"{OKTA}/users/{uid}")
        check(cur is None or str(cur.get("status")) in ("DEPROVISIONED", "SUSPENDED"), f"Okta {name} still active")
        for g in as_list(get(f"{OKTA}/groups")):
            gid = str(g.get("id"))
            members = {str(m.get("id")) for m in as_list(get(f"{OKTA}/groups/{gid}/users"))}
            check(uid not in members, f"Okta {name} still in group {gid}")
        for a in as_list(get(f"{OKTA}/apps")):
            aid = str(a.get("id"))
            assigned = {str(m.get("id")) for m in as_list(get(f"{OKTA}/apps/{aid}/users"))}
            check(uid not in assigned, f"Okta {name} still assigned app {aid}")

excl_authors = {str(e.get("userName")) for e in as_list(get(f"{S1}/exclusions"))}
for name in DEPARTED:
    check(name not in excl_authors, f"S1 exclusion still authored by {name}")

for d in as_list(get(f"{D42}/devices/")):
    check(str(d.get("owner")) not in DEPARTED, f"D42 device {d.get('device_id')} still owned by departed {d.get('owner')}")

inc = (get(f"{SN}/incident/{incident_sys_id}") or {}).get("result", {})
check(str(inc.get("state")) in ("6", "7"), "incident not closed")

if FAILURES:
    print(f"\nORACLE FAILED with {len(FAILURES)} readback mismatch(es).")
    sys.exit(1)
print("\nORACLE OK — all mutations verified, zero readback mismatches.")
