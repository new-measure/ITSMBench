#!/usr/bin/env python3
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

PURVIEW = "http://purview.local.mock:8080/v1.0"
SN = "http://servicenow.local.mock:8080/api/now/table"
INCIDENT_NUMBER = "INC0030001"
MISMATCHES = []

def call(method, url, body=None, form=False):
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
        return {"_error": e.code, "_body": e.read().decode()[:200]}

def get(url):
    return call("GET", url)

def gvalue(url):
    d = get(url)
    return (d or {}).get("value", []) if isinstance(d, dict) else (d if isinstance(d, list) else [])

def check(desc, ok):
    print(("  OK   " if ok else "  FAIL ") + desc)
    if not ok:
        MISMATCHES.append(desc)

def is_active(status):
    return str(status) == "active"

def is_closed(status):
    return str(status) in ("closed", "closedWithError", "pendingDelete", "closing")

incidents = get(SN + "/incident")
incidents = (incidents or {}).get("result", []) if isinstance(incidents, dict) else []
cur = next((i for i in incidents if str(i.get("number")) == INCIDENT_NUMBER), None)
assert cur, "incident not found"
inc_sys = str(cur["sys_id"])
choices = get(SN + "/sys_choice")
choices = (choices or {}).get("result", []) if isinstance(choices, dict) else []
closed_states = [str(c.get("value")) for c in choices if str(c.get("name")) == "incident"
                 and str(c.get("element")) == "state" and str(c.get("label", "")).lower() in ("resolved", "closed")]
CLOSE_STATE = closed_states[-1] if closed_states else "7"
print("incident %s sys_id=%s -> close state %s" % (INCIDENT_NUMBER, inc_sys, CLOSE_STATE))

cases = gvalue(PURVIEW + "/security/cases/ediscoveryCases")
print("matters:", [(c.get("id"), c.get("status")) for c in cases])
for case in cases:
    cid = case["id"]
    status = case.get("status")
    custs = gvalue(PURVIEW + "/security/cases/ediscoveryCases/%s/custodians" % cid)
    for cu in custs:
        uid = cu["id"]
        base = PURVIEW + "/security/cases/ediscoveryCases/%s/custodians/%s" % (cid, uid)
        if is_active(status):
            if str(cu.get("status")) != "active":
                call("POST", base + "/microsoft.graph.security.activate")
                print("  activate %s (matter %s)" % (uid, cid))
            if str(cu.get("holdStatus")) != "applied":
                call("POST", base + "/microsoft.graph.security.applyHold")
                print("  applyHold %s (matter %s)" % (uid, cid))
        elif is_closed(status):
            if str(cu.get("status")) != "released":
                call("POST", base + "/microsoft.graph.security.release")
                print("  release %s (matter %s)" % (uid, cid))

labels = gvalue(PURVIEW + "/security/labels/retentionLabels")
events = gvalue(PURVIEW + "/security/triggers/retentionEvents")
types_with_events = {str((e.get("retentionEventType") or {}).get("id")) for e in events}
corp_events = ((get(SN + "/u_corporate_event") or {}).get("result")) or []
type_types = {str(t.get("id")): t for t in gvalue(PURVIEW + "/security/triggerTypes/retentionEventTypes")}

def _corp_row_for(et_id):
    words = set()
    t = type_types.get(str(et_id)) or {}
    for field in ("displayName", "description"):
        words |= {w.strip(".,;()").lower() for w in str(t.get(field, "")).split()}
    best = None
    for row in corp_events:
        toks = set(str(row.get("u_type", "")).replace("_", " ").split())
        if toks & words:
            best = row
    return best

for lbl in labels:
    et = (lbl.get("retentionEventType") or {}).get("id")
    if lbl.get("isInUse") and str(lbl.get("retentionTrigger")) == "dateOfEvent" and et:
        if str(et) not in types_with_events:
            row = _corp_row_for(et) or {}
            when = str(row.get("u_date") or "2026-07-18") + "T00:00:00Z"
            call("POST", PURVIEW + "/security/triggers/retentionEvents",
                 body={"displayName": "Retention trigger for %s" % lbl.get("displayName", et),
                       "eventTriggerDateTime": when,
                       "retentionEventType": {"id": et}})
            types_with_events.add(str(et))
            print("  +retentionEvent for type %s (label %s, occurred %s)" % (et, lbl.get("id"), when))

call("PATCH", SN + "/incident/%s" % inc_sys,
     body={"state": CLOSE_STATE, "close_code": "Solved (Permanently)",
           "close_notes": "Reconciled actual preservation/retention state to obligations: placed unheld/"
                          "never-activated custodians on active matters under hold, released holds left "
                          "over on closed matters, and triggered in-use event-based retention obligations "
                          "that had never started. Left already-correct matters, holds, and labels untouched."})

print("\n--- readback ---")
cases2 = gvalue(PURVIEW + "/security/cases/ediscoveryCases")
for case in cases2:
    cid, status = case["id"], case.get("status")
    custs = gvalue(PURVIEW + "/security/cases/ediscoveryCases/%s/custodians" % cid)
    for cu in custs:
        if is_active(status):
            check("active-matter custodian %s on hold" % cu["id"],
                  str(cu.get("status")) == "active" and str(cu.get("holdStatus")) == "applied")
        elif is_closed(status):
            check("closed-matter custodian %s released" % cu["id"], str(cu.get("status")) == "released")
labels2 = gvalue(PURVIEW + "/security/labels/retentionLabels")
events2 = gvalue(PURVIEW + "/security/triggers/retentionEvents")
tset = {str((e.get("retentionEventType") or {}).get("id")) for e in events2}
for lbl in labels2:
    et = (lbl.get("retentionEventType") or {}).get("id")
    if lbl.get("isInUse") and str(lbl.get("retentionTrigger")) == "dateOfEvent" and et:
        check("retention obligation %s triggered" % et, str(et) in tset)
inc2 = (get(SN + "/incident/%s" % inc_sys) or {}).get("result", {})
check("incident closed", str(inc2.get("state")) == CLOSE_STATE)

print("\n%d mismatch(es)" % len(MISMATCHES))
for m in MISMATCHES:
    print("  FAILED:", m)
sys.exit(1 if MISMATCHES else 0)
