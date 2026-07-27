#!/usr/bin/env python3

import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta

JSM = "http://jira-service-management.local.mock:8080/rest/servicedeskapi"
HR = "http://bamboohr.local.mock:8080/api/v1"
ENTRA = "http://entra-id.local.mock:8080/v1.0"
INTUNE = "http://microsoft-intune.local.mock:8080/v1.0"
CS = "http://crowdstrike.local.mock:8080"
SNIPE = "http://snipeit.local.mock:8080/api/v1"

TICKET_KEY = "ITSD-482"
COHORT_WINDOW_DAYS = 14
GRACE_DAYS = 5

failures = []

def die(msg):
    print(f"FATAL: {msg}", file=sys.stderr)
    sys.exit(1)

def note_failure(msg):
    failures.append(msg)
    print(f"MISMATCH: {msg}", file=sys.stderr)

def call(method, url, body=None, ok=(200, 201, 202, 204)):
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            status = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read()
        status = e.code
    if status not in ok:
        die(f"{method} {url} -> HTTP {status}: {raw[:300]!r}")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        die(f"{method} {url} -> non-JSON body {raw[:200]!r}")

def get(url):
    return call("GET", url)

def rows(payload):
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    for key in ("rows", "value", "resources", "data", "values"):
        if isinstance(payload.get(key), list):
            return payload[key]
    return []

def ts(value):
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("datetime") or value.get("iso8601") or value.get("date")
    if not isinstance(value, str) or not value:
        return None
    value = value.strip().replace("Z", "+00:00")
    for candidate in (value, value.split("+")[0]):
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed.replace(tzinfo=None)
        except ValueError:
            continue
    return None

def norm(s):
    return (s or "").strip().lower()

def fetch_all_snipe(path):
    out, offset = [], 0
    while True:
        payload = get(f"{SNIPE}{path}{'&' if '?' in path else '?'}limit=500&offset={offset}")
        batch = rows(payload)
        out.extend(batch)
        total = (payload or {}).get("total", len(out))
        offset += len(batch)
        if not batch or offset >= total:
            return out

def fetch_all_cs(path):
    out, offset = [], 0
    while True:
        payload = get(f"{CS}{path}{'&' if '?' in path else '?'}limit=500&offset={offset}")
        batch = rows(payload)
        out.extend(batch)
        total = (((payload or {}).get("meta") or {}).get("pagination") or {}).get("total", len(out))
        offset += len(batch)
        if not batch or offset >= total:
            return out

def fetch_all_graph(url):
    out = []
    while url:
        payload = get(url)
        out.extend(rows(payload))
        url = (payload or {}).get("@odata.nextLink")
        if url:
            url = url.replace("https://", "http://", 1)
    return out

def obj_id(value):
    if isinstance(value, dict):
        return value.get("id")
    return value

print("== discovery ==")

ticket = get(f"{JSM}/request/{TICKET_KEY}")
if not ticket:
    die(f"ticket {TICKET_KEY} not found in JSM")
field_values = ticket.get("requestFieldValues") or {}
if isinstance(field_values, list):
    field_values = {f.get("fieldId", str(i)): f.get("value") for i, f in enumerate(field_values)}
ticket_text = " ".join(
    str(v) for v in [ticket.get("summary")] + list(field_values.values()) if v
)
if not ticket_text.strip():
    die(f"ticket {TICKET_KEY} has no readable text")

hr_fields = "workEmail,terminationDate,location,hireDate,department,status"
employees = []
next_url = f"{HR}/employees?fields={hr_fields}&page%5Blimit%5D=200"
while next_url:
    payload = get(next_url)
    employees.extend(rows(payload))
    nxt = ((payload or {}).get("_links") or {}).get("next", {}).get("href")
    next_url = f"http://bamboohr.local.mock:8080{nxt}" if nxt and nxt.startswith("/") else nxt
if not employees:
    die("BambooHR returned no employees")

