#!/usr/bin/env python3
import collections
import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

SN = "http://servicenow.local.mock:8080/api/now/table"
WINDOW_START = "2026-07-25 00:00:00"
WINDOW_END = "2026-07-27 06:00:00"
NEEDS_TYPES = {"reltype-depends-on", "reltype-runs-on", "reltype-hosted-on", "reltype-consumes"}

def _req(method, url, body=None):
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        raise RuntimeError("%s %s -> %s %s" % (method, url, e.code, e.read().decode()[:300]))
    return json.loads(raw) if raw else None

def _rows(obj):
    if isinstance(obj, dict) and isinstance(obj.get("result"), list):
        return obj["result"]
    if isinstance(obj, dict) and isinstance(obj.get("result"), dict):
        return [obj["result"]]
    return obj if isinstance(obj, list) else []

def get_list(table, query=None, fields=None, limit=2000):
    q = []
    if query:
        q.append("sysparm_query=" + urllib.parse.quote(query))
    if fields:
        q.append("sysparm_fields=" + urllib.parse.quote(fields))
    q.append("sysparm_limit=%d" % limit)
    return _rows(_req("GET", "%s/%s?%s" % (SN, table, "&".join(q))))

def patch(table, sys_id, body):
    return _req("PATCH", "%s/%s/%s" % (SN, table, sys_id), body)

def parse(dt):
    return datetime.datetime.strptime(str(dt), "%Y-%m-%d %H:%M:%S")

def overlap(a, b):
    return parse(a["start_date"]) < parse(b["end_date"]) and parse(b["start_date"]) < parse(a["end_date"])

def reachability(rels):
    adj = collections.defaultdict(set)
    for r in rels:
        if str(r.get("type")) in NEEDS_TYPES:
            adj[str(r["parent"])].add(str(r["child"]))
    nodes = set(adj) | {c for s in adj.values() for c in s}
    reach = {}
    for node in nodes:
        seen, stack = set(), list(adj[node])
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            stack.extend(adj[n])
        reach[node] = seen
    return reach

def related(ci_a, ci_b, reach, nodes):
    if ci_a == ci_b:
        return True
    if ci_b in reach.get(ci_a, ()) or ci_a in reach.get(ci_b, ()):
        return True
    for s in nodes:
        r = reach.get(s, ())
        if ci_a in r and ci_b in r:
            return True
    return False

def hold(change, reason):
    patch("change_request", change["sys_id"], {"on_hold": "true", "on_hold_reason": reason, "state": "4"})

def main():
    changes = get_list("change_request",
                       query="state=-2^start_date>=%s^start_date<=%s" % (WINDOW_START, WINDOW_END))
    changes = [c for c in changes if c.get("start_date") and c.get("end_date")]
    by_id = {c["sys_id"]: c for c in changes}

    rels = get_list("cmdb_rel_ci", fields="parent,child,type", limit=1000)
    reach = reachability(rels)
    nodes = set(reach.keys())

    held = set()
    collisions = []
    for i in range(len(changes)):
        for j in range(i + 1, len(changes)):
            a, b = changes[i], changes[j]
            if overlap(a, b) and related(str(a["cmdb_ci"]), str(b["cmdb_ci"]), reach, nodes):
                collisions.append((a, b))
    for a, b in collisions:
        victim = b if parse(b["start_date"]) >= parse(a["start_date"]) else a
        if victim["sys_id"] not in held:
            hold(victim, "Change collision: conflicts with %s in an overlapping window" %
                 (a["number"] if victim is b else b["number"]))
            held.add(victim["sys_id"])

    freeze = get_list("u_change_freeze", query="active=true")
    frozen_ranges = [(parse(f["u_start"]), parse(f["u_end"])) for f in freeze]

    def in_freeze(c):
        s = parse(c["start_date"])
        return any(fs <= s < fe for fs, fe in frozen_ranges)

    approvals = get_list("sysapproval_approver", fields="sysapproval,state,assignment_group", limit=2000)
    approved_of = collections.defaultdict(set)
    for ap in approvals:
        approved_of[str(ap["sysapproval"])].add(str(ap.get("state")).lower())

    def approved(c):
        return "approved" in approved_of.get(c["sys_id"], set())

    for c in changes:
        if c["sys_id"] in held:
            continue
        is_emergency = str(c.get("type")).lower() == "emergency"
        if in_freeze(c) and not is_emergency:
            hold(c, "Scheduled inside the active change freeze")
            held.add(c["sys_id"])
            continue
        if not approved(c) and not is_emergency:
            hold(c, "Not authorized to run: no approved CAB sign-off")
            held.add(c["sys_id"])

    mismatches = 0
    for sys_id in held:
        c = get_list("change_request", query="sys_id=" + sys_id,
                     fields="number,on_hold,state")[0]
        ok = str(c.get("on_hold")).lower() == "true" and str(c.get("state")) == "4"
        if not ok:
            mismatches += 1
            print("MISMATCH", c.get("number"), c.get("on_hold"), c.get("state"))
    print("held=%d  collisions=%d  mismatches=%d" % (len(held), len(collisions), mismatches))
    if mismatches:
        sys.exit(1)

main()
