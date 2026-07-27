#!/usr/bin/env python3
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

AWS = "http://aws-vpc.local.mock:8080/"
DNS = "http://infoblox-nios.local.mock:8080/wapi/v2.14"
D42 = "http://device42.local.mock:8080"
SN = "http://servicenow.local.mock:8080/api/now/table"
INCIDENT_NUMBER = "INC0088001"
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

def aws(action, **params):
    params["Action"] = action
    return call("POST", AWS, body=params, form=True)

def aws_set(action, setname):
    node = (aws(action) or {}).get(setname)
    if isinstance(node, dict) and isinstance(node.get("item"), list):
        return node["item"]
    return node if isinstance(node, list) else []

def check(desc, ok):
    print(("  OK   " if ok else "  FAIL ") + desc)
    if not ok:
        MISMATCHES.append(desc)

def rows(url):
    r = get(url)
    return r if isinstance(r, list) else []

incidents = get(SN + "/incident")
incidents = incidents if isinstance(incidents, list) else (incidents or {}).get("result", [])
cur = next((i for i in incidents if str(i.get("number")) == INCIDENT_NUMBER), None)
assert cur, "incident not found"
inc_sys = str(cur["sys_id"])
desc = str(cur.get("description", "")) + " " + str(cur.get("short_description", ""))
m = re.search(r"\b([a-z0-9][a-z0-9-]*\.(?:example|com|net|org|io))\b", desc, re.I)
domain = m.group(1).lower() if m else None
m = re.search(r"\bCHG\d+\b", desc)
suspected = m.group(0) if m else None
print("incident %s sys_id=%s domain=%s suspected(decoy)=%s" % (INCIDENT_NUMBER, inc_sys, domain, suspected))
choices = get(SN + "/sys_choice")
choices = choices if isinstance(choices, list) else (choices or {}).get("result", [])
closed = [str(c.get("value")) for c in choices if str(c.get("name")) == "incident"
          and str(c.get("element")) == "state" and re.search(r"resolv|clos", str(c.get("label", "")), re.I)]
CLOSED = closed[-1] if closed else "7"

changes = get(SN + "/change_request")
changes = changes if isinstance(changes, list) else (changes or {}).get("result", [])
decoy = next((c for c in changes if str(c.get("number")) == suspected), None)
zones = rows(DNS + "/zone_auth")
ns = [r for r in rows(DNS + "/record:ns") if str(r.get("name")) == domain]
zone_ok = any(str(z.get("fqdn")) == domain for z in zones)
print("decoy %s closed=%s | zone present=%s ns_delegation=%d record(s) -> resolver healthy, NOT the cause"
      % (suspected, decoy and decoy.get("state"), zone_ok, len(ns)))
assert zone_ok and len(ns) >= 2, "resolver plumbing should be healthy (decoy)"

enis = aws_set("DescribeNetworkInterfaces", "networkInterfaceSet")

def eni_name(e):
    for t in (e.get("TagSet") or []):
        if str(t.get("Key")) == "Name" and t.get("Value"):
            return str(t["Value"])
    return str(e.get("Description") or "")

ENI_OWNER = {str(e.get("PrivateIpAddress")): eni_name(e) for e in enis
             if str(e.get("Status")) == "in-use" and e.get("PrivateIpAddress")}
LIVE_IFACE = set(ENI_OWNER)
devs = ((get(D42 + "/api/2.0/devices/") or {}).get("devices")) or []
in_service = [d for d in devs if d.get("in_service") in (True, "true", "yes", 1)]
ip_rows = ((get(D42 + "/api/2.0/ips/") or {}).get("ips")) or []
assigned = [r for r in ip_rows if str(r.get("available")) == "no"]
IPAM_OWNER = {str(r.get("ip")): str(r.get("label") or r.get("device"))
              for r in assigned if ":" not in str(r.get("ip"))}
LIVE_V4 = set(IPAM_OWNER) & LIVE_IFACE
HOST_IP = {}
for ip in LIVE_V4:
    owner = ENI_OWNER.get(ip) or IPAM_OWNER.get(ip)
    if owner:
        HOST_IP[owner] = ip
HOST_V6 = {str(r.get("device")): str(r.get("ip")) for r in assigned if ":" in str(r.get("ip"))}
_ghosts = [h for h in HOST_IP if not any(str(d.get("name")) == h for d in in_service)]
print("inventory: live hosts=%d (of which %d have a live iface but NO CMDB device) live v4=%d v6=%d"
      % (len(HOST_IP), len(_ghosts), len(LIVE_V4), len(HOST_V6)))

def short(name):
    n = str(name)
    return n[:-len("." + domain)] if n.endswith("." + domain) else n

def rec_uuid(rec):
    if rec.get("uuid"):
        return str(rec["uuid"])
    m = re.search(r"/([0-9a-f-]{36}):", str(rec.get("_ref", "")))
    return m.group(1) if m else None

a_recs = rows(DNS + "/record:a")
by_name = {}
for r in a_recs:
    by_name.setdefault(str(r.get("name")), []).append(r)

