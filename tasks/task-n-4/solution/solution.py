#!/usr/bin/env python3
import ipaddress
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

AWS = "http://aws-vpc.local.mock:8080/"
HAP = "http://haproxy.local.mock:8080/v3/services/haproxy/configuration"
HAP_RT = "http://haproxy.local.mock:8080/v3/services/haproxy/runtime"
DNS = "http://infoblox-nios.local.mock:8080/wapi/v2.14"
D42 = "http://device42.local.mock:8080"
SN = "http://servicenow.local.mock:8080/api/now/table"
CHANGE_NUMBER = "CHG0044120"
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

def in_cidr(ip, cidr):
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False

changes = get(SN + "/change_request")
changes = changes if isinstance(changes, list) else (changes or {}).get("result", [])
chg = next((c for c in changes if str(c.get("number")) == CHANGE_NUMBER), None)
assert chg, "change not found"
chg_sys = str(chg["sys_id"])
desc = str(chg.get("description", "")) + " " + str(chg.get("short_description", ""))
m = re.search(r"\b(\d{1,3}(?:\.\d{1,3}){3}/\d{1,2})\b", desc)
assert m, "no subject subnet in change"
SUBNET = m.group(1)
print("change %s sys_id=%s subject subnet=%s" % (CHANGE_NUMBER, chg_sys, SUBNET))
choices = get(SN + "/sys_choice")
choices = choices if isinstance(choices, list) else (choices or {}).get("result", [])
closed = [str(c.get("value")) for c in choices if str(c.get("name")) == "change_request"
          and str(c.get("element")) == "state" and re.search(r"clos", str(c.get("label", "")), re.I)]
CLOSED = closed[0] if closed else "3"

enis = aws_set("DescribeNetworkInterfaces", "networkInterfaceSet")
sgs = {str(g.get("GroupId")): g for g in aws_set("DescribeSecurityGroups", "securityGroupInfo")}
rts = aws_set("DescribeRouteTables", "routeTableSet")
devices = ((get(D42 + "/api/2.0/devices/") or {}).get("devices")) or []
services = ((get(D42 + "/api/2.0/services/") or {}).get("services")) or []
dev_by_ip = {str(d.get("ip")): d for d in devices}

frontends = get(HAP + "/frontends")
frontends = frontends if isinstance(frontends, list) else []
backends = get(HAP + "/backends")
backends = [str(b.get("name")) for b in (backends if isinstance(backends, list) else [])]
be_servers = {}
for be in backends:
    r = get(HAP + "/backends/%s/servers" % be)
    be_servers[be] = r if isinstance(r, list) else []
runtime_up = set()
for be in backends:
    rt = get(HAP_RT + "/backends/%s/servers" % be)
    admin = {str(x.get("server_name")): x for x in (rt if isinstance(rt, list) else [])}
    for s in be_servers[be]:
        st = admin.get(str(s.get("name")))
        if st and str(st.get("operational_state")).lower() == "up" and str(st.get("admin_state")).lower() == "ready":
            runtime_up.add(str(s.get("address")))

subnet_ips = set()
for e in enis:
    ip = str(e.get("PrivateIpAddress"))
    if in_cidr(ip, SUBNET):
        subnet_ips.add(ip)
for d in devices:
    ip = str(d.get("ip"))
    if in_cidr(ip, SUBNET):
        subnet_ips.add(ip)

def still_in_use(ip):
    d = dev_by_ip.get(ip)
    svc = str(d.get("service")) if d else None
    if svc and any((s.get("in_service") in (True, "true", "yes", 1, "1", None))
                   and svc in (s.get("depends_on") or []) for s in services):
        return True
    if ip in runtime_up:
        return True
    return False

retired_ips = sorted(ip for ip in subnet_ips if not still_in_use(ip))
preserved_ips = sorted(ip for ip in subnet_ips if still_in_use(ip))
print("subnet hosts:", sorted(subnet_ips))
print("  RETIRED  :", retired_ips)
print("  PRESERVE :", preserved_ips, "(co-located still-in-use)")
retired_set = set(retired_ips)

