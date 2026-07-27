#!/usr/bin/env python3

import json
import re
import sys
from datetime import datetime

import requests

INCIDENT_NUMBER = "INC0052841"

SN = "http://servicenow.local.mock:8080"
D42 = "http://device42.local.mock:8080"
IB = "http://infoblox-nios.local.mock:8080/wapi/v2.14"
HAP = "http://haproxy.local.mock:8080/v3/services/haproxy"
ZIA = "http://zscaler-zia.local.mock:8080/zia/api/v1"
VPC = "http://aws-vpc.local.mock:8080"

session = requests.Session()
WRITES = []
MISMATCHES = []

def fail(link, detail=""):
    print(f"EVIDENCE LINK MISSING: {link}" + (f" — {detail}" if detail else ""))
    sys.exit(2)

def get_json(url, params=None):
    r = session.get(url, params=params, timeout=30)
    if r.status_code != 200:
        fail(f"GET {url}", f"status {r.status_code}: {r.text[:200]}")
    return r.json()

def write(method, url, *, json_body=None, data=None, ok=(200, 201, 204)):
    r = session.request(method, url, json=json_body, data=data, timeout=30)
    WRITES.append(f"{method} {url} {json.dumps(json_body or data or {}, sort_keys=True)} -> {r.status_code}")
    if r.status_code not in ok:
        fail(f"{method} {url}", f"status {r.status_code}: {r.text[:300]}")
    return r

def parse_ts(value):
    s = str(value or "").replace("T", " ").rstrip("Z")
    try:
        return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None

def tokens(value):
    return {t for t in re.split(r"[^a-z0-9]+", str(value).lower()) if t}

def subnet24(ip):
    return ".".join(str(ip).split(".")[:3])

def sn_table(table):
    rows, offset = [], 0
    while True:
        page = get_json(f"{SN}/api/now/table/{table}",
                        {"sysparm_limit": 200, "sysparm_offset": offset}).get("result", [])
        rows.extend(page)
        if len(page) < 200:
            return rows
        offset += 200

def d42_list(path, list_key):
    rows, offset = [], 0
    while True:
        env = get_json(f"{D42}{path}", {"limit": 200, "offset": offset})
        page = env.get(list_key, [])
        rows.extend(page)
        offset += 200
        if offset >= int(env.get("total_count", len(rows))) or not page:
            return rows

def ib_list(record_type):
    rows, page_id = [], None
    while True:
        params = {"_paging": 1, "_max_results": 200, "_return_as_object": 1}
        if page_id:
            params["_page_id"] = page_id
        env = get_json(f"{IB}/{record_type}", params)
        rows.extend(env.get("result", []))
        page_id = env.get("next_page_id")
        if not page_id:
            return rows

def zia_rules_all():
    rows, page = [], 1
    while True:
        chunk = get_json(f"{ZIA}/firewallFilteringRules", {"page": page, "pageSize": 100})
        rows.extend(chunk)
        if len(chunk) < 100:
            return rows
        page += 1

def vpc_query(action, extra=None):
    data = {"Action": action, "Version": "2016-11-15"}
    data.update(extra or {})
    r = session.post(VPC + "/", data=data, timeout=30)
    if action.startswith(("Revoke", "Authorize")):
        WRITES.append(f"EC2 {action} {json.dumps(extra or {}, sort_keys=True)} -> {r.status_code}")
    if r.status_code != 200:
        fail(f"EC2 {action}", f"status {r.status_code}: {r.text[:300]}")
    return r.json()

def vpc_security_groups():
    rows, token = [], None
    while True:
        extra = {"MaxResults": 200}
        if token:
            extra["NextToken"] = token
        out = vpc_query("DescribeSecurityGroups", extra)
        rows.extend(out.get("securityGroupInfo", {}).get("item", []))
        token = out.get("nextToken")
        if not token:
            return rows

incidents = sn_table("incident")
trigger = [r for r in incidents if str(r.get("number")) == INCIDENT_NUMBER]
if len(trigger) != 1:
    fail("C1 trigger incident", f"found {len(trigger)}")
trigger = trigger[0]
text = f"{trigger.get('short_description', '')} {trigger.get('description', '')}"
chg = sorted(set(re.findall(r"\bCHG\d+\b", text)))
if len(chg) != 1:
    fail("C1 blamed change", f"expected one CHG token, got {chg}")
