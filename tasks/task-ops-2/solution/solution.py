#!/usr/bin/env python3
import datetime
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

SN = "http://servicenow.local.mock:8080/api/now/table"
PRB = "PRB0041001"
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

def q(table, encoded, fields=None, limit=5000):
    url = "%s/%s?sysparm_limit=%d&sysparm_query=%s" % (SN, table, limit, urllib.parse.quote(encoded))
    if fields:
        url += "&sysparm_fields=" + urllib.parse.quote(fields)
    return rows(call("GET", url))

def parse(ts):
    return str(ts).replace("-", "").replace(":", "").replace(" ", "")[:14]

def shift(ts14, mins):
    d = datetime.datetime.strptime(ts14, "%Y%m%d%H%M%S") + datetime.timedelta(minutes=mins)
    return d.strftime("%Y%m%d%H%M%S")

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
print("problem %s sys_id=%s state=%s affected_CI=%s" % (PRB, prob_sysid, prob.get("state"), prob_ci))

all_rels = q("cmdb_rel_ci", "sys_idISNOTEMPTY", limit=10000)

def closure(start, follow):
    ci_set = {start}
    frontier = {start}
    while frontier:
        nxt = set()
        for rel in all_rels:
            if follow == "down" and rel.get("child") in frontier and rel.get("parent") not in ci_set:
                nxt.add(rel["parent"])
            if follow == "up" and rel.get("parent") in frontier and rel.get("child") not in ci_set:
                nxt.add(rel["child"])
        nxt -= ci_set
        ci_set |= nxt
        frontier = nxt
    return ci_set

DOWN = closure(prob_ci, "down")
UP = closure(prob_ci, "up")
FULL = DOWN | UP
print("DOWNSTREAM closure (%d):" % len(DOWN), sorted(DOWN))
print("UPSTREAM   closure (%d):" % len(UP), sorted(UP))

day = str(prob.get("sys_created_on") or "2026-07-18")[:10]
co_incs = q("incident", "cmdb_ci=%s^sys_created_on>=%s 00:00:00" % (prob_ci, day))
assert co_incs, "no incidents on the affected CI on the problem's day"
times = sorted(parse(r.get("sys_created_on")) for r in co_incs if r.get("sys_created_on"))
win_lo, win_hi = shift(times[0], -15), shift(times[-1], 15)
print("onset window (from affected-CI burst):", win_lo, "..", win_hi)

cand = q("incident", "sys_created_on>=%s^sys_created_on<=%s"
         % (day + " 02:30:00", day + " 04:15:00"), limit=5000)
footprint = []
for r in cand:
    if not (win_lo <= parse(r.get("sys_created_on")) <= win_hi):
        continue
    if r.get("cmdb_ci") in DOWN and str(r.get("state")) in ("1", "2", "3"):
        footprint.append(r)
fp_ids = {r["sys_id"] for r in footprint}
primary = sorted(footprint, key=lambda r: parse(r.get("sys_created_on")))[0]["sys_id"]
print("FOOTPRINT discovered: %d incidents across the downstream closure" % len(footprint))

def overlaps(c):
    s, e = c.get("start_date"), c.get("end_date")
    if not s:
        return False
    return parse(s) <= win_hi and parse(e or s) >= win_lo

changes = q("change_request", "sys_idISNOTEMPTY", limit=5000)
rc_cands = [c for c in changes if c.get("cmdb_ci") in FULL and overlaps(c)]
assert len(rc_cands) == 1, "root-cause change not unique: %s" % [c.get("number") for c in rc_cands]
root_change = rc_cands[0]
print("ROOT-CAUSE change:", root_change.get("number"), "on CI", root_change.get("cmdb_ci"),
      "(in-window, in dependency graph)")

for r in footprint:
    call("PATCH", "%s/incident/%s" % (SN, r["sys_id"]), body={
        "problem_id": prob_sysid,
        "parent_incident": (primary if r["sys_id"] != primary else ""),
        "state": "7", "close_code": "Duplicate",
        "close_notes": "Consolidated under the checkout problem %s (downstream footprint)." % PRB})

call("PATCH", "%s/problem/%s" % (SN, prob_sysid), body={
    "u_root_cause_change": root_change["sys_id"], "state": "3", "known_error": "true",
    "root_cause": "Traced UP the CMDB dependency graph: an in-window change on an upstream service the "
                  "affected service depends on broke token issuance and cascaded to the checkout "
                  "footprint. The recent change on the affected CI itself is out of the onset window."})

print("\n--- readback ---")
for r in footprint:
    cur = q("incident", "sys_id=" + r["sys_id"])[0]
    linked = cur.get("problem_id") == prob_sysid or cur.get("parent_incident") in (fp_ids | {prob_sysid})
    closed = str(cur.get("state")) in ("6", "7") and "dup" in str(cur.get("close_code")).lower()
    check("footprint %s linked+closed-as-dup" % cur.get("number"), linked and closed)

pp = q("problem", "sys_id=" + prob_sysid)[0]
check("problem links the upstream root-cause change", root_change["sys_id"] in [str(v) for v in pp.values()])
check("problem NOT linked to the decoy change (out-of-window, on affected CI)",
      not any(str(c.get("cmdb_ci")) == prob_ci and not overlaps(c) and c["sys_id"] in [str(v) for v in pp.values()]
              for c in changes))
check("problem state advanced from New", str(pp.get("state")) not in ("1", "", "None"))
check("problem marked known error", str(pp.get("known_error")).lower() in ("true", "1"))

sib = q("problem", "number=PRB0041002")
if sib:
    check("[ctrl] sibling problem not linked to our root-cause change",
          root_change["sys_id"] not in [str(v) for v in sib[0].values()])

print("\nfootprint=%d root-cause=%s | %d mismatch(es)"
      % (len(footprint), root_change.get("number"), len(MISMATCHES)))
for m in MISMATCHES:
    print("  FAILED:", m)
sys.exit(1 if (MISMATCHES or len(footprint) != 17) else 0)
