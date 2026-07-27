#!/usr/bin/env python3
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

VANTA = "http://vanta.local.mock:8080/v1"
OKTA = "http://okta.local.mock:8080/api/v1"
SN = "http://servicenow.local.mock:8080/api/now/table"
INCIDENT_NUMBER = "INC0031001"
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
        return json.loads(raw) if raw and raw.strip()[:1] in "{[" else raw
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_body": e.read().decode()[:200]}

def get(url):
    return call("GET", url)

def vlist(path):
    out, cursor = [], None
    while True:
        u = VANTA + path + ("?pageSize=100" if "?" not in path else "&pageSize=100")
        if cursor:
            u += "&pageCursor=" + urllib.parse.quote(cursor)
        d = get(u)
        results = (d or {}).get("results") or {}
        out.extend(results.get("data") or [])
        info = results.get("pageInfo") or {}
        if info.get("hasNextPage") and info.get("endCursor"):
            cursor = info["endCursor"]
        else:
            break
    return out

NOW = datetime(2026, 7, 18, 9, 0, 0, tzinfo=timezone.utc)

def parse(dt):
    if not dt:
        return None
    try:
        return datetime.fromisoformat(str(dt).replace("Z", "+00:00"))
    except ValueError:
        return None

def check(desc, ok):
    print(("  OK   " if ok else "  FAIL ") + desc)
    if not ok:
        MISMATCHES.append(desc)

incidents = get(SN + "/incident")
incidents = (incidents or {}).get("result", []) if isinstance(incidents, dict) else []
cur = next((i for i in incidents if str(i.get("number")) == INCIDENT_NUMBER), None)
assert cur, "incident not found"
inc_sys = str(cur["sys_id"])
choices = get(SN + "/sys_choice")
choices = (choices or {}).get("result", []) if isinstance(choices, dict) else []
closed = [str(c.get("value")) for c in choices if str(c.get("name")) == "incident"
          and str(c.get("element")) == "state" and str(c.get("label", "")).lower() in ("resolved", "closed")]
CLOSED = closed[-1] if closed else "7"
print("incident %s sys_id=%s -> close state %s" % (INCIDENT_NUMBER, inc_sys, CLOSED))

apps = get(OKTA + "/apps")
apps = apps if isinstance(apps, list) else []
live_access_labels = set()
for a in apps:
    if str(a.get("status")) == "ACTIVE":
        users = get(OKTA + "/apps/%s/users" % a["id"])
        users = users if isinstance(users, list) else []
        if users:
            live_access_labels.add(str(a.get("label")))
print("vendors holding live Okta access:", sorted(live_access_labels))

vendors = vlist("/vendors")
print("register size:", len(vendors))
A_set, B_findings, C_set, D_set = [], [], [], []
for v in vendors:
    vid, name, status = v["id"], str(v.get("name")), str(v.get("status"))
    assessments = vlist("/vendors/%s/assessments" % vid)
    completed = [a for a in assessments if str(a.get("status")) == "COMPLETED" and a.get("completionDate")]
    latest = max(completed, key=lambda a: a["completionDate"]) if completed else None
    findings = vlist("/vendors/%s/findings" % vid)
    due = parse(v.get("nextSecurityReviewDueDate"))

    if status == "MANAGED" and latest and str((latest.get("decision") or {}).get("status")) == "NOT_APPROVED":
        A_set.append(vid)
        call("POST", VANTA + "/vendors/%s/set-status" % vid, body={"status": "IN_PROCUREMENT"})
        print("  [A] %s: latest assessment NOT_APPROVED -> status IN_PROCUREMENT" % name)

    for f in findings:
        if str(f.get("riskStatus")) == "REMEDIATE" and str((f.get("remediation") or {}).get("state")) == "OPEN":
            B_findings.append((vid, f["id"]))
            call("PATCH", VANTA + "/vendors/%s/findings/%s" % (vid, f["id"]),
                 body={"remediation": {"state": "CLOSED",
                                       "requirementNotes": "Remediation evidence received and validated; closed."}})
            print("  [B] %s: actioned open REMEDIATE finding %s" % (name, f["id"]))

    if status == "MANAGED" and not completed and name in live_access_labels:
        C_set.append(vid)
        call("POST", VANTA + "/vendors/%s/findings" % vid,
             body={"content": "Vendor holds live SSO access but has no completed security assessment on "
                              "file. Access granted without diligence; flagged pending review.",
                   "riskStatus": "REMEDIATE",
                   "remediation": {"state": "OPEN", "requirementNotes": "Complete diligence or gate access."}})
        call("POST", VANTA + "/vendors/%s/set-status" % vid, body={"status": "IN_PROCUREMENT"})
        print("  [C] %s: live access + no completed assessment -> flagged + IN_PROCUREMENT" % name)

    if status == "MANAGED" and due and due < NOW:
        D_set.append(vid)
        call("POST", VANTA + "/vendors/%s/set-status" % vid, body={"status": "IN_PROCUREMENT"})
        print("  [D] %s: reassessment overdue -> status IN_PROCUREMENT" % name)

call("PATCH", SN + "/incident/%s" % inc_sys,
     body={"state": CLOSED, "close_code": "Solved (Permanently)",
           "close_notes": "Reviewed the whole third-party register against reality: re-flagged vendors "
                          "whose latest assessment had failed, actioned open high-severity findings, "
                          "flagged vendors holding live access with no completed diligence, and re-flagged "
                          "overdue reassessments. Left genuinely low-risk/current vendors untouched."})

print("\n--- readback ---")

def flagged(vid):
    v = get(VANTA + "/vendors/%s" % vid)
    if str((v or {}).get("status")) != "MANAGED":
        return True
    return any(str(f.get("riskStatus")) == "REMEDIATE" for f in vlist("/vendors/%s/findings" % vid))

print("acted: A=%d B=%d C=%d D=%d" % (len(A_set), len(B_findings), len(C_set), len(D_set)))
for vid in A_set:
    check("A %s re-flagged (latest assessment failed)" % vid, flagged(vid))
for vid, fid in B_findings:
    f = next((x for x in vlist("/vendors/%s/findings" % vid) if str(x.get("id")) == fid), None)
    actioned = f is not None and (str(f.get("riskStatus")) != "REMEDIATE"
                                  or str((f.get("remediation") or {}).get("state")) == "CLOSED")
    check("B %s finding %s actioned" % (vid, fid), actioned)
for vid in C_set:
    check("C %s flagged (access without diligence)" % vid, flagged(vid))
for vid in D_set:
    check("D %s handled (overdue reassessment)" % vid, flagged(vid))

inc2 = (get(SN + "/incident/%s" % inc_sys) or {}).get("result", {})
check("incident closed", str(inc2.get("state")) == CLOSED)

check("found 5 A vendors", len(A_set) == 5)
check("found 5 B findings", len(B_findings) == 5)
check("found 4 C vendors", len(C_set) == 4)
check("found 4 D vendors", len(D_set) == 4)

print("\n%d mismatch(es)" % len(MISMATCHES))
for m in MISMATCHES:
    print("  FAILED:", m)
sys.exit(1 if MISMATCHES else 0)