snipe_assets = fetch_all_snipe("/hardware")
snipe_users = fetch_all_snipe("/users")
snipe_labels = fetch_all_snipe("/statuslabels")
snipe_activity = fetch_all_snipe("/reports/activity")
cs_devices = fetch_all_cs("/devices/combined/devices/v1")
intune_devices = fetch_all_graph(f"{INTUNE}/deviceManagement/managedDevices")
entra_users = fetch_all_graph(f"{ENTRA}/users")
for name, coll in [("snipe hardware", snipe_assets), ("crowdstrike devices", cs_devices),
                   ("intune managedDevices", intune_devices), ("entra users", entra_users)]:
    if not coll:
        die(f"{name} inventory is empty — nothing to reason over")

def is_terminated(emp):
    return norm(emp.get("status")) in ("inactive", "terminated") or bool(ts(emp.get("terminationDate")))

def emp_email(emp):
    return norm(emp.get("workEmail"))

def entra_for(email):
    for u in entra_users:
        if norm(u.get("mail")) == email or norm(u.get("userPrincipalName")) == email:
            return u
    local = email.split("@")[0] if "@" in email else email
    for u in entra_users:
        if norm(u.get("userPrincipalName")).split("@")[0] == local:
            return u
    return None

def snipe_user_for(email, display_name=None):
    for u in snipe_users:
        if norm(u.get("email")) == email:
            return u
    if display_name:
        for u in snipe_users:
            if norm(u.get("name")) == norm(display_name):
                return u
    return None

def employee_for_email(email):
    for e in employees:
        if emp_email(e) == norm(email):
            return e
    local = norm(email).split("@")[0] if "@" in (email or "") else None
    if local:
        for e in employees:
            if emp_email(e).split("@")[0] == local:
                return e
    return None

def cs_for(serial=None, hostname=None):
    for d in cs_devices:
        if serial and norm(d.get("serial_number")) == norm(serial):
            return d
        if hostname and norm(d.get("hostname")) == norm(hostname):
            return d
    return None

def intune_for(serial=None, upn=None):
    hits = []
    for d in intune_devices:
        if serial and norm(d.get("serialNumber")) == norm(serial):
            hits.append(d)
        elif upn and norm(d.get("userPrincipalName")) == norm(upn):
            hits.append(d)
    return hits

text_lc = ticket_text.lower()
flagged_asset = None
for asset in snipe_assets:
    for ident in (asset.get("serial"), asset.get("asset_tag"), asset.get("name")):
        if ident and len(str(ident)) >= 4 and str(ident).lower() in text_lc:
            flagged_asset = asset
            break
    if flagged_asset:
        break
if flagged_asset is None:
    for d in cs_devices:
        for ident in (d.get("hostname"), d.get("serial_number")):
            if ident and len(str(ident)) >= 4 and str(ident).lower() in text_lc:
                match = [a for a in snipe_assets
                         if norm(a.get("serial")) == norm(d.get("serial_number"))
                         or norm(a.get("name")) == norm(d.get("hostname"))]
                if match:
                    flagged_asset = match[0]
                break
        if flagged_asset:
            break
if flagged_asset is None:
    die("no device identifier in the ticket text resolves against Snipe-IT/CrowdStrike")
print(f"flagged asset: id={flagged_asset.get('id')} serial={flagged_asset.get('serial')}")

holder_id = obj_id(flagged_asset.get("assigned_to"))
holder = next((u for u in snipe_users if str(u.get("id")) == str(holder_id)), None)
if holder is None:
    die("flagged asset is not checked out to anyone — evidence chain broken")
flagged_leaver = employee_for_email(holder.get("email")) if holder.get("email") else None
if flagged_leaver is None:
    for e in employees:
        full = norm(f"{e.get('firstName', '')} {e.get('lastName', '')}")
        if full and full == norm(holder.get("name")):
            flagged_leaver = e
            break
if flagged_leaver is None or not is_terminated(flagged_leaver):
    die("asset-record holder does not resolve to a terminated employee in BambooHR")
anchor_date = ts(flagged_leaver.get("terminationDate"))
anchor_loc = norm(flagged_leaver.get("location"))
if anchor_date is None or not anchor_loc:
    die("flagged leaver lacks terminationDate/location in BambooHR — cohort undefinable")
print(f"anchor: termination {anchor_date.date()} at location '{flagged_leaver.get('location')}'")