blamed = chg[0]
text_tokens = tokens(text)

backends = get_json(f"{HAP}/configuration/backends")
anchors = [b["name"] for b in backends
           if tokens(b["name"].replace("be_", "", 1)) <= text_tokens]
if len(anchors) != 1:
    fail("C1 anchor backend", f"matched {anchors}")
anchor = anchors[0]
print(f"[1] trigger {INCIDENT_NUMBER}; blamed change {blamed}; anchor backend {anchor}")

devices = d42_list("/api/2.0/devices/", "devices")
ips_rows = d42_list("/api/2.0/ips/", "ips")
audits = d42_list("/api/1.0/auditlogs/", "auditlogs")
a_records = ib_list("record:a")
cname_records = ib_list("record:cname")
backend_servers = {b["name"]: get_json(f"{HAP}/configuration/backends/{b['name']}/servers")
                   for b in backends}
runtime_servers = {b["name"]: get_json(f"{HAP}/runtime/backends/{b['name']}/servers")
                   for b in backends}
zia_rules = zia_rules_all()
zia_groups = get_json(f"{ZIA}/ipSourceGroups")
sgs = vpc_security_groups()
crs = sn_table("change_request")

assigned = {str(r["ip"]): str(r.get("device", "")) for r in ips_rows}
print(f"[2] world: {len(devices)} devices, {len(ips_rows)} ips, {len(audits)} audit rows, "
      f"{len(a_records)} A, {len(backends)} backends, {len(zia_rules)} zia rules, {len(sgs)} SGs")

anchor_addrs = [str(s.get("address")) for s in backend_servers[anchor]]
seam_assigned = [a for a in anchor_addrs if a in assigned]
seam_orphaned = [a for a in anchor_addrs if a not in assigned]
if len(seam_assigned) != 1 or not seam_orphaned:
    fail("C2 seam", f"assigned={seam_assigned} orphaned={seam_orphaned}")
NEW24 = subnet24(seam_assigned[0])
OLD24 = subnet24(seam_orphaned[0])
if NEW24 == OLD24:
    fail("C2 seam subnets", f"old and new collapse to {NEW24}")
print(f"[3] retired subnet {OLD24}.0/24 -> current {NEW24}.0/24")

def is_old(addr):
    return subnet24(addr) == OLD24 if re.match(r"^(?:\d{1,3}\.){3}\d{1,3}$", str(addr)) else False

old_to_device = {}
for a in audits:
    fields = a.get("object_fields")
    try:
        fields = json.loads(fields) if isinstance(fields, str) else (fields or {})
    except ValueError:
        continue
    ip = str(fields.get("ip", ""))
    if is_old(ip) and fields.get("device"):
        old_to_device[ip] = str(fields["device"])

device_new = {}
for r in ips_rows:
    if subnet24(r["ip"]) == NEW24 and r.get("device"):
        device_new.setdefault(str(r["device"]), []).append(str(r["ip"]))

MAP = {}
for old, dev in sorted(old_to_device.items()):
    news = device_new.get(dev, [])
    if len(news) != 1:
        fail("C3 old->new map", f"{dev} has {len(news)} current addresses in {NEW24}.0/24")
    MAP[old] = (dev, news[0])
if not MAP:
    fail("C3 old->new map", "no audit-derived pairs")
print(f"[4] renumber map covers {len(MAP)} hosts")

def mapped(old, context):
    if old not in MAP:
        fail("C3 unmappable reference", f"{context} references {old}")
    return MAP[old][1]

blamed_rows = [r for r in crs if str(r.get("number")) == blamed]
if len(blamed_rows) != 1:
    fail("C4 blamed change resolves", blamed)
blamed_cr = blamed_rows[0]
if str(blamed_cr.get("state")) not in ("3", "closed", "Closed"):
    fail("C4 blamed change closed", f"state={blamed_cr.get('state')}")
if not blamed_cr.get("parent"):
    fail("C4 blamed change program linkage", "no parent change")
onset = parse_ts(trigger.get("opened_at"))
executed = parse_ts(blamed_cr.get("closed_at"))
if not (executed and onset and executed < onset):
    fail("C4 chronology", f"change closed {executed}, incident opened {onset}")
print(f"[5] blamed change {blamed} verified: closed {executed}, part of "
      f"{next((r.get('number') for r in crs if r.get('sys_id') == blamed_cr.get('parent')), '?')} "
      f"— innocent; fixing forward")

