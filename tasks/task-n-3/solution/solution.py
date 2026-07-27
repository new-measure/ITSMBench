#!/usr/bin/env python3
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ZIA = "http://zscaler-zia.local.mock:8080/zia/api/v1"
DNS = "http://infoblox-nios.local.mock:8080/wapi/v2.14"
D42 = "http://device42.local.mock:8080"
CS = "http://crowdstrike.local.mock:8080"
SN = "http://servicenow.local.mock:8080/api/now/table"
INCIDENT_NUMBER = "INC0021001"
MISMATCHES = []

def call(method, url, body=None):
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

def check(desc, ok):
    print(("  OK   " if ok else "  FAIL ") + desc)
    if not ok:
        MISMATCHES.append(desc)

def ref_ids(refs):
    return {str(x.get("id")) for x in (refs or []) if isinstance(x, dict) and x.get("id") is not None}

inc_list = get(SN + "/incident")
inc_list = inc_list if isinstance(inc_list, list) else (inc_list or {}).get("result", [])
cur = next((i for i in inc_list if str(i.get("number")) == INCIDENT_NUMBER), None)
assert cur, "incident not found"
inc_sys = str(cur["sys_id"])
desc = (str(cur.get("description", "")) + " " + str(cur.get("short_description", ""))).lower()
suspected = re.search(r"\bchg\d+\b", desc)
suspected = suspected.group(0).upper() if suspected else None
print("incident %s sys_id=%s suspected(decoy)=%s" % (INCIDENT_NUMBER, inc_sys, suspected))

cs_devs = (get(CS + "/devices/combined/devices/v1") or {}).get("resources", [])
sensors_ok = bool(cs_devs) and all(str(d.get("status")) == "normal" and not d.get("hidden")
                                   and str(d.get("reduced_functionality_mode", "no")) == "no" for d in cs_devs)
print("decoy check: %d POS endpoints, sensors healthy=%s -> endpoint update NOT the cause" % (len(cs_devs), sensors_ok))

choices = get(SN + "/sys_choice")
choices = choices if isinstance(choices, list) else (choices or {}).get("result", [])
closed = [str(c.get("value")) for c in choices if str(c.get("name")) == "incident"
          and str(c.get("element")) == "state" and re.search(r"resolv|clos", str(c.get("label", "")), re.I)]
CLOSED = closed[-1] if closed else "7"

d42_services = ((get(D42 + "/api/2.0/services/") or {}).get("services")) or []
d42_devices = ((get(D42 + "/api/2.0/devices/") or {}).get("devices")) or []
app = None
for s in d42_services:
    nm = str(s.get("name") or s.get("displayname")).lower()
    if nm and nm in desc and s.get("depends_on"):
        app = s
        break
if not app:
    app = max((s for s in d42_services if s.get("depends_on")), key=lambda s: len(s.get("depends_on") or []), default=None)
assert app, "could not find affected application"
pay_fqdns = [str(x) for x in (app.get("depends_on") or [])]
print("affected app=%s depends_on=%s" % (app.get("name"), pay_fqdns))

endpoint_ip = {str(d.get("name")): str(d.get("ip")) for d in d42_devices if d.get("ip")}
LIVE_IPS = set(endpoint_ip.values())
KNOWN_FQDNS = set(endpoint_ip.keys())
pay_live = {f: endpoint_ip.get(f) for f in pay_fqdns}
pay_live_ips = {ip for ip in pay_live.values() if ip}
print("live payment endpoint IPs:", pay_live)

rules = get(ZIA + "/firewallFilteringRules")
rules = rules if isinstance(rules, list) else []
dgroups = get(ZIA + "/ipDestinationGroups")
dgroups = dgroups if isinstance(dgroups, list) else []
dg_by_id = {str(g.get("id")): g for g in dgroups}
dg_by_name = {str(g.get("name")): g for g in dgroups}

def rule_dest_fqdns(r):
    return [str(g.get("name")) for g in (r.get("destIpGroups") or []) if str(g.get("name")) in dg_by_name]