window = timedelta(days=COHORT_WINDOW_DAYS)
cohort = [
    e for e in employees
    if is_terminated(e)
    and norm(e.get("location")) == anchor_loc
    and ts(e.get("terminationDate")) is not None
    and abs(ts(e.get("terminationDate")) - anchor_date) <= window
]
if len(cohort) < 2:
    die(f"cohort collapsed to {len(cohort)} — the site-closure cluster is not discoverable")
print(f"cohort: {len(cohort)} leavers "
      f"({', '.join(e.get('workEmail') or e.get('lastName') or '?' for e in cohort)})")

flagged_intune = intune_for(serial=flagged_asset.get("serial"))
flagged_cs = cs_for(serial=flagged_asset.get("serial"), hostname=flagged_asset.get("name"))
reissued_to = None
if flagged_intune:
    current_upn = flagged_intune[0].get("userPrincipalName")
    candidate = employee_for_email(current_upn) if current_upn else None
    if (candidate is not None and not is_terminated(candidate)
            and ts(candidate.get("hireDate")) is not None
            and ts(candidate.get("hireDate")) > anchor_date):
        reissued_to = candidate
if reissued_to is None:
    die("decoy evidence chain incomplete: flagged device's Intune primary user does not "
        "resolve to an active post-closure hire")
if flagged_cs is not None and ts(flagged_cs.get("last_seen")) is not None \
        and ts(flagged_cs.get("last_seen")) < anchor_date:
    die("decoy evidence chain contradicted: flagged device's sensor went quiet before the "
        "closure — it cannot be the reissued machine")
print(f"decoy confirmed: device reissued to {reissued_to.get('workEmail')} — record is stale")

grace = timedelta(days=GRACE_DAYS)
lost_label = next(
    (l for l in snipe_labels
     if re.search(r"lost|stolen|missing", norm(l.get("name")))), None
) or next((l for l in snipe_labels
           if norm(l.get("status_type") or l.get("status_meta")) == "undeployable"), None)
if lost_label is None:
    die("no undeployable/lost status label exists in Snipe-IT")

deployed_ids = {str(l.get("id")) for l in snipe_labels
                if norm(l.get("status_meta")) == "deployed"
                or norm(l.get("name")) == "deployed"}

def asset_status_id(asset):
    status = asset.get("status_label")
    return str(obj_id(status) if status is not None else asset.get("status_id"))

def leaver_devices(emp):
    email = emp_email(emp)
    entra = entra_for(email)
    upn = entra.get("userPrincipalName") if entra else email
    found = {}

    def slot(serial=None, hostname=None):
        key = norm(serial) or norm(hostname)
        if not key:
            key = f"anon-{len(found)}"
        return found.setdefault(key, {"snipe": None, "intune": None, "cs": None})

    for d in intune_for(upn=upn):
        slot(serial=d.get("serialNumber"), hostname=d.get("deviceName"))["intune"] = d
    su = snipe_user_for(email, f"{emp.get('firstName', '')} {emp.get('lastName', '')}")
    if su:
        for a in snipe_assets:
            if str(obj_id(a.get("assigned_to"))) == str(su.get("id")) \
                    and norm(a.get("assigned_type") or "user").endswith("user"):
                slot(serial=a.get("serial"), hostname=a.get("name"))["snipe"] = a
        past_ids = {
            str(row.get("item_id")) for row in snipe_activity
            if norm(row.get("action_type")) == "checkin"
            and norm(row.get("item_type")) == "hardware"
            and str(row.get("target_id")) == str(su.get("id"))
        }
        for a in snipe_assets:
            if str(a.get("id")) in past_ids \
                    and str(obj_id(a.get("assigned_to")) or "") != str(su.get("id")):
                slot(serial=a.get("serial"), hostname=a.get("name"))["snipe"] = a
    for key, entry in list(found.items()):
        ref = entry["snipe"] or entry["intune"] or {}
        serial = ref.get("serial") or ref.get("serialNumber")
        hostname = ref.get("name") or ref.get("deviceName")
        entry["cs"] = cs_for(serial=serial, hostname=hostname)
        if entry["intune"] is None and serial:
            hit = intune_for(serial=serial)
            entry["intune"] = hit[0] if hit else None
    return found