plan = []

for rec in a_records:
    ip = str(rec.get("ipv4addr"))
    if is_old(ip):
        new = mapped(ip, f"A {rec.get('name')}")
        ref = rec["_ref"]
        plan.append((f"dns: {rec.get('name')} {ip} -> {new}",
                     lambda ref=ref, new=new: write(
                         "PUT", f"{IB}/record:a/{requests.utils.quote(ref, safe='')}",
                         json_body={"ipv4addr": new})))

for bname, servers in backend_servers.items():
    for s in servers:
        addr = str(s.get("address"))
        if is_old(addr):
            new = mapped(addr, f"server {bname}/{s['name']}")
            body = {"name": s["name"], "address": new, "port": s.get("port"),
                    "check": s.get("check", "enabled")}
            plan.append((f"lb config: {bname}/{s['name']} {addr} -> {new}",
                         lambda b=bname, n=s["name"], body=body: write(
                             "PUT", f"{HAP}/configuration/backends/{b}/servers/{n}",
                             json_body=body)))
for bname, rows in runtime_servers.items():
    for r in rows:
        addr = str(r.get("address"))
        if is_old(addr):
            new = mapped(addr, f"runtime {bname}/{r.get('server_name')}")
            rname = str(r.get("server_name") or r.get("name"))
            plan.append((f"lb runtime: {bname}/{rname} {addr} -> {new}",
                         lambda b=bname, n=rname, new=new: write(
                             "PUT", f"{HAP}/runtime/backends/{b}/servers/{n}",
                             json_body={"address": new})))

zia_dirty = False
for rule in zia_rules:
    src = [str(s) for s in (rule.get("srcIps") or [])]
    if any(is_old(s) for s in src):
        new_src = [mapped(s, f"zia rule {rule.get('name')}") if is_old(s) else s for s in src]
        rid = rule["id"]
        plan.append((f"zia rule: {rule.get('name')} srcIps {src} -> {new_src}",
                     lambda rid=rid, new_src=new_src: write(
                         "PUT", f"{ZIA}/firewallFilteringRules/{rid}",
                         json_body={"srcIps": new_src})))
        zia_dirty = True
for g in zia_groups:
    addrs = [str(a) for a in (g.get("ipAddresses") or [])]
    hit = [a for a in addrs if a == f"{OLD24}.0/24" or is_old(a.split("/")[0])]
    if hit:
        new_addrs = []
        for a in addrs:
            if a == f"{OLD24}.0/24":
                new_addrs.append(f"{NEW24}.0/24")
            elif is_old(a.split("/")[0]):
                new_addrs.append(mapped(a.split("/")[0], f"zia group {g.get('name')}")
                                 + ("/" + a.split("/")[1] if "/" in a else ""))
            else:
                new_addrs.append(a)
        gid = g["id"]
        plan.append((f"zia group: {g.get('name')} {hit} -> new range",
                     lambda gid=gid, new_addrs=new_addrs: write(
                         "PUT", f"{ZIA}/ipSourceGroups/{gid}",
                         json_body={"ipAddresses": new_addrs})))
        zia_dirty = True

for sg in sgs:
    for perm in sg.get("IpPermissions") or []:
        ranges = perm.get("IpRanges") or []
        hits = [r for r in ranges if is_old(str(r.get("CidrIp", "")).split("/")[0])]
        if not hits:
            continue
        if len(hits) != len(ranges):
            fail("C3 SG permission purity", f"{sg.get('GroupId')} mixes old and live ranges")
        base = {"GroupId": sg["GroupId"], "IpPermissions.1.IpProtocol": str(perm.get("IpProtocol"))}
        if perm.get("FromPort") is not None:
            base["IpPermissions.1.FromPort"] = str(perm["FromPort"])
        if perm.get("ToPort") is not None:
            base["IpPermissions.1.ToPort"] = str(perm["ToPort"])
        revoke = dict(base)
        authorize = dict(base)
        for i, r in enumerate(ranges, start=1):
            old_ip = str(r["CidrIp"]).split("/")[0]
            revoke[f"IpPermissions.1.IpRanges.{i}.CidrIp"] = str(r["CidrIp"])
            authorize[f"IpPermissions.1.IpRanges.{i}.CidrIp"] = \
                mapped(old_ip, f"SG {sg.get('GroupName')}") + "/32"
        plan.append((f"sg: {sg.get('GroupName')} tcp/{perm.get('FromPort')} "
                     f"{[r['CidrIp'] for r in ranges]} -> new /32",
                     lambda revoke=revoke, authorize=authorize: (
                         vpc_query("RevokeSecurityGroupIngress", revoke),
                         vpc_query("AuthorizeSecurityGroupIngress", authorize))))

