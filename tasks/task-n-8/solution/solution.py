#!/usr/bin/env python3
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

INTUNE = "http://microsoft-intune.local.mock:8080/v1.0"
DEFENDER = "http://microsoft-defender.local.mock:8080/v1.0"
ENTRA = "http://entra-id.local.mock:8080/v1.0"
SN = "http://servicenow.local.mock:8080/api/now/table"
INCIDENT_NUMBER = "INC0044201"
MISMATCHES = []

def call(method, url, body=None, form=False, json_body=False):
    data, headers = None, {"Accept": "application/json"}
    if form:
        data = urllib.parse.urlencode(body or {}).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
        return json.loads(raw) if raw and raw.strip()[:1] in "{[" else raw
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_body": e.read().decode()[:300]}

def get(url):
    return call("GET", url)

def value(obj):
    if isinstance(obj, dict):
        return obj.get("value") or obj.get("result") or []
    return obj if isinstance(obj, list) else []

def check(desc, ok):
    print(("  OK   " if ok else "  FAIL ") + desc)
    if not ok:
        MISMATCHES.append(desc)

incs = value(get(SN + "/incident"))
cur = next((i for i in incs if str(i.get("number")) == INCIDENT_NUMBER), None)
assert cur, "incident not found"
inc_sys = str(cur["sys_id"])
desc = str(cur.get("description", ""))
suspected = re.search(r"CHG\d+", desc)
print("incident %s sys_id=%s | ticket blames: %s / Finance ring (NOT trusted)"
      % (INCIDENT_NUMBER, inc_sys, suspected.group(0) if suspected else "?"))
choices = value(get(SN + "/sys_choice"))
closed = [str(c.get("value")) for c in choices if str(c.get("name")) == "incident"
          and str(c.get("element")) == "state" and re.search(r"resolv|clos", str(c.get("label", "")), re.I)]
CLOSED = closed[-1] if closed else "7"

policies = value(get(INTUNE + "/deviceManagement/deviceCompliancePolicies"))
enforced_groups = set()
for p in policies:
    asgs = value(get(INTUNE + "/deviceManagement/deviceCompliancePolicies/" + str(p.get("id")) + "/assignments"))
    for a in asgs:
        t = a.get("target") or {}
        if str(t.get("@odata.type", "")).endswith("groupAssignmentTarget") and t.get("groupId"):
            enforced_groups.add(str(t["groupId"]))
assert len(enforced_groups) == 1, "expected exactly one enforced group, got %s" % enforced_groups
ENFORCED = next(iter(enforced_groups))

groups = value(get(ENTRA + "/groups"))
exempt_owner_ids = set()
for g in groups:
    text = (str(g.get("displayName", "")) + " " + str(g.get("description", ""))).lower()
    if str(g.get("id")) != ENFORCED and ("exempt" in text or "exclud" in text):
        for m in value(get(ENTRA + "/groups/" + str(g.get("id")) + "/members")):
            if isinstance(m, dict) and m.get("id"):
                exempt_owner_ids.add(str(m["id"]))
enforced_member_ids = {str(m.get("id")) for m in value(get(ENTRA + "/groups/" + ENFORCED + "/members")) if isinstance(m, dict)}
print("enforced group=%s (%d members) | exempt owners=%d" % (ENFORCED, len(enforced_member_ids), len(exempt_owner_ids)))

devices = value(get(INTUNE + "/deviceManagement/managedDevices"))
fix_devices = [d for d in devices
               if str(d.get("complianceState")) == "noncompliant"
               and str(d.get("userId")) not in enforced_member_ids
               and str(d.get("userId")) not in exempt_owner_ids]
print("managed devices=%d | fix (drifted non-compliant)=%s"
      % (len(devices), [d["deviceName"] for d in fix_devices]))
fix_owner_ids = [str(d.get("userId")) for d in fix_devices]

for uid in fix_owner_ids:
    r = call("POST", ENTRA + "/groups/" + ENFORCED + "/members/$ref",
             body={"@odata.id": "https://graph.microsoft.com/v1.0/directoryObjects/" + uid})
    print("  add owner %s ->" % uid, "ok" if not (isinstance(r, dict) and r.get("_error")) else r)

alerts = value(get(DEFENDER + "/security/alerts_v2"))
genuine = [a for a in alerts if str(a.get("classification")) != "falsePositive" and str(a.get("status")) != "resolved"]
print("defender alerts=%d | genuine to resolve=%d | left (false-positive/resolved)=%d"
      % (len(alerts), len(genuine), len(alerts) - len(genuine)))
for a in genuine:
    r = call("PATCH", DEFENDER + "/security/alerts_v2/" + str(a["id"]),
             body={"status": "resolved", "classification": "truePositive", "determination": "other"})
    print("  resolve alert %s ->" % a["id"], "ok" if not (isinstance(r, dict) and r.get("_error")) else r)

for d in fix_devices:
    r = call("POST", INTUNE + "/deviceManagement/managedDevices/" + str(d["id"]) + "/syncDevice")
    print("  sync %s ->" % d["deviceName"], "ok" if not (isinstance(r, dict) and r.get("_error")) else r)

call("PATCH", SN + "/incident/" + inc_sys, body={
    "state": CLOSED, "close_code": "Solved (Permanently)",
    "close_notes": "Reconstructed the true non-compliant fleet (spanning Sales, Finance and "
                   "Engineering, not just the suspected Finance ring; the baseline policy push was "
                   "not the cause). Re-added drifted device owners to the CA-required compliant-device "
                   "group, resolved the genuine Defender device-risk alerts, and forced an Intune sync "
                   "on each so they re-evaluate compliant before enforcement. The approved-exemption "
                   "device, the known false-positive, and the already-compliant devices were left "
                   "untouched."})

print("\n--- readback ---")
enforced_after = {str(m.get("id")) for m in value(get(ENTRA + "/groups/" + ENFORCED + "/members")) if isinstance(m, dict)}
for uid in fix_owner_ids:
    check("owner %s in enforced group" % uid, uid in enforced_after)
alerts_after = {str(a["id"]): a for a in value(get(DEFENDER + "/security/alerts_v2"))}
for a in genuine:
    check("alert %s resolved" % a["id"], str(alerts_after.get(str(a["id"]), {}).get("status")) == "resolved")
devs_after = {str(d["id"]): d for d in value(get(INTUNE + "/deviceManagement/managedDevices"))}
for d in fix_devices:
    results = devs_after.get(str(d["id"]), {}).get("deviceActionResults") or []
    check("device %s synced" % d["deviceName"], any(str(r.get("actionName")) == "syncDevice" for r in results))
inc_after = (get(SN + "/incident/" + inc_sys) or {}).get("result", {})
check("incident closed", str(inc_after.get("state")) == CLOSED)

print("\n%d mismatch(es)" % len(MISMATCHES))
for m in MISMATCHES:
    print("  FAILED:", m)
sys.exit(1 if MISMATCHES else 0)