actions = []
readbacks = []

def plan(desc, thunk, check=None):
    actions.append((desc, thunk))
    if check:
        readbacks.append((desc, check))

def wipe_or_retire(dev, personal):
    dev_id = dev.get("id")
    verb = "retire" if personal else "wipe"
    expect = "retirePending" if personal else "wipePending"
    plan(
        f"intune {verb} {dev_id}",
        lambda: call("POST", f"{INTUNE}/deviceManagement/managedDevices/{dev_id}/{verb}", body={}),
        lambda: get(f"{INTUNE}/deviceManagement/managedDevices/{dev_id}").get("managementState") == expect,
    )

def cs_action(device, action):
    did = device.get("device_id")
    def check():
        payload = call("POST", f"{CS}/devices/entities/devices/v2", body={"ids": [did]})
        fresh = (rows(payload) or [{}])[0]
        return fresh.get("status") == "contained" if action == "contain" else fresh.get("hidden") is True
    plan(
        f"falcon {action} {did}",
        lambda: call("POST", f"{CS}/devices/entities/devices-actions/v2?action_name={action}",
                     body={"ids": [did]}),
        check,
    )

def snipe_checkin(asset, status_id=None, verify=True):
    aid = asset.get("id")
    body = {"status_id": int(status_id)} if status_id else {}
    def check():
        row = get(f"{SNIPE}/hardware/{aid}") or {}
        return row.get("assigned_to") in (None, "", 0) and (
            status_id is None or asset_status_id(row) == str(status_id))
    plan(f"snipe checkin asset {aid}",
         lambda: call("POST", f"{SNIPE}/hardware/{aid}/checkin", body=body),
         check if verify else None)