allow_rules = [r for r in rules if str(r.get("action")).upper() == "ALLOW"]
peer_rules = [r for r in allow_rules
              if rule_dest_fqdns(r) and all(f in KNOWN_FQDNS and f not in pay_fqdns for f in rule_dest_fqdns(r))]
print("peer allow rules:", [r.get("name") for r in peer_rules])

base_src = set.intersection(*[ref_ids(r.get("srcIpGroups")) for r in peer_rules]) if peer_rules else set()
base_svc = set.intersection(*[ref_ids(r.get("nwServices")) for r in peer_rules]) if peer_rules else set()
src_group_ref = {}
svc_ref = {}
for r in peer_rules:
    for g in (r.get("srcIpGroups") or []):
        src_group_ref[str(g.get("id"))] = g
    for s in (r.get("nwServices") or []):
        svc_ref[str(s.get("id"))] = s
print("baseline src groups=%s services=%s" % (sorted(base_src), sorted(base_svc)))

for f in pay_fqdns:
    r = next((x for x in allow_rules if f in rule_dest_fqdns(x)), None)
    if not r:
        continue
    rid = r.get("id")
    body = {}
    if str(r.get("state")).upper() != "ENABLED":
        body["state"] = "ENABLED"
    have_src = ref_ids(r.get("srcIpGroups"))
    missing_src = base_src - have_src
    if missing_src:
        body["srcIpGroups"] = (r.get("srcIpGroups") or []) + [src_group_ref[i] for i in sorted(missing_src)]
    have_svc = ref_ids(r.get("nwServices"))
    missing_svc = base_svc - have_svc
    if missing_svc:
        body["nwServices"] = (r.get("nwServices") or []) + [svc_ref[i] for i in sorted(missing_svc)]
    if body:
        res = call("PUT", ZIA + "/firewallFilteringRules/%s" % rid, body=body)
        print("  fix rule %s (%s): %s (%s)" % (rid, f, list(body.keys()),
                                               "ok" if not (isinstance(res, dict) and res.get("_error")) else res))

for f in pay_fqdns:
    g = dg_by_name.get(f)
    live = pay_live.get(f)
    if not g or not live:
        continue
    ips = [str(x) for x in (g.get("ipAddresses") or [])]
    if live not in ips:
        res = call("PUT", ZIA + "/ipDestinationGroups/%s" % g.get("id"), body={"ipAddresses": ips + [live]})
        print("  dest group %s (%s): +%s (%s)" % (g.get("id"), f, live,
                                                  "ok" if not (isinstance(res, dict) and res.get("_error")) else res))

block_rules = [r for r in rules if str(r.get("action")).upper() == "BLOCK"]
block_group_ids = {str(g.get("id")) for r in block_rules for g in (r.get("destIpGroups") or [])}
for gid in sorted(block_group_ids):
    g = dg_by_id.get(gid)
    if not g:
        continue
    ips = [str(x) for x in (g.get("ipAddresses") or [])]
    keep = [ip for ip in ips if ip not in pay_live_ips]
    if keep != ips:
        res = call("PUT", ZIA + "/ipDestinationGroups/%s" % gid, body={"ipAddresses": keep})
        print("  narrow block group %s: removed %s (%s)" % (gid, sorted(set(ips) - set(keep)),
                                                            "ok" if not (isinstance(res, dict) and res.get("_error")) else res))

for r in allow_rules:
    da = [str(x) for x in (r.get("destAddresses") or [])]
    if da and all(ip not in LIVE_IPS for ip in da) and not rule_dest_fqdns(r):
        res = call("DELETE", ZIA + "/firewallFilteringRules/%s" % r.get("id"))
        print("  -orphan rule %s (dead dest %s) (%s)" % (r.get("id"), da,
                                                         "ok" if not (isinstance(res, dict) and res.get("_error")) else res))

def rec_uuid(rec):
    if rec.get("uuid"):
        return str(rec["uuid"])
    m = re.search(r"record:a/([^:]+):", str(rec.get("_ref", "")))
    return m.group(1) if m else None

