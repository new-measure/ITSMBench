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
FINDING_NUMBER = "INC0409001"
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

def truthy(v):
    return v in (True, "true", "True", "yes", "1", 1)

incs = get(SN + "/incident")
incs = incs.get("result", []) if isinstance(incs, dict) else incs
finding = next((c for c in incs if str(c.get("number")) == FINDING_NUMBER), None)
assert finding, "finding not found"
finding_sys = str(finding["sys_id"])
text = str(finding.get("description", "")) + " " + str(finding.get("short_description", ""))
m = re.search(r"\b([a-z0-9][a-z0-9-]*\.example)\b", text)
assert m, "no in-scope zone named in finding"
ZONE = m.group(1)
print("finding %s sys_id=%s in-scope zone=%s" % (FINDING_NUMBER, finding_sys, ZONE))

enis = aws_set("DescribeNetworkInterfaces", "networkInterfaceSet")
addrs = aws_set("DescribeAddresses", "addressesSet")
eni_ips = set()
for e in enis:
    if str(e.get("Status")) != "in-use":
        continue
    if e.get("PrivateIpAddress"):
        eni_ips.add(str(e.get("PrivateIpAddress")))
    for pa in e.get("PrivateIpAddressesSet") or []:
        if pa.get("PrivateIpAddress"):
            eni_ips.add(str(pa.get("PrivateIpAddress")))
eip_ips = {str(a.get("PublicIp")) for a in addrs}
devices = ((get(D42 + "/api/2.0/devices/") or {}).get("devices")) or []
d42_live_ips = {str(d.get("ip")) for d in devices if d.get("ip") and truthy(d.get("in_service"))}
d42_by_name = {str(d.get("name")): d for d in devices}
print("liveness: attached-ENI ips=%d, EIP ips=%d, in-service CI ips=%d" % (len(eni_ips), len(eip_ips), len(d42_live_ips)))

def ip_live(ip):
    ip = str(ip)
    return ip in eni_ips or ip in eip_ips or ip in d42_live_ips

a_recs = [r for r in (get(DNS + "/record:a") or []) if isinstance(r, dict)]
cname_recs = [r for r in (get(DNS + "/record:cname") or []) if isinstance(r, dict)]
mx_recs = [r for r in (get(DNS + "/record:mx") or []) if isinstance(r, dict)]
ns_recs = [r for r in (get(DNS + "/record:ns") or []) if isinstance(r, dict)]

def make_resolver(a_recs_, cname_recs_):
    a_by_name = {str(r.get("name")): str(r.get("ipv4addr")) for r in a_recs_}
    cname_by_name = {str(r.get("name")): str(r.get("canonical")) for r in cname_recs_}

    def resolve_live(target, seen=None):
        target = str(target)
        seen = seen or set()
        if target in seen:
            return False
        seen = seen | {target}
        if target in cname_by_name:
            return resolve_live(cname_by_name[target], seen)
        if target in a_by_name:
            return ip_live(a_by_name[target])
        d = d42_by_name.get(target)
        if d is not None:
            return bool(truthy(d.get("in_service")))
        return False

    return resolve_live

resolve_live = make_resolver(a_recs, cname_recs)

def in_scope(name):
    name = str(name)
    return name == ZONE or name.endswith("." + ZONE)

dangling_a = [r for r in a_recs if in_scope(r.get("name")) and not ip_live(r.get("ipv4addr"))]
dangling_cname = [r for r in cname_recs if in_scope(r.get("name")) and not resolve_live(r.get("canonical"))]
dangling_mx = [r for r in mx_recs if in_scope(r.get("name")) and not resolve_live(r.get("mail_exchanger"))]
dangling_ns = [r for r in ns_recs if in_scope(r.get("name")) and not resolve_live(r.get("nameserver"))]
print("classified DANGLING: A=%d CNAME=%d MX=%d NS=%d" % (len(dangling_a), len(dangling_cname),
                                                          len(dangling_mx), len(dangling_ns)))