touched_hosts = {MAP[o][0] for o in MAP
                 if any(o in label for label, _ in plan)}
consistent = [d for d in MAP.values() if d[0] not in touched_hosts]
if len(consistent) < 6:
    fail("C5 diff standard", f"only {len(consistent)} hosts already consistent")

print(f"[6] PLAN ({len(plan)} fixes; {len(consistent)} hosts already consistent, untouched):")
for label, _ in plan:
    print(f"    - {label}")

for label, action in plan:
    action()

if zia_dirty:
    status = get_json(f"{ZIA}/status").get("status")
    if status != "PENDING":
        MISMATCHES.append(f"zia activation expected PENDING after writes, got {status}")
    write("POST", f"{ZIA}/status/activate")

write("PATCH", f"{SN}/api/now/table/incident/{trigger['sys_id']}",
      json_body={
          "state": "6",
          "close_notes": (
              f"{blamed} is not at fault: it retired the old range as planned and "
              f"exposed records that were never migrated. The automated renumber push "
              f"partially applied (its change closed as completed despite stopping "
              f"early) and skipped the legacy-named hosts entirely. All remaining "
              f"references to the retired range have been repointed to the current "
              f"Device42 addresses across DNS, load balancer config and runtime, "
              f"egress firewall and cloud security groups; policies activated."
          ),
      })

def sweep_old():
    found = []
    for rec in ib_list("record:a"):
        if is_old(rec.get("ipv4addr")):
            found.append(f"A {rec.get('name')}")
    for b in get_json(f"{HAP}/configuration/backends"):
        for s in get_json(f"{HAP}/configuration/backends/{b['name']}/servers"):
            if is_old(s.get("address")):
                found.append(f"config {b['name']}/{s['name']}")
        for r in get_json(f"{HAP}/runtime/backends/{b['name']}/servers"):
            if is_old(r.get("address")):
                found.append(f"runtime {b['name']}/{r.get('server_name')}")
    for rule in zia_rules_all():
        if any(is_old(s) for s in (rule.get("srcIps") or [])):
            found.append(f"zia rule {rule.get('name')}")
    for g in get_json(f"{ZIA}/ipSourceGroups"):
        for a in g.get("ipAddresses") or []:
            if str(a) == f"{OLD24}.0/24" or is_old(str(a).split("/")[0]):
                found.append(f"zia group {g.get('name')}")
    for sg in vpc_security_groups():
        for perm in sg.get("IpPermissions") or []:
            for r in perm.get("IpRanges") or []:
                if is_old(str(r.get("CidrIp", "")).split("/")[0]):
                    found.append(f"sg {sg.get('GroupName')} {r.get('CidrIp')}")
    return found

left = sweep_old()
if left:
    MISMATCHES.append(f"old-subnet references remain: {left}")
for rec in ib_list("record:a"):
    name_host = str(rec.get("name", "")).split(".")[0]
    for old, (dev, new) in MAP.items():
        if name_host == dev and str(rec.get("ipv4addr")) != new:
            MISMATCHES.append(f"A {rec.get('name')} is {rec.get('ipv4addr')}, expected {new}")
if get_json(f"{ZIA}/status").get("status") != "ACTIVE":
    MISMATCHES.append("zia activation not ACTIVE")
inc = get_json(f"{SN}/api/now/table/incident/{trigger['sys_id']}").get("result", {})
if str(inc.get("state")) not in ("6", "7"):
    MISMATCHES.append(f"incident state {inc.get('state')!r}")

print(f"[7] WRITE LIST ({len(WRITES)}):")
for w in WRITES:
    print(f"    {w}")
if MISMATCHES:
    print(f"[8] READBACK MISMATCHES ({len(MISMATCHES)}):")
    for m in MISMATCHES:
        print(f"    !! {m}")
    sys.exit(1)
print("[8] readback clean — oracle complete")
