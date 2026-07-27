#!/usr/bin/env python3
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

SN = "http://servicenow.local.mock:8080/api/now/table"
PRB = "PRB0040100"
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

def q(table, encoded, fields=None, limit=1000):
    url = "%s/%s?sysparm_limit=%d&sysparm_query=%s" % (SN, table, limit, urllib.parse.quote(encoded))
    if fields:
        url += "&sysparm_fields=" + urllib.parse.quote(fields)
    return rows(call("GET", url))

def parse(ts):
    return str(ts).replace("-", "").replace(":", "").replace(" ", "")[:14]

def check(desc, ok):
    print(("  OK   " if ok else "  FAIL ") + desc)
    if not ok:
        MISMATCHES.append(desc)

prob = q("problem", "number=" + PRB)
assert prob, "problem %s not found" % PRB
prob = prob[0]
prob_sysid = prob["sys_id"]
prob_ci = prob.get("cmdb_ci")
assert prob_ci, "problem has no affected CI"
print("problem %s sys_id=%s state=%s CI=%s" % (PRB, prob_sysid, prob.get("state"), prob_ci))

all_rels = q("cmdb_rel_ci", "sys_idISNOTEMPTY", limit=5000)
CI_SET = {prob_ci}
changed = True
while changed:
    changed = False
    for rel in all_rels:
        if rel.get("child") in CI_SET and rel.get("parent") not in CI_SET:
            CI_SET.add(rel["parent"])
            changed = True
print("blast-radius CI_SET (%d, transitive):" % len(CI_SET), sorted(CI_SET))

ci_tagged = q("incident", "cmdb_ci=%s^sys_created_on>=2026-07-18 00:00:00" % prob_ci)
from collections import Counter
corr_counts = Counter(str(r.get("u_correlation_id")) for r in ci_tagged if r.get("u_correlation_id"))
assert corr_counts, "no correlation id found on the problem's CI incidents"
ALERT = corr_counts.most_common(1)[0][0]
print("dominant alert correlation id:", ALERT, dict(corr_counts))

sig_rows = q("incident", "u_correlation_id=" + ALERT)
times = sorted(parse(r.get("sys_created_on")) for r in sig_rows if r.get("sys_created_on"))
win_lo, win_hi = times[0], times[-1]
def shift(ts, mins):
    import datetime
    d = datetime.datetime.strptime(ts, "%Y%m%d%H%M%S") + datetime.timedelta(minutes=mins)
    return d.strftime("%Y%m%d%H%M%S")
win_lo, win_hi = shift(win_lo, -10), shift(win_hi, 10)
print("onset window:", win_lo, "..", win_hi)

cand = {}
for r in q("incident", "sys_created_on>=2026-07-18 02:40:00^sys_created_on<=2026-07-18 03:50:00"):
    cand[r["sys_id"]] = r
cluster = []
for r in cand.values():
    if not (win_lo <= parse(r.get("sys_created_on")) <= win_hi):
        continue
    if r.get("cmdb_ci") in CI_SET or str(r.get("u_correlation_id")) == ALERT:
        if str(r.get("state")) in ("1", "2", "3"):
            cluster.append(r)
cluster_ids = {r["sys_id"] for r in cluster}
print("CLUSTER discovered: %d children" % len(cluster))

primary = sorted(cluster, key=lambda r: parse(r.get("sys_created_on")))[0]["sys_id"]

def overlaps(c):
    s, e = c.get("start_date"), c.get("end_date")
    if not s:
        return False
    return parse(s) <= win_hi and parse(e or s) >= win_lo

rc_cands = [c for c in q("change_request", "cmdb_ci=" + prob_ci) if overlaps(c)]
assert len(rc_cands) == 1, "root-cause change not unique: %s" % [c.get("number") for c in rc_cands]
root_change = rc_cands[0]
print("root-cause change:", root_change.get("number"), root_change["sys_id"])