for name, recs in sorted(by_name.items()):
    host = short(name)
    if host in HOST_IP:
        live = HOST_IP[host]
        for r in recs:
            got = str(r.get("ipv4addr"))
            if got != live:
                kind = "stale-dead" if got not in LIVE_V4 else "ip-conflict(live-but-wrong)"
                res = call("PUT", DNS + "/record:a/" + rec_uuid(r), body={"ipv4addr": live})
                print("  repoint A %s: %s -> %s [%s] (%s)" % (name, got, live, kind,
                      "ok" if not (isinstance(res, dict) and res.get("_error")) else res))
    else:
        for r in recs:
            got = str(r.get("ipv4addr"))
            if got not in LIVE_V4:
                res = call("DELETE", DNS + "/record:a/" + rec_uuid(r))
                what = "dead RR member" if len(recs) > 1 else "dangling record (no host, dead addr)"
                print("  delete A %s -> %s [%s] (%s)" % (name, got, what,
                      "ok" if not (isinstance(res, dict) and res.get("_error")) else res))

have_names = {short(n) for n in by_name}
for host, ip in sorted(HOST_IP.items()):
    if host not in have_names and ip in LIVE_V4:
        res = call("POST", DNS + "/record:a", body={"name": host + "." + domain, "ipv4addr": ip,
                                                    "view": "default",
                                                    "comment": "Added during DNS/IPAM reconciliation."})
        print("  add A %s -> %s (%s)" % (host + "." + domain, ip,
              "ok" if not (isinstance(res, dict) and res.get("_error")) else res))

for r in rows(DNS + "/record:aaaa"):
    host = short(r.get("name"))
    got = str(r.get("ipv6addr"))
    live6 = HOST_V6.get(host)
    if live6 and got != live6:
        res = call("PUT", DNS + "/record:aaaa/" + rec_uuid(r), body={"ipv6addr": live6})
        print("  repoint AAAA %s: %s -> %s (%s)" % (r.get("name"), got, live6,
              "ok" if not (isinstance(res, dict) and res.get("_error")) else res))
    elif not live6 and host not in HOST_IP:
        res = call("DELETE", DNS + "/record:aaaa/" + rec_uuid(r))
        print("  delete dangling AAAA %s (%s)" % (r.get("name"),
              "ok" if not (isinstance(res, dict) and res.get("_error")) else res))

a_now = rows(DNS + "/record:a")
live_a_names = {str(r.get("name")) for r in a_now if str(r.get("ipv4addr")) in LIVE_V4}
for r in rows(DNS + "/record:cname"):
    canonical = str(r.get("canonical"))
    if canonical in live_a_names or short(canonical) in {short(n) for n in live_a_names}:
        continue
    base = re.split(r"[-.]", short(canonical))[0]
    target = next((n for n in sorted(live_a_names) if short(n) == base), None)
    if target:
        res = call("PUT", DNS + "/record:cname/" + rec_uuid(r), body={"canonical": target})
        print("  repoint CNAME %s: %s -> %s (%s)" % (r.get("name"), canonical, target,
              "ok" if not (isinstance(res, dict) and res.get("_error")) else res))
    else:
        res = call("DELETE", DNS + "/record:cname/" + rec_uuid(r))
        print("  delete dangling CNAME %s -> %s (%s)" % (r.get("name"), canonical,
              "ok" if not (isinstance(res, dict) and res.get("_error")) else res))

call("PATCH", SN + "/incident/%s" % inc_sys, body={
    "state": CLOSED, "close_code": "Solved (Permanently)",
    "close_notes": "The DNS grid maintenance was verified healthy (zone + delegation intact) and was "
                   "not the cause. The dispatch-tier re-IP migration had released the old addresses "
                   "without reconciling the forward zone. Reconciled every record against the CMDB/"
                   "IPAM inventory and live cloud interfaces: repointed stale and conflicting records "
                   "to each host's live address, removed records for decommissioned hosts and the dead "
                   "round-robin member, added records for the newly provisioned hosts, and fixed the "
                   "dangling aliases. Resolver, peer tiers and in-service legacy hosts left untouched."})

print("\n--- readback ---")
a2 = rows(DNS + "/record:a")
by2 = {}
for r in a2:
    by2.setdefault(str(r.get("name")), []).append(str(r.get("ipv4addr")))
for host, ip in sorted(HOST_IP.items()):
    if ip in LIVE_V4:
        got = by2.get(host + "." + domain, [])
        check("A %s -> %s (own live addr)" % (host, ip), got == [ip])
check("no A record resolves to a non-live address",
      all(ip in LIVE_V4 for ips in by2.values() for ip in ips))
gone = [n for n in by2 if short(n) not in HOST_IP and any(ip not in LIVE_V4 for ip in by2[n])]
check("no dangling A names remain", gone == [])
aaaa2 = rows(DNS + "/record:aaaa")
for r in aaaa2:
    host = short(r.get("name"))
    check("AAAA %s -> live v6" % host, str(r.get("ipv6addr")) == HOST_V6.get(host))
live_names2 = {str(r.get("name")) for r in a2 if str(r.get("ipv4addr")) in LIVE_V4}
for r in rows(DNS + "/record:cname"):
    check("CNAME %s canonical live" % r.get("name"), str(r.get("canonical")) in live_names2)
ns2 = [r for r in rows(DNS + "/record:ns") if str(r.get("name")) == domain]
check("NS delegation untouched (2 records)", len(ns2) == 2)
zones2 = rows(DNS + "/zone_auth")
check("zone untouched", len(zones2) == 1 and str(zones2[0].get("fqdn")) == domain)
inc2 = (get(SN + "/incident/%s" % inc_sys) or {}).get("result", {})
check("incident closed", str(inc2.get("state")) == CLOSED)

print("\n%d mismatch(es)" % len(MISMATCHES))
for m in MISMATCHES:
    print("  FAILED:", m)
sys.exit(1 if MISMATCHES else 0)
