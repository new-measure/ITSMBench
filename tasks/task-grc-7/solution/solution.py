#!/usr/bin/env python3
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

CS = "http://crowdstrike.local.mock:8080"
SN = "http://servicenow.local.mock:8080/api/now/table"
INCIDENT_NUMBER = "INC0030001"
ACTIVE = {"open", "in_progress", "in progress", "assigned", "reopened"}
INACTIVE = {"resolved", "closed"}
IN_SCOPE_SEV = {"CRITICAL", "HIGH"}
MISMATCHES = []

def call(method, url, body=None, bodyless=False):
    data, headers = None, {"Accept": "application/json"}
    if body is not None:
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

def sn_list(table, query=""):
    url = SN + "/" + table + "?sysparm_limit=1000"
    if query:
        url += "&sysparm_query=" + urllib.parse.quote(query)
    r = get(url)
    return (r or {}).get("result", []) if isinstance(r, dict) else []

def check(desc, ok):
    print(("  OK   " if ok else "  FAIL ") + desc)
    if not ok:
        MISMATCHES.append(desc)

inc = next((i for i in sn_list("incident", "number=%s" % INCIDENT_NUMBER)), None)
assert inc, "incident not found"
inc_sys = str(inc["sys_id"])
NOW = str(inc.get("sys_created_on") or inc.get("sys_updated_on") or "")[:10]
choices = sn_list("sys_choice", "name=incident")
closed = [str(c.get("value")) for c in choices if str(c.get("element")) == "state"
          and str(c.get("label", "")).lower() in ("resolved", "closed")]
CLOSED = closed[-1] if closed else "7"
print("incident %s sys=%s now=%s close-state=%s" % (INCIDENT_NUMBER, inc_sys, NOW, CLOSED))

scan = get(CS + "/spotlight/combined/vulnerabilities/v1?limit=1000")
rows = scan.get("resources", []) if isinstance(scan, dict) else []
latest = {}
for r in rows:
    host = str(((r.get("host_info") or {}).get("hostname")))
    cve = str((r.get("cve") or {}).get("id"))
    key = (host, cve)
    if key not in latest or str(r.get("updated_timestamp")) > str(latest[key].get("updated_timestamp")):
        latest[key] = r
scanner_open = {k: v for k, v in latest.items() if str(v.get("status")) == "open"}
print("scanner rows=%d, latest-open (host,cve) pairs=%d" % (len(rows), len(scanner_open)))

cmdb = {str(c.get("name")) for c in sn_list("cmdb_ci_server")}
acc = sn_list("u_risk_acceptance")

def valid_acceptance(host, cve):
    for a in acc:
        if str(a.get("u_asset")) == host and str(a.get("u_cve")) == cve \
                and str(a.get("u_status")) == "approved" and str(a.get("u_expires")) >= NOW:
            return True
    return False

tickets = sn_list("u_vuln_item")
have_ticket = {(str(t.get("u_asset")), str(t.get("u_cve"))) for t in tickets}
group_counts = {}
for t in tickets:
    g = str(t.get("u_assignment_group") or "")
    if g and str(t.get("u_state")) in ("in_progress", "in progress"):
        group_counts[g] = group_counts.get(g, 0) + 1
GROUP = max(group_counts, key=group_counts.get) if group_counts else ""
print("cmdb assets=%d, acceptances=%d, tickets=%d, remediation-group=%s" % (len(cmdb), len(acc), len(tickets), GROUP))

def patch_ticket(sys_id, body):
    call("PATCH", SN + "/u_vuln_item/%s" % sys_id, body=body)

for t in tickets:
    host, cve, state = str(t.get("u_asset")), str(t.get("u_cve")), str(t.get("u_state"))
    sid = str(t.get("sys_id"))
    key = (host, cve)
    if valid_acceptance(host, cve):
        if state not in ("risk_accepted", "accepted"):
            patch_ticket(sid, {"u_state": "risk_accepted"})
            print("  accept  %s/%s" % (host, cve))
        continue
    if key in scanner_open:
        if state in INACTIVE:
            if str(t.get("u_close_code")) == "false_positive":
                continue
            patch_ticket(sid, {"u_state": "in_progress", "u_assignment_group": GROUP})
            print("  reopen  %s/%s" % (host, cve))
        elif state == "open" and str(t.get("u_severity")) == "CRITICAL" \
                and str(t.get("u_due") or "") and str(t.get("u_due")) < inc.get("sys_created_on", NOW) \
                and not str(t.get("u_assignment_group") or ""):
            patch_ticket(sid, {"u_state": "in_progress", "u_assignment_group": GROUP})
            print("  escalate %s/%s (breached)" % (host, cve))

from collections import defaultdict
groups = defaultdict(list)
for t in sn_list("u_vuln_item"):
    if str(t.get("u_state")) in ACTIVE:
        groups[(str(t.get("u_asset")), str(t.get("u_cve")))].append(t)