cis = {c["sys_id"]: c for c in q("cmdb_ci", "operational_status=1", limit=1000)}
if not cis:
    cis = {c["sys_id"]: c for c in q("cmdb_ci", "install_status=1", limit=1000)}
support = {sysid: c.get("support_group") for sysid, c in cis.items()}
open_incs = q("incident", "stateIN1,2,3", limit=2000)
misrouted = []
for r in open_incs:
    if r["sys_id"] in cluster_ids:
        continue
    sup = support.get(r.get("cmdb_ci"))
    if sup and r.get("assignment_group") and r["assignment_group"] != sup:
        misrouted.append((r, sup))
print("mis-routed found: %d" % len(misrouted))

crit_cis = {sysid for sysid, c in cis.items() if str(c.get("business_criticality")).startswith("1")}
breached = {t.get("task") for t in q("task_sla", "has_breached=true", limit=2000)}
mispri = [r for r in open_incs if r["sys_id"] not in cluster_ids and r.get("cmdb_ci") in crit_cis
          and str(r.get("priority")) != "1" and r["sys_id"] in breached]
print("mis-prioritized found: %d" % len(mispri))

for r in cluster:
    call("PATCH", "%s/incident/%s" % (SN, r["sys_id"]), body={
        "problem_id": prob_sysid,
        "parent_incident": (primary if r["sys_id"] != primary else ""),
        "state": "7", "close_code": "Duplicate",
        "close_notes": "Consolidated under the payment authorization major incident (%s)." % PRB})

call("PATCH", "%s/problem/%s" % (SN, prob_sysid), body={
    "u_root_cause_change": root_change["sys_id"], "state": "2", "known_error": "true",
    "root_cause": "Root cause traced to the in-window change on the affected service."})

for r, sup in misrouted:
    call("PATCH", "%s/incident/%s" % (SN, r["sys_id"]), body={"assignment_group": sup})

for r in mispri:
    call("PATCH", "%s/incident/%s" % (SN, r["sys_id"]),
         body={"priority": "1", "impact": "1", "urgency": "1",
               "u_escalation_reason": "Most-critical service, SLA breached."})

print("\n--- readback ---")
for r in cluster:
    cur = q("incident", "sys_id=" + r["sys_id"])[0]
    linked = cur.get("problem_id") == prob_sysid or cur.get("parent_incident") in (cluster_ids | {prob_sysid})
    closed = str(cur.get("state")) in ("6", "7") and "dup" in str(cur.get("close_code")).lower()
    check("child %s linked+closed-as-dup" % cur.get("number"), linked and closed)

pp = q("problem", "sys_id=" + prob_sysid)[0]
check("problem links root-cause change", root_change["sys_id"] in [str(v) for v in pp.values()])
check("problem state advanced", str(pp.get("state")) not in ("1", ""))

for r, sup in misrouted:
    cur = q("incident", "sys_id=" + r["sys_id"])[0]
    check("mis-routed %s -> CI support group" % cur.get("number"), cur.get("assignment_group") == sup)

for r in mispri:
    cur = q("incident", "sys_id=" + r["sys_id"])[0]
    p1 = str(cur.get("priority")) == "1" or (str(cur.get("impact")) == "1" and str(cur.get("urgency")) == "1")
    check("mis-prioritized %s -> P1" % cur.get("number"), p1)

for k, num in (("distractor", "PRB0040101"),):
    dp = q("problem", "number=" + num)
    if dp:
        check("[ctrl] distractor problem not root-cause-linked to payments change",
              root_change["sys_id"] not in [str(v) for v in dp[0].values()])

print("\ncluster=%d misrouted=%d mispri=%d  |  %d mismatch(es)" % (len(cluster), len(misrouted), len(mispri), len(MISMATCHES)))
for m in MISMATCHES:
    print("  FAILED:", m)
sys.exit(1 if (MISMATCHES or len(cluster) != 16 or len(misrouted) != 8 or len(mispri) != 1) else 0)