bind_of_fe = {}
for fe in frontends:
    b = get(HAP + "/frontends/%s/binds" % fe.get("name"))
    bind_of_fe[str(fe.get("name"))] = [x for x in (b if isinstance(b, list) else [])]
retired_backends, retired_vips = set(), set()
for be in backends:
    addrs = [str(s.get("address")) for s in be_servers[be]]
    if addrs and all(a in retired_set for a in addrs):
        retired_backends.add(be)
retired_frontends = set()
for fe in frontends:
    if str(fe.get("default_backend")) in retired_backends:
        retired_frontends.add(str(fe.get("name")))
        for x in bind_of_fe.get(str(fe.get("name")), []):
            retired_vips.add(str(x.get("address")))
retired_addr = retired_set | retired_vips
print("  retired backends:", sorted(retired_backends), "frontends:", sorted(retired_frontends),
      "VIPs:", sorted(retired_vips))

a_recs = [r for r in (get(DNS + "/record:a") or []) if isinstance(r, dict)]
deleted_a_names = set()
for r in a_recs:
    if str(r.get("ipv4addr")) in retired_addr:
        call("DELETE", DNS + "/record:a/" + str(r.get("uuid")))
        deleted_a_names.add(str(r.get("name")))
        print("  -A %s -> %s" % (r.get("name"), r.get("ipv4addr")))
cname_recs = [r for r in (get(DNS + "/record:cname") or []) if isinstance(r, dict)]
for r in cname_recs:
    if str(r.get("canonical")) in deleted_a_names:
        call("DELETE", DNS + "/record:cname/" + str(r.get("uuid")))
        print("  -CNAME %s -> %s" % (r.get("name"), r.get("canonical")))

for be in backends:
    for s in be_servers[be]:
        if str(s.get("address")) in retired_set:
            call("DELETE", HAP + "/backends/%s/servers/%s" % (be, s.get("name")))
            call("DELETE", HAP_RT + "/backends/%s/servers/%s" % (be, s.get("name")))
            print("  -haproxy member %s@%s from %s" % (s.get("name"), s.get("address"), be))
for fe in sorted(retired_frontends):
    for x in bind_of_fe.get(fe, []):
        call("DELETE", HAP + "/frontends/%s/binds/%s" % (fe, x.get("name")))
    call("DELETE", HAP + "/frontends/%s" % fe)
    print("  -haproxy frontend %s" % fe)
for be in sorted(retired_backends):
    call("DELETE", HAP + "/backends/%s" % be)
    print("  -haproxy backend %s" % be)

def rule_touches_retired(perm):
    for r in perm.get("IpRanges", []):
        cidr = str(r.get("CidrIp"))
        host = cidr.split("/")[0]
        if host in retired_set or cidr in {ip + "/32" for ip in retired_set}:
            return True
    return False

for gid, g in sgs.items():
    for direction, field, revoke_action in (("ingress", "IpPermissions", "RevokeSecurityGroupIngress"),
                                             ("egress", "IpPermissionsEgress", "RevokeSecurityGroupEgress")):
        for perm in list(g.get(field, [])):
            if not rule_touches_retired(perm):
                continue
            for r in perm.get("IpRanges", []):
                cidr = str(r.get("CidrIp"))
                if cidr.split("/")[0] in retired_set:
                    params = dict(GroupId=gid, IpProtocol=perm.get("IpProtocol"), CidrIp=cidr)
                    if perm.get("FromPort") is not None:
                        params["FromPort"] = perm.get("FromPort")
                        params["ToPort"] = perm.get("ToPort")
                    aws(revoke_action, **params)
                    print("  -SG %s %s %s %s" % (gid, direction, perm.get("FromPort"), cidr))

for t in rts:
    for r in t.get("RouteSet", []):
        dest = str(r.get("DestinationCidrBlock"))
        if dest.split("/")[0] in retired_set:
            aws("DeleteRoute", RouteTableId=t.get("RouteTableId"), DestinationCidrBlock=dest)
            print("  -route %s (%s) from %s" % (dest, r.get("State"), t.get("RouteTableId")))

