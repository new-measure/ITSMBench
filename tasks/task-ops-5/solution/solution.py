#!/usr/bin/env python3
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict

SN = "http://servicenow.local.mock:8080/api/now/table"
SEVERE_THRESHOLD = 4
MISMATCHES = []

def call(method, url, body=None):
    data, hdrs = None, {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode()
        return json.loads(raw) if raw and raw.strip()[:1] in "{[" else raw
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_body": e.read().decode()[:200]}

def rows(obj):
    if isinstance(obj, dict) and isinstance(obj.get("result"), list):
        return obj["result"]
    if isinstance(obj, dict) and isinstance(obj.get("result"), dict):
        return [obj["result"]]
    return obj if isinstance(obj, list) else []

def q(table, encoded=None, fields=None, limit=5000):
    url = "%s/%s?sysparm_limit=%d" % (SN, table, limit)
    if encoded:
        url += "&sysparm_query=" + urllib.parse.quote(encoded)
    if fields:
        url += "&sysparm_fields=" + urllib.parse.quote(fields)
    return rows(call("GET", url))

def check(desc, ok):
    print(("  OK   " if ok else "  FAIL ") + desc)
    if not ok:
        MISMATCHES.append(desc)

cis = q("cmdb_ci", limit=5000)
crit = {c["sys_id"]: str(c.get("business_criticality", "")) for c in cis}
ci_name = {c["sys_id"]: c.get("name") for c in cis}
CRIT1 = {sid for sid, v in crit.items() if v.startswith("1")}
edges = q("cmdb_rel_ci", limit=10000)
dependents = defaultdict(set)
for e in edges:
    if e.get("parent") and e.get("child"):
        dependents[e["child"]].add(e["parent"])
print("CMDB: %d CIs (%d most-critical) | %d dependency edges" % (len(cis), len(CRIT1), len(edges)))

def blast_radius(ci_sid):
    closure, frontier = set(), {ci_sid}
    while frontier:
        nxt = set()
        for node in frontier:
            for p in dependents.get(node, ()):
                if p not in closure and p != ci_sid:
                    closure.add(p); nxt.add(p)
        frontier = nxt
    return len(closure & CRIT1)

BLAST = {c["sys_id"]: blast_radius(c["sys_id"]) for c in cis}

breached_tasks = {t.get("task") for t in q("task_sla", limit=5000)
                  if str(t.get("has_breached")).lower() == "true" and str(t.get("stage")) != "paused"}
print("genuine SLA breaches (non-paused): %d" % len(breached_tasks))

open_incs = q("incident", "stateIN1,2,3", limit=5000)

def is_p1(r):
    return str(r.get("priority")) == "1" or (str(r.get("impact")) == "1" and str(r.get("urgency")) == "1")

def is_major(r):
    return str(r.get("major_incident_state", "")).lower() in ("proposed", "accepted")

severe, sla_esc = [], []
for r in open_incs:
    ci = r.get("cmdb_ci")
    b = BLAST.get(ci, 0)
    if ci and b >= SEVERE_THRESHOLD:
        if not (is_p1(r) and is_major(r)):
            severe.append((r, b))
    elif r["sys_id"] in breached_tasks and not is_p1(r):
        sla_esc.append(r)

print("\nSEVERE (blast-radius) incidents to escalate+declare-major: %d" % len(severe))
for r, b in sorted(severe, key=lambda x: -x[1]):
    print("  %-12s %-24s blast=%d  (stated P%s)" % (r.get("number"), ci_name.get(r.get("cmdb_ci")), b, r.get("priority")))
print("SLA-breach incidents to escalate: %d" % len(sla_esc))
for r in sla_esc:
    print("  %-12s %-24s (stated P%s)" % (r.get("number"), ci_name.get(r.get("cmdb_ci")), r.get("priority")))

for r, b in severe:
    call("PATCH", "%s/incident/%s" % (SN, r["sys_id"]), body={
        "priority": "1", "impact": "1", "urgency": "1",
        "major_incident_state": "Accepted",
        "u_escalation_reason": "Shared component with %d most-critical downstream dependents; "
                               "widespread customer impact." % b})

for r in sla_esc:
    call("PATCH", "%s/incident/%s" % (SN, r["sys_id"]), body={
        "priority": "1", "impact": "1", "urgency": "1",
        "u_escalation_reason": "Most-critical customer-facing service with a breached resolution SLA."})

print("\n--- readback ---")
for r, b in severe:
    cur = q("incident", "sys_id=" + r["sys_id"])[0]
    check("severe %s (%s) raised to P1" % (cur.get("number"), ci_name.get(cur.get("cmdb_ci"))), is_p1(cur))
    check("severe %s (%s) declared major" % (cur.get("number"), ci_name.get(cur.get("cmdb_ci"))), is_major(cur))
for r in sla_esc:
    cur = q("incident", "sys_id=" + r["sys_id"])[0]
    check("sla-breach %s raised to P1" % cur.get("number"), is_p1(cur))

escalated_ids = {r["sys_id"] for r, _ in severe} | {r["sys_id"] for r in sla_esc}
for c in cis:
    if BLAST[c["sys_id"]] == 0 and crit[c["sys_id"]].startswith("1"):
        for r in [x for x in open_incs if x.get("cmdb_ci") == c["sys_id"]]:
            if r["sys_id"] in breached_tasks or str(r.get("priority")) == "1":
                continue
            cur = q("incident", "sys_id=" + r["sys_id"])[0]
            check("[ctrl] crit1-no-dependents %s left un-escalated" % cur.get("number"),
                  not is_major(cur) and str(cur.get("priority")) != "1")

print("\nsevere=%d sla_esc=%d | %d mismatch(es)" % (len(severe), len(sla_esc), len(MISMATCHES)))
for m in MISMATCHES:
    print("  FAILED:", m)
sys.exit(1 if (MISMATCHES or len(severe) != 8 or len(sla_esc) != 2) else 0)