for key, dupes in groups.items():
    if len(dupes) > 1 and key in scanner_open:
        keep = sorted(dupes, key=lambda x: str(x.get("number")))[0]
        for d in dupes:
            if str(d.get("sys_id")) != str(keep.get("sys_id")):
                patch_ticket(str(d["sys_id"]), {"u_state": "closed", "u_close_code": "duplicate",
                                                "u_duplicate_of": str(keep["sys_id"])})
                print("  dedup   %s/%s close %s" % (key[0], key[1], d.get("number")))

for (host, cve), r in scanner_open.items():
    sev = str((r.get("cve") or {}).get("severity"))
    if sev in IN_SCOPE_SEV and host in cmdb and (host, cve) not in have_ticket:
        call("POST", SN + "/u_vuln_item", body={"u_asset": host, "u_cve": cve, "u_severity": sev,
             "u_state": "open", "u_finding_id": str(r.get("id")),
             "short_description": "%s on %s" % (cve, host),
             "description": "Raised from scanner reconciliation; finding active per CrowdStrike Spotlight."})
        print("  raise   %s/%s (%s)" % (host, cve, sev))

call("PATCH", SN + "/incident/%s" % inc_sys,
     body={"state": CLOSED, "close_code": "Solved (Permanently)",
           "close_notes": "Reconciled the vulnerability register to the CrowdStrike Spotlight scanner: reopened "
                          "false closures still present, raised tickets for scanner-active findings with none, "
                          "escalated breached criticals, applied approved risk acceptances, reconciled duplicates, "
                          "and left scanner-clear closures / false positives / expired-or-pending acceptances / "
                          "within-SLA / outage-stale / informational items as-is."})

print("\n--- readback ---")

def items(cve, host):
    return sn_list("u_vuln_item", "u_cve=%s^u_asset=%s" % (cve, host))

def active(cve, host):
    return [t for t in items(cve, host) if str(t.get("u_state")) in ACTIVE]

FC = [("web-prod-01", "CVE-2026-0101"), ("api-prod-01", "CVE-2026-0102"), ("db-prod-01", "CVE-2026-0103"),
      ("auth-prod-01", "CVE-2026-0104"), ("gw-prod-01", "CVE-2026-0105"), ("bastion-01", "CVE-2026-0110")]
for host, cve in FC:
    check("false-closure %s/%s reopened" % (host, cve), len(active(cve, host)) >= 1)
NT = [("worker-prod-01", "CVE-2026-0201"), ("cache-prod-01", "CVE-2026-0202"),
      ("k8s-node-01", "CVE-2026-0203"), ("log-prod-01", "CVE-2026-0204")]
for host, cve in NT:
    check("reconcile %s/%s ticket raised" % (host, cve), len(active(cve, host)) >= 1)
SLA = [("db-prod-02", "CVE-2026-0301"), ("log-prod-01", "CVE-2026-0302"), ("mail-prod-01", "CVE-2026-0303")]
for host, cve in SLA:
    ok = any(str(t.get("u_state")) in ("in_progress", "in progress") and str(t.get("u_assignment_group") or "")
             for t in items(cve, host))
    check("SLA %s/%s escalated+assigned" % (host, cve), ok)
RA = [("bastion-01", "CVE-2026-0401"), ("k8s-node-02", "CVE-2026-0402"),
      ("web-prod-02", "CVE-2026-0403"), ("gw-prod-01", "CVE-2026-0407")]
for host, cve in RA:
    check("acceptance %s/%s applied" % (host, cve),
          any(str(t.get("u_state")) in ("risk_accepted", "accepted") for t in items(cve, host)))
for host, cve in [("api-prod-01", "CVE-2026-0501"), ("db-prod-01", "CVE-2026-0502")]:
    check("duplicate %s/%s -> 1 active" % (host, cve), len(active(cve, host)) == 1)
inc2 = next((i for i in sn_list("incident", "number=%s" % INCIDENT_NUMBER)), {})
check("incident closed", str(inc2.get("state")) == CLOSED)

check("scanner-clear gw stays closed", len(active("CVE-2026-0106", "gw-prod-01")) == 0)
check("false-positive stays closed", len(active("CVE-2026-0108", "api-prod-01")) == 0)
check("expired acceptance not applied", all(str(t.get("u_state")) not in ("risk_accepted", "accepted")
      for t in items("CVE-2026-0404", "cache-prod-01")))
check("within-SLA not escalated", all(str(t.get("u_state")) == "open" for t in items("CVE-2026-0304", "db-prod-02")))
check("outage-stale stays resolved", len(active("CVE-2026-0601", "log-prod-01")) == 0)
check("low finding no ticket", len(items("CVE-2026-0603", "cache-prod-01")) == 0)
check("typo host no ticket", len(items("CVE-2026-0605", "web-prd-01")) == 0)

print("\n%d mismatch(es)" % len(MISMATCHES))
for m in MISMATCHES:
    print("  FAILED:", m)
sys.exit(1 if MISMATCHES else 0)