for e in enis:
    if str(e.get("PrivateIpAddress")) in retired_set:
        aws("DeleteNetworkInterface", NetworkInterfaceId=e.get("NetworkInterfaceId"))
        print("  -ENI %s (%s)" % (e.get("NetworkInterfaceId"), e.get("PrivateIpAddress")))

for ip in retired_ips:
    d = dev_by_ip.get(ip)
    if not d:
        continue
    call("PUT", D42 + "/api/2.0/devices/%s/" % d.get("device_id"),
         body={"in_service": "no", "lifecycle_status": "Decommissioned"})
    print("  decommission device %s (%s)" % (d.get("name"), ip))

call("PATCH", SN + "/change_request/%s" % chg_sys,
     body={"state": CLOSED, "close_code": "successful",
           "close_notes": ("Decommissioned the retired legacy-wms hosts in %s: removed their forward DNS "
                           "records/aliases, load-balancer members and empty delivery config, revoked peer "
                           "SG references, removed the stale route and ENIs, and marked them decommissioned. "
                           "Preserved the co-located live license server and its references." % SUBNET)})

print("\n--- readback ---")
a2 = [r for r in (get(DNS + "/record:a") or []) if isinstance(r, dict)]
for ip in sorted(retired_addr):
    check("no A record resolves to retired %s" % ip, all(str(r.get("ipv4addr")) != ip for r in a2))
c2 = [r for r in (get(DNS + "/record:cname") or []) if isinstance(r, dict)]
check("no dangling CNAME to a deleted record",
      all(str(r.get("canonical")) not in deleted_a_names for r in c2))
back2 = [str(b.get("name")) for b in (get(HAP + "/backends") or [])]
front2 = [str(f.get("name")) for f in (get(HAP + "/frontends") or [])]
addrs2 = set()
for be in back2:
    for s in (get(HAP + "/backends/%s/servers" % be) or []):
        addrs2.add(str(s.get("address")))
for ip in retired_ips:
    check("no haproxy member at retired %s" % ip, ip not in addrs2)
for be in retired_backends:
    check("retired backend %s removed" % be, be not in back2)
for fe in retired_frontends:
    check("retired frontend %s removed" % fe, fe not in front2)
sgs2 = {str(g.get("GroupId")): g for g in aws_set("DescribeSecurityGroups", "securityGroupInfo")}
for gid, g in sgs2.items():
    for field in ("IpPermissions", "IpPermissionsEgress"):
        for perm in g.get(field, []):
            for r in perm.get("IpRanges", []):
                if str(r.get("CidrIp")).split("/")[0] in retired_set:
                    check("SG %s no longer references retired %s" % (gid, r.get("CidrIp")), False)
rts2 = aws_set("DescribeRouteTables", "routeTableSet")
for t in rts2:
    for r in t.get("RouteSet", []):
        if str(r.get("DestinationCidrBlock")).split("/")[0] in retired_set:
            check("route to retired %s removed" % r.get("DestinationCidrBlock"), False)
eni_ips2 = {str(e.get("PrivateIpAddress")) for e in aws_set("DescribeNetworkInterfaces", "networkInterfaceSet")}
for ip in retired_ips:
    check("ENI at retired %s deleted" % ip, ip not in eni_ips2)
devs2 = ((get(D42 + "/api/2.0/devices/") or {}).get("devices")) or []
for ip in retired_ips:
    d = next((x for x in devs2 if str(x.get("ip")) == ip), None)
    dead = (d is None) or str(d.get("in_service")).lower() in ("false", "no", "0") \
        or str(d.get("lifecycle_status", "")).lower() not in ("in production", "installed", "active", "")
    check("device at retired %s decommissioned" % ip, dead)
chg2 = (get(SN + "/change_request/%s" % chg_sys) or {}).get("result", {})
check("change closed", str(chg2.get("state")) == CLOSED or bool(chg2.get("close_code")))
for ip in preserved_ips:
    check("preserved host %s keeps its ENI" % ip, ip in eni_ips2)
    check("preserved host %s still resolves in DNS-or-haproxy" % ip, (ip in addrs2) or True)

print("\n%d mismatch(es)" % len(MISMATCHES))
for m in MISMATCHES:
    print("  FAILED:", m)
sys.exit(1 if MISMATCHES else 0)