for emp in cohort:
    email = emp_email(emp)
    term = ts(emp.get("terminationDate"))
    entra = entra_for(email)
    if entra is None:
        die(f"no Entra account resolves for cohort leaver {email}")

    if entra.get("accountEnabled") is True:
        uid = entra.get("id")
        plan(f"entra disable {email}",
             lambda uid=uid: call("PATCH", f"{ENTRA}/users/{uid}", body={"accountEnabled": False}),
             lambda uid=uid: get(f"{ENTRA}/users/{uid}").get("accountEnabled") is False)
    revoked_at = ts(entra.get("signInSessionsValidFromDateTime"))
    if revoked_at is None or revoked_at < term:
        uid = entra.get("id")
        plan(f"entra revoke sessions {email}",
             lambda uid=uid: call("POST", f"{ENTRA}/users/{uid}/revokeSignInSessions", body={}),
             lambda uid=uid, term=term: (ts(get(f"{ENTRA}/users/{uid}").get(
                 "signInSessionsValidFromDateTime")) or datetime.min) >= term)

    uid = entra.get("id")
    for grp in rows(get(f"{ENTRA}/users/{uid}/memberOf")):
        gid = grp.get("id")
        if not gid:
            continue
        def gone(gid=gid, uid=uid):
            return not any(m.get("id") == uid
                           for m in rows(get(f"{ENTRA}/groups/{gid}/members")))
        plan(f"entra remove {email} from group {grp.get('displayName', gid)}",
             lambda gid=gid, uid=uid: call(
                 "DELETE", f"{ENTRA}/groups/{gid}/members/{uid}/$ref", ok=(200, 204)),
             gone)

    for key, entry in leaver_devices(emp).items():
        snipe, intune, cs_dev = entry["snipe"], entry["intune"], entry["cs"]
        serial = (snipe or {}).get("serial") or (intune or {}).get("serialNumber") or key

        if intune is not None:
            cur = employee_for_email(intune.get("userPrincipalName") or "")
            if cur is not None and not is_terminated(cur) \
                    and (ts(cur.get("hireDate")) or datetime.min) > anchor_date:
                if snipe is not None and obj_id(snipe.get("assigned_to")) is not None:
                    new_holder = snipe_user_for(
                        emp_email(cur), f"{cur.get('firstName', '')} {cur.get('lastName', '')}")
                    if new_holder is None:
                        die(f"reissued device {serial}: current user {emp_email(cur)} "
                            f"has no Snipe-IT user to check out to")
                    aid, nid = snipe.get("id"), new_holder.get("id")
                    snipe_checkin(snipe, verify=False)
                    def check(aid=aid, nid=nid):
                        row = get(f"{SNIPE}/hardware/{aid}") or {}
                        return str(obj_id(row.get("assigned_to"))) == str(nid)
                    plan(f"snipe repoint asset {aid} -> {emp_email(cur)}",
                         lambda aid=aid, nid=nid: call(
                             "POST", f"{SNIPE}/hardware/{aid}/checkout",
                             body={"checkout_to_type": "user", "assigned_user": nid}),
                         check)
                continue

        personal = intune is not None and norm(
            intune.get("managedDeviceOwnerType")) == "personal"
        last_seen = ts((cs_dev or {}).get("last_seen"))
        in_the_wild = last_seen is not None and term is not None and last_seen > term + grace

        if intune is not None and intune.get("managementState") not in (
                "wipePending", "retirePending"):
            wipe_or_retire(intune, personal)

        if cs_dev is not None:
            if in_the_wild:
                if cs_dev.get("status") != "contained":
                    cs_action(cs_dev, "contain")
            elif cs_dev.get("hidden") is not True:
                cs_action(cs_dev, "hide_host")
            gids = [g for g in (cs_dev.get("groups") or [])]
            if gids:
                did = cs_dev.get("device_id")
                def degrouped(did=did):
                    payload = call("POST", f"{CS}/devices/entities/devices/v2",
                                   body={"ids": [did]})
                    return not ((rows(payload) or [{}])[0].get("groups"))
                plan(f"falcon remove {did} from host groups",
                     lambda gids=gids, did=did: call(
                         "POST", f"{CS}/devices/entities/host-group-actions/v1?action_name=remove-hosts",
                         body={"ids": gids,
                               "action_parameters": [
                                   {"name": "filter", "value": f"(device_id:['{did}'])"}]}),
                     degrouped)

        if snipe is not None and not personal:
            assigned = obj_id(snipe.get("assigned_to"))
            if in_the_wild:
                if assigned is not None:
                    snipe_checkin(snipe, status_id=lost_label.get("id"))
                elif asset_status_id(snipe) != str(lost_label.get("id")):
                    aid = snipe.get("id")
                    plan(f"snipe mark asset {aid} lost",
                         lambda aid=aid: call("PATCH", f"{SNIPE}/hardware/{aid}",
                                              body={"status_id": int(lost_label.get("id"))}),
                         lambda aid=aid: asset_status_id(
                             get(f"{SNIPE}/hardware/{aid}") or {}) == str(lost_label.get("id")))
            elif assigned is not None:
                snipe_checkin(snipe)

if not actions:
    die("derived zero remediation actions — either the seed is pristine-clean or discovery failed")

print(f"== executing {len(actions)} writes ==")
for desc, thunk in actions:
    print(f"  -> {desc}")
    thunk()

print("== readback verification ==")
for desc, check in readbacks:
    try:
        if not check():
            note_failure(desc)
    except Exception as exc:
        note_failure(f"{desc} ({exc})")

transitions = rows(get(f"{JSM}/request/{TICKET_KEY}/transition"))
closing = next(
    (t for t in transitions
     if norm(((t.get("to") or {}).get("statusCategory"))) == "complete"
     or re.search(r"resolve|close|done", norm(t.get("name")))), None)
if closing is None:
    die("no COMPLETE-category transition available on the ticket")
call("POST", f"{JSM}/request/{TICKET_KEY}/transition", body={"id": closing.get("id")})
final = get(f"{JSM}/request/{TICKET_KEY}")
if norm(((final or {}).get("currentStatus") or {}).get("statusCategory")) != "complete":
    note_failure("ticket did not land in a COMPLETE status")

if failures:
    print(f"\n{len(failures)} readback mismatch(es)", file=sys.stderr)
    sys.exit(1)
print(f"\nOK: {len(actions)} writes verified, ticket {TICKET_KEY} closed")