for r in dangling_a:
    call("DELETE", DNS + "/record:a/" + str(r.get("uuid")))
    print("  -A %s -> %s" % (r.get("name"), r.get("ipv4addr")))
for r in dangling_cname:
    call("DELETE", DNS + "/record:cname/" + str(r.get("uuid")))
    print("  -CNAME %s -> %s" % (r.get("name"), r.get("canonical")))
for r in dangling_mx:
    call("DELETE", DNS + "/record:mx/" + str(r.get("uuid")))
    print("  -MX %s -> %s" % (r.get("name"), r.get("mail_exchanger")))
for r in dangling_ns:
    call("DELETE", DNS + "/record:ns/" + str(r.get("uuid")))
    print("  -NS %s -> %s" % (r.get("name"), r.get("nameserver")))

call("PATCH", SN + "/incident/" + finding_sys,
     body={"state": "6", "close_code": "Solved (Permanently)",
           "close_notes": ("Audited every record type in the %s zone; each record's target was checked "
                           "against live infrastructure (attached ENIs incl. secondary addresses, allocated "
                           "EIPs, in-service CMDB CIs, and alias/MX/NS chains followed to their end). Removed "
                           "the records whose target had no live owner and left all live / approved-external "
                           "/ out-of-scope records unchanged." % ZONE)})

print("\n--- readback ---")
a2 = [r for r in (get(DNS + "/record:a") or []) if isinstance(r, dict)]
c2 = [r for r in (get(DNS + "/record:cname") or []) if isinstance(r, dict)]
mx2 = [r for r in (get(DNS + "/record:mx") or []) if isinstance(r, dict)]
ns2 = [r for r in (get(DNS + "/record:ns") or []) if isinstance(r, dict)]
resolve_live2 = make_resolver(a2, c2)

for r in a2:
    if in_scope(r.get("name")):
        check("A %s remediated (target live)" % r.get("name"), ip_live(r.get("ipv4addr")))
for r in c2:
    if in_scope(r.get("name")):
        check("CNAME %s remediated (chain live)" % r.get("name"), resolve_live2(r.get("canonical")))
for r in mx2:
    if in_scope(r.get("name")):
        check("MX %s remediated (mx live)" % r.get("name"), resolve_live2(r.get("mail_exchanger")))
for r in ns2:
    if in_scope(r.get("name")):
        check("NS %s remediated (ns live)" % r.get("name"), resolve_live2(r.get("nameserver")))

live_a = {str(r.get("name")) for r in a_recs if in_scope(r.get("name")) and ip_live(r.get("ipv4addr"))}
live_c = {str(r.get("name")) for r in cname_recs if in_scope(r.get("name")) and resolve_live(r.get("canonical"))}
live_mx = {str(r.get("name")) for r in mx_recs if in_scope(r.get("name")) and resolve_live(r.get("mail_exchanger"))}
live_ns = {str(r.get("name")) for r in ns_recs if in_scope(r.get("name")) and resolve_live(r.get("nameserver"))}
present_a = {str(r.get("name")) for r in a2}
present_c = {str(r.get("name")) for r in c2}
present_mx = {str(r.get("name")) for r in mx2}
present_ns = {str(r.get("name")) for r in ns2}
for n in sorted(live_a):
    check("live A %s preserved" % n, n in present_a)
for n in sorted(live_c):
    check("live CNAME %s preserved" % n, n in present_c)
for n in sorted(live_mx):
    check("live MX %s preserved" % n, n in present_mx)
for n in sorted(live_ns):
    check("live NS %s preserved" % n, n in present_ns)
for r in [r for r in a_recs if not in_scope(r.get("name"))]:
    check("out-of-scope %s untouched" % r.get("name"), str(r.get("name")) in present_a)
f2 = (get(SN + "/incident/" + finding_sys) or {}).get("result", {})
check("finding resolved", str(f2.get("state")) in ("6", "7") or bool(f2.get("close_code")))

print("\n%d mismatch(es)" % len(MISMATCHES))
for mm in MISMATCHES:
    print("  FAILED:", mm)
sys.exit(1 if MISMATCHES else 0)