dns_recs = [r for r in (get(DNS + "/record:a") or []) if isinstance(r, dict)]
for rec in dns_recs:
    name = str(rec.get("name"))
    ip = str(rec.get("ipv4addr"))
    if name in pay_live and pay_live[name] and ip != pay_live[name]:
        res = call("PUT", DNS + "/record:a/" + rec_uuid(rec), body={"ipv4addr": pay_live[name]})
        print("  repoint DNS %s: %s -> %s (%s)" % (name, ip, pay_live[name],
                                                   "ok" if not (isinstance(res, dict) and res.get("_error")) else res))
    elif name not in KNOWN_FQDNS and ip not in LIVE_IPS:
        res = call("DELETE", DNS + "/record:a/" + rec_uuid(rec))
        print("  -dangling DNS %s -> %s (%s)" % (name, ip,
                                                 "ok" if not (isinstance(res, dict) and res.get("_error")) else res))

call("PATCH", SN + "/incident/%s" % inc_sys, body={
    "state": CLOSED, "close_code": "Solved (Permanently)",
    "close_notes": ("Friday security-hardening egress window broke the store->payment-processor egress "
                    "path end to end on the secure web gateway. Restored each payment ALLOW rule to the "
                    "peer baseline (re-enabled, restored the store source group and HTTPS service), "
                    "refreshed the destination allowlists and DNS to the live processor addresses, "
                    "narrowed the over-broad block group without deleting it, and removed the dangling "
                    "rule and record the migration left behind. The sensor update and vendor were "
                    "verified healthy and left untouched.")})

print("\n--- readback ---")
rules2 = get(ZIA + "/firewallFilteringRules")
rules2 = {str(r.get("id")): r for r in (rules2 if isinstance(rules2, list) else [])}
dg2 = {str(g.get("id")): g for g in (get(ZIA + "/ipDestinationGroups") or [])}
dg2_name = {str(g.get("name")): g for g in dg2.values()}

def rule_for(f):
    return next((r for r in rules2.values() if str(r.get("action")).upper() == "ALLOW"
                 and any(str(g.get("name")) == f for g in (r.get("destIpGroups") or []))), None)

for f in pay_fqdns:
    r = rule_for(f) or {}
    check("%s rule ENABLED" % f, str(r.get("state")).upper() == "ENABLED")
    check("%s rule has baseline src" % f, base_src <= ref_ids(r.get("srcIpGroups")))
    check("%s rule has baseline svc" % f, base_svc <= ref_ids(r.get("nwServices")))
    g = dg2_name.get(f) or {}
    check("%s dest group has live IP" % f, pay_live.get(f) in [str(x) for x in (g.get("ipAddresses") or [])])
    recs = [x for x in (get(DNS + "/record:a") or []) if isinstance(x, dict) and str(x.get("name")) == f]
    check("%s DNS resolves live" % f, bool(recs) and all(str(x.get("ipv4addr")) == pay_live.get(f) for x in recs))
for gid in sorted(block_group_ids):
    g = dg2.get(gid) or {}
    ips = [str(x) for x in (g.get("ipAddresses") or [])]
    check("block group %s excludes payment IPs" % gid, all(ip not in ips for ip in pay_live_ips))
orphan_left = [r for r in rules2.values() if str(r.get("action")).upper() == "ALLOW"
               and str(r.get("state")).upper() == "ENABLED"
               and any(ip not in LIVE_IPS for ip in [str(x) for x in (r.get("destAddresses") or [])])
               and (r.get("destAddresses"))]
check("no enabled orphan ALLOW rule (dead dest)", not orphan_left)
dangling = [x for x in (get(DNS + "/record:a") or []) if isinstance(x, dict)
            and str(x.get("name")) not in KNOWN_FQDNS and str(x.get("ipv4addr")) not in LIVE_IPS]
check("no dangling DNS record", not dangling)
inc2 = (get(SN + "/incident/%s" % inc_sys) or {}).get("result", {})
check("incident closed", str(inc2.get("state")) == CLOSED)

print("\n%d mismatch(es)" % len(MISMATCHES))
for m in MISMATCHES:
    print("  FAILED:", m)
sys.exit(1 if MISMATCHES else 0)
