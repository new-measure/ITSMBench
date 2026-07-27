#!/usr/bin/env python3
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

SN = "http://servicenow.local.mock:8080/api/now/table"
REQ = "REQ0098001"
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
    if not ok:
        MISMATCHES.append(desc)

reqs = q("sc_request", "number=" + REQ)
assert reqs, "review %s not found" % REQ
review_sid = reqs[0]["sys_id"]
queue = [r for r in q("sc_req_item") if str(r.get("request")) == review_sid and str(r.get("state")) == "1"]
print("review %s sys_id=%s | pending queue: %d requests" % (REQ, review_sid, len(queue)))

users = {u["user_name"]: u for u in q("sys_user")}
grmember = q("sys_user_grmember")
group_members = {}
for m in grmember:
    group_members.setdefault(str(m.get("u_group") or m.get("group")), set()).add(str(m.get("u_user") or m.get("user")))
catalog = {e["u_key"]: e for e in q("u_entitlement")}
existing = {}
for r in q("u_user_entitlement"):
    existing.setdefault(str(r.get("u_user")), set()).add(str(r.get("u_entitlement")))
group_confer = {str(g.get("u_group")): str(g.get("u_entitlement")) for g in q("u_group_entitlement")}
sod = set()
for r in q("u_sod_rule"):
    sod.add(frozenset((str(r.get("u_entitlement_a")), str(r.get("u_entitlement_b")))))
exceptions = {(str(r.get("u_user")), str(r.get("u_entitlement"))) for r in q("u_access_exception")
              if str(r.get("u_state")) == "approved"}
approvals = {}
for a in q("sysapproval_approver"):
    approvals.setdefault(str(a.get("sysapproval") or a.get("document_id")), []).append(a)
print("directory=%d groups=%d catalogue=%d existing-holders=%d sod-pairs=%d exceptions=%d approvals=%d"
      % (len(users), len(group_members), len(catalog), len(existing), len(sod), len(exceptions), len(approvals)))

def authorized_approvers(user, ent):
    s = set()
    mgr = str(users.get(user, {}).get("manager") or "")
    if mgr:
        s.add(mgr)
    s |= group_members.get(str(catalog[ent]["u_owner_group"]), set())
    return s

def eligible(user, ent):
    roles = str(catalog[ent]["u_eligible_roles"])
    if roles == "*":
        return True
    return str(users.get(user, {}).get("title")) in [t.strip() for t in roles.split(",")]

def effective_existing(user):
    ents = set(existing.get(user, set()))
    for gsid, members in group_members.items():
        if user in members and gsid in group_confer:
            ents.add(group_confer[gsid])
    return ents

def violation_reasons(r):
    user, ent = str(r.get("requested_for")), str(r.get("u_requested_entitlement"))
    reasons = []
    if ent not in catalog:
        return ["unknown_entitlement"]
    apps = approvals.get(str(r.get("sys_id")), [])
    approved = [a for a in apps if str(a.get("state")) == "approved"]
    if not approved:
        reasons.append("missing_approval")
    else:
        for a in approved:
            if str(a.get("approver")) == user:
                reasons.append("self_approval")
            elif str(a.get("approver")) not in authorized_approvers(user, ent):
                reasons.append("unauthorized_approver")
    if not eligible(user, ent) and (user, ent) not in exceptions:
        reasons.append("over_entitlement")
    for e in effective_existing(user):
        if e != ent and frozenset((e, ent)) in sod:
            reasons.append("sod")
    return reasons

decisions = {}
nviol = nok = 0
for r in queue:
    reasons = violation_reasons(r)
    decisions[r["sys_id"]] = reasons
    if reasons:
        nviol += 1
        call("PATCH", "%s/sc_req_item/%s" % (SN, r["sys_id"]),
             body={"state": "4", "u_disposition": "rejected",
                   "close_notes": "Not fulfilled: %s." % ", ".join(sorted(set(reasons)))})
    else:
        nok += 1
        call("PATCH", "%s/sc_req_item/%s" % (SN, r["sys_id"]),
             body={"state": "3", "u_disposition": "fulfilled",
                   "close_notes": "Fulfilled: valid approval, eligible, no conflict with existing access."})
print("dispositioned: %d not-fulfilled (violations), %d fulfilled (compliant)" % (nviol, nok))

call("PATCH", "%s/sc_request/%s" % (SN, review_sid),
     body={"request_state": "closed_complete", "state": "3",
           "close_notes": "Queue worked: fulfilled the in-order requests; held back the policy violations."})

for r in queue:
    cur = q("sc_req_item", "sys_id=" + r["sys_id"])[0]
    st = str(cur.get("state"))
    should_reject = bool(decisions[r["sys_id"]])
    ok = (st == "4") if should_reject else (st == "3")
    check("%s -> %s (%s)" % (cur.get("number"), "reject" if should_reject else "fulfil", st), ok)

rev = q("sc_request", "number=" + REQ)[0]
check("review closed", str(rev.get("request_state")).startswith("closed") or str(rev.get("state")) == "3")

print("\nderived violations=%d (expect 14)  fulfilled=%d  |  %d mismatch(es)"
      % (nviol, nok, len(MISMATCHES)))
for m in MISMATCHES:
    print("  FAILED:", m)
sys.exit(1 if (MISMATCHES or nviol != 14) else 0)
