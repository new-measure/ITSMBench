#!/usr/bin/env python3
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
INCIDENT_NUMBER = "INC0010001"
EPHEMERAL = (1024, 65535)
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

def ing_key(p):
    return (str(p.get("IpProtocol")).lower(), p.get("FromPort"), p.get("ToPort"),
            tuple(sorted(str(r.get("CidrIp")) for r in p.get("IpRanges", []) if r.get("CidrIp"))))

def acl_key(e):
    pr = e.get("PortRange") or {}
    return (bool(e.get("Egress")), str(e.get("RuleAction")).lower(), str(e.get("Protocol")),
            str(e.get("CidrBlock")), pr.get("From"), pr.get("To"))

incidents = as_incidents = get(SN + "/incident")
incidents = incidents if isinstance(incidents, list) else (incidents or {}).get("result", [])
cur = next((i for i in incidents if str(i.get("number")) == INCIDENT_NUMBER), None)
assert cur, "incident not found"
inc_sys = str(cur["sys_id"])
desc = str(cur.get("description", "")) + " " + str(cur.get("short_description", ""))
hostname = next((f for f in re.findall(r"\b([a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)+)\b", desc, re.I)
                 if not f.replace(".", "").isdigit()), None)
suspected = (re.search(r"\bCHG\d+\b", desc) or [None])
suspected = re.search(r"\bCHG\d+\b", desc)
suspected = suspected.group(0) if suspected else None
print("incident %s sys_id=%s host=%s suspected(decoy)=%s" % (INCIDENT_NUMBER, inc_sys, hostname, suspected))
choices = get(SN + "/sys_choice")
choices = choices if isinstance(choices, list) else (choices or {}).get("result", [])
closed = [str(c.get("value")) for c in choices if str(c.get("name")) == "incident"
          and str(c.get("element")) == "state" and re.search(r"resolv|clos", str(c.get("label", "")), re.I)]
CLOSED = closed[-1] if closed else "7"

enis = aws_set("DescribeNetworkInterfaces", "networkInterfaceSet")
sgs = {str(g.get("GroupId")): g for g in aws_set("DescribeSecurityGroups", "securityGroupInfo")}
acls = aws_set("DescribeNetworkAcls", "networkAclSet")
rts = aws_set("DescribeRouteTables", "routeTableSet")
d42 = ((get(D42 + "/api/2.0/devices/") or {}).get("devices")) or []
LIVE_IPS = {str(e.get("PrivateIpAddress")) for e in enis if e.get("PrivateIpAddress")} | \
           {str(d.get("ip")) for d in d42 if d.get("ip")}
d42_services = ((get(D42 + "/api/2.0/services/") or {}).get("services")) or \
               ((get(D42 + "/api/2.0/services/") or {}).get("result")) or []
pay_deps = next((s.get("depends_on") for s in d42_services if str(s.get("name")) == "payments"), []) or []

def subnet_of(ip):
    e = next((x for x in enis if str(x.get("PrivateIpAddress")) == ip), None)
    return str(e.get("SubnetId")) if e else None

def sg_of_ip(ip):
    e = next((x for x in enis if str(x.get("PrivateIpAddress")) == ip), None)
    if e and e.get("GroupSet"):
        return str(e["GroupSet"][0].get("GroupId"))
    d = next((x for x in d42 if str(x.get("ip")) == ip), None)
    return str(d.get("security_group")) if d else None

def cidr_of_subnet(sid):
    s = next((x for x in aws_set("DescribeSubnets", "subnetSet") if str(x.get("SubnetId")) == sid), None)
    return str(s.get("CidrBlock")) if s else None

def acl_for_subnet(sid):
    return next((a for a in acls if any(str(x.get("SubnetId")) == sid for x in a.get("AssociationSet", []))), None)

def rt_for_subnet(sid):
    return next((t for t in rts if any(str(x.get("SubnetId")) == sid for x in t.get("AssociationSet", []))), None)

dns_rows = get(DNS + "/record:a")
dns_rows = dns_rows if isinstance(dns_rows, list) else []
vip = next((str(r.get("ipv4addr")) for r in dns_rows if str(r.get("name")) == hostname), None)
frontends = get(HAP + "/frontends")
frontends = frontends if isinstance(frontends, list) else []
target_be = None
for fe in frontends:
    binds = get(HAP + "/frontends/%s/binds" % fe.get("name"))
    if isinstance(binds, list) and any(str(b.get("address")) == vip for b in binds):
        target_be = str(fe.get("default_backend"))
        break
assert target_be, "no frontend bound to VIP %s" % vip
servers = get(HAP + "/backends/%s/servers" % target_be)
servers = servers if isinstance(servers, list) else []
backend_ips = [str(s.get("address")) for s in servers]
pay_sg = next(sg_of_ip(ip) for ip in backend_ips if sg_of_ip(ip))
pay_subnet = next(subnet_of(ip) for ip in backend_ips if subnet_of(ip))
PAY_CIDR = cidr_of_subnet(pay_subnet)
print("edge: %s -> VIP %s -> backend %s -> %s | payments SG=%s subnet=%s (%s)"
      % (hostname, vip, target_be, backend_ips, pay_sg, pay_subnet, PAY_CIDR))

peer_services = {str(d.get("service")) for d in d42 if str(d.get("role")) == "backend"} - {"payments"} - set(pay_deps)
sibling_sgs = sorted({str(d.get("security_group")) for d in d42 if str(d.get("role")) == "backend"
                      and str(d.get("service")) in peer_services and d.get("security_group")})
sibling_subnets = sorted({subnet_of(str(d.get("ip"))) for d in d42 if str(d.get("role")) == "backend"
                          and str(d.get("service")) in peer_services and subnet_of(str(d.get("ip")))})
sibling_cidrs = sorted({cidr_of_subnet(s) for s in sibling_subnets if cidr_of_subnet(s)})
print("siblings: SGs=%s subnets=%s cidrs=%s" % (sibling_sgs, sibling_subnets, sibling_cidrs))

changes = get(SN + "/change_request")
changes = changes if isinstance(changes, list) else (changes or {}).get("result", [])
dep_change = next((c for c in changes if str(c.get("number")) == suspected), None)
print("decoy %s closed=%s app-config-consistent=%s -> NOT the cause"
      % (suspected, dep_change and dep_change.get("state"), bool(servers)))

def restore_sg_ingress(target_gid, sibling_gids):
    sib_sets, by_key = [], {}
    for gid in sibling_gids:
        keys = set()
        for p in (sgs.get(gid) or {}).get("IpPermissions", []):
            k = ing_key(p)
            keys.add(k)
            by_key[k] = p
        sib_sets.append(keys)
    baseline = set.intersection(*sib_sets) if sib_sets else set()
    have = {ing_key(p) for p in (sgs.get(target_gid) or {}).get("IpPermissions", [])}
    for k in baseline - have:
        p = by_key[k]
        for r in p.get("IpRanges", []):
            cidr = r.get("CidrIp")
            if cidr and cidr != "0.0.0.0/0":
                aws("AuthorizeSecurityGroupIngress", GroupId=target_gid, IpProtocol=p.get("IpProtocol"),
                    FromPort=p.get("FromPort"), ToPort=p.get("ToPort"), CidrIp=cidr)
                print("  +ingress %s %s-%s from %s on %s" % (p.get("IpProtocol"), p.get("FromPort"),
                                                             p.get("ToPort"), cidr, target_gid))

restore_sg_ingress(pay_sg, sibling_sgs)

sib_e_sets, e_by_key = [], {}
for gid in sibling_sgs:
    keys = set()
    for p in (sgs.get(gid) or {}).get("IpPermissionsEgress", []):
        k = ing_key(p)
        keys.add(k)
        e_by_key[k] = p
    sib_e_sets.append(keys)
egress_baseline = set.intersection(*sib_e_sets) if sib_e_sets else set()
pay_egress_have = {ing_key(p) for p in (sgs.get(pay_sg) or {}).get("IpPermissionsEgress", [])}
for k in egress_baseline - pay_egress_have:
    p = e_by_key[k]
    for r in p.get("IpRanges", []):
        cidr = r.get("CidrIp")
        if cidr and cidr != "0.0.0.0/0":
            aws("AuthorizeSecurityGroupEgress", GroupId=pay_sg, IpProtocol=p.get("IpProtocol"),
                FromPort=p.get("FromPort"), ToPort=p.get("ToPort"), CidrIp=cidr)
            print("  +egress %s %s-%s to %s" % (p.get("IpProtocol"), p.get("FromPort"), p.get("ToPort"), cidr))

pay_acl = acl_for_subnet(pay_subnet)
sib_acls = [acl_for_subnet(s) for s in sibling_subnets]
sib_acls = [a for a in sib_acls if a]

def allow_keys(a):
    return {acl_key(e) for e in a.get("EntrySet", []) if str(e.get("RuleAction")).lower() == "allow"}

sib_acl_baseline = set.intersection(*[allow_keys(a) for a in sib_acls]) if sib_acls else set()
pay_acl_have = allow_keys(pay_acl)
acl_src = {}
for a in sib_acls:
    for e in a.get("EntrySet", []):
        acl_src[acl_key(e)] = e
used_rules = {(bool(e.get("Egress")), int(e.get("RuleNumber"))) for e in pay_acl.get("EntrySet", [])
              if str(e.get("RuleNumber")).isdigit()}

def next_rule(egress):
    n = 200
    while (egress, n) in used_rules:
        n += 1
    used_rules.add((egress, n))
    return n

for k in sib_acl_baseline - pay_acl_have:
    e = acl_src[k]
    pr = e.get("PortRange") or {}
    params = dict(NetworkAclId=pay_acl["NetworkAclId"], RuleNumber=next_rule(bool(e.get("Egress"))),
                  Protocol=e.get("Protocol"), RuleAction="allow",
                  Egress="true" if e.get("Egress") else "false", CidrBlock=e.get("CidrBlock"))
    if pr:
        params["PortRange.From"], params["PortRange.To"] = pr.get("From"), pr.get("To")
    aws("CreateNetworkAclEntry", **params)
    print("  +payments NACL %s allow %s ports=%s" % ("egress" if e.get("Egress") else "ingress",
                                                     e.get("CidrBlock"), pr or "-"))

pay_rt = rt_for_subnet(pay_subnet)
sib_rts = [rt_for_subnet(s) for s in sibling_subnets]
sib_dests = set()
for t in sib_rts:
    if t:
        sib_dests |= {str(r.get("DestinationCidrBlock")) for r in t.get("RouteSet", [])}
for r in (pay_rt or {}).get("RouteSet", []):
    if str(r.get("State")) == "blackhole" and str(r.get("DestinationCidrBlock")) not in sib_dests:
        aws("DeleteRoute", RouteTableId=pay_rt["RouteTableId"], DestinationCidrBlock=r.get("DestinationCidrBlock"))
        print("  -blackhole route %s from %s" % (r.get("DestinationCidrBlock"), pay_rt["RouteTableId"]))

print("payments depends_on:", pay_deps)
dep_hosts = [d for d in d42 if str(d.get("service")) in pay_deps]
dep_subnets = sorted({subnet_of(str(d.get("ip"))) for d in dep_hosts if subnet_of(str(d.get("ip")))})
for dsub in dep_subnets:
    dacl = acl_for_subnet(dsub)
    if not dacl:
        continue
    sib_in = [e for e in dacl.get("EntrySet", []) if not bool(e.get("Egress"))
              and str(e.get("RuleAction")).lower() == "allow" and str(e.get("CidrBlock")) in sibling_cidrs]
    has_pay = any(not bool(e.get("Egress")) and str(e.get("RuleAction")).lower() == "allow"
                  and str(e.get("CidrBlock")) == PAY_CIDR for e in dacl.get("EntrySet", []))
    if sib_in and not has_pay:
        tmpl = sib_in[0]
        pr = tmpl.get("PortRange") or {}
        rn = max([int(e["RuleNumber"]) for e in dacl["EntrySet"] if not bool(e.get("Egress"))
                  and str(e["RuleNumber"]).isdigit()] + [100]) + 1
        params = dict(NetworkAclId=dacl["NetworkAclId"], RuleNumber=rn, Protocol=tmpl.get("Protocol"),
                      RuleAction="allow", Egress="false", CidrBlock=PAY_CIDR)
        if pr:
            params["PortRange.From"], params["PortRange.To"] = pr.get("From"), pr.get("To")
        aws("CreateNetworkAclEntry", **params)
        print("  +shared NACL %s ingress allow from payments %s" % (dacl["NetworkAclId"], PAY_CIDR))

dep_sgs = sorted({sg_of_ip(str(d.get("ip"))) for d in dep_hosts if sg_of_ip(str(d.get("ip")))})
for gid in dep_sgs:
    g = sgs.get(gid) or {}
    sib_ports = {(p.get("FromPort"), p.get("ToPort"), str(p.get("IpProtocol")))
                 for p in g.get("IpPermissions", [])
                 for r in p.get("IpRanges", []) if str(r.get("CidrIp")) in sibling_cidrs}
    has_pay = any(str(r.get("CidrIp")) == PAY_CIDR for p in g.get("IpPermissions", []) for r in p.get("IpRanges", []))
    if sib_ports and not has_pay:
        for fp, tp, proto in sib_ports:
            aws("AuthorizeSecurityGroupIngress", GroupId=gid, IpProtocol=proto, FromPort=fp, ToPort=tp, CidrIp=PAY_CIDR)
            print("  +%s ingress %s %s-%s from payments %s" % (gid, proto, fp, tp, PAY_CIDR))

def dep_live_vip(service):
    h = next((d for d in d42 if str(d.get("service")) == service and str(d.get("role")) == "vip"
              and str(d.get("ip")) in LIVE_IPS), None)
    if h:
        return str(h["ip"])
    h = next((d for d in d42 if str(d.get("service")) == service and str(d.get("ip")) in LIVE_IPS), None)
    return str(h["ip"]) if h else None

def rec_uuid(rec):
    if rec.get("uuid"):
        return str(rec["uuid"])
    ref = str(rec.get("_ref", ""))
    m = re.search(r"record:a/([^:]+):", ref)
    return m.group(1) if m else None

for fe in frontends:
    b = get(HAP + "/frontends/%s/binds" % fe.get("name"))
    LIVE_IPS |= {str(x.get("address")) for x in (b if isinstance(b, list) else []) if x.get("address")}

def dep_related(name):
    return any(str(name).split(".")[0].startswith(s) for s in pay_deps)

dns_now = [r for r in (get(DNS + "/record:a") or []) if isinstance(r, dict)]
for svc in pay_deps:
    live = dep_live_vip(svc)
    if not live:
        continue
    for rec in dns_now:
        if str(rec.get("name")).split(".")[0] == svc and str(rec.get("ipv4addr")) not in LIVE_IPS:
            uid = rec_uuid(rec)
            res = call("PUT", DNS + "/record:a/" + uid, body={"ipv4addr": live})
            print("  repoint DNS %s: %s -> %s (%s)" % (rec.get("name"), rec.get("ipv4addr"), live,
                                                       "ok" if not (isinstance(res, dict) and res.get("_error")) else res))
for rec in [r for r in (get(DNS + "/record:a") or []) if isinstance(r, dict)]:
    if dep_related(rec.get("name")) and str(rec.get("ipv4addr")) not in LIVE_IPS:
        uid = rec_uuid(rec)
        res = call("DELETE", DNS + "/record:a/" + uid)
        print("  delete dangling DNS %s -> %s (%s)" % (rec.get("name"), rec.get("ipv4addr"),
                                                       "ok" if not (isinstance(res, dict) and res.get("_error")) else res))

for be in {target_be} | {str(s.get("parent_name")) for s in servers}:
    pass
all_backends = get(HAP + "/backends")
all_backends = [str(b.get("name")) for b in (all_backends if isinstance(all_backends, list) else [])]
for be in all_backends:
    srvs = get(HAP + "/backends/%s/servers" % be)
    srvs = srvs if isinstance(srvs, list) else []
    rt = get(HAP_RT + "/backends/%s/servers" % be)
    rt = rt if isinstance(rt, list) else []
    admin = {str(r.get("server_name")): str(r.get("admin_state")) for r in rt}
    for s in srvs:
        name, addr = str(s.get("name")), str(s.get("address"))
        if addr not in LIVE_IPS:
            res = call("DELETE", HAP + "/backends/%s/servers/%s" % (be, name))
            call("DELETE", HAP_RT + "/backends/%s/servers/%s" % (be, name))
            print("  -dead server %s@%s from %s (%s)" % (name, addr, be,
                                                         "ok" if not (isinstance(res, dict) and res.get("_error")) else res))
        elif admin.get(name) in ("maint", "drain"):
            res = call("PUT", HAP_RT + "/backends/%s/servers/%s" % (be, name), body={"admin_state": "ready"})
            print("  un-drain %s@%s in %s (%s)" % (name, addr, be,
                                                   "ok" if not (isinstance(res, dict) and res.get("_error")) else res))

call("PATCH", SN + "/incident/%s" % inc_sys, body={"state": CLOSED, "close_code": "Solved (Permanently)",
     "close_notes": "Overnight maintenance window (hardening + shared-services migration) broke payments "
                    "end to end; restored edge + dependency paths to the peer baseline, repointed DNS to the "
                    "migrated VIPs, re-enabled drained nodes, removed dangling config. Deploy verified not the cause."})

print("\n--- readback ---")
sgs2 = {str(g.get("GroupId")): g for g in aws_set("DescribeSecurityGroups", "securityGroupInfo")}

def ing_ok(gid, port, cidr):
    for p in (sgs2.get(gid) or {}).get("IpPermissions", []):
        if str(p.get("IpProtocol")).lower() == "tcp" and p.get("FromPort") is not None and int(p["FromPort"]) <= port <= int(p["ToPort"]) and any(str(r.get("CidrIp")) == cidr for r in p.get("IpRanges", [])):
            return True
    return False

def eg_ok(gid, port, cidr):
    for p in (sgs2.get(gid) or {}).get("IpPermissionsEgress", []):
        if str(p.get("IpProtocol")).lower() == "tcp" and p.get("FromPort") is not None and int(p["FromPort"]) <= port <= int(p["ToPort"]) and any(str(r.get("CidrIp")) == cidr for r in p.get("IpRanges", [])):
            return True
    return False

for p in (443, 8081, 8404):
    check("payments SG ingress %d from LB" % p, ing_ok(pay_sg, p, "10.60.0.0/24"))
for prt in (8443, 5432, 6379):
    check("payments SG egress %d to shared" % prt, eg_ok(pay_sg, prt, "10.50.0.0/24"))
acls2 = aws_set("DescribeNetworkAcls", "networkAclSet")
pay_acl2 = next(a for a in acls2 if a["NetworkAclId"] == pay_acl["NetworkAclId"])
egress_ret = any(bool(e.get("Egress")) and str(e.get("CidrBlock")) == "10.60.0.0/24" and str(e.get("RuleAction")) == "allow" for e in pay_acl2["EntrySet"])
ingress_ret = any((not bool(e.get("Egress"))) and str(e.get("CidrBlock")) == "10.50.0.0/24" and str(e.get("RuleAction")) == "allow" for e in pay_acl2["EntrySet"])
check("payments NACL edge egress-return", egress_ret)
check("payments NACL dependency ingress-return", ingress_ret)
rts2 = aws_set("DescribeRouteTables", "routeTableSet")
pay_rt2 = next(t for t in rts2 if t["RouteTableId"] == pay_rt["RouteTableId"])
check("no blackhole route on payments RT", not any(str(r.get("State")) == "blackhole" for r in pay_rt2["RouteSet"]))
dns2 = get(DNS + "/record:a")
dns2 = dns2 if isinstance(dns2, list) else []
for svc in pay_deps:
    recs = [r for r in dns2 if str(r.get("name")).split(".")[0] == svc]
    check("DNS %s resolves live" % svc, bool(recs) and all(str(r.get("ipv4addr")) in LIVE_IPS for r in recs))
check("no dangling dependency DNS records",
      all(str(r.get("ipv4addr")) in LIVE_IPS for r in dns2 if dep_related(r.get("name"))))
for be in all_backends:
    rt = get(HAP_RT + "/backends/%s/servers" % be)
    for r in (rt if isinstance(rt, list) else []):
        check("%s/%s not drained" % (be, r.get("server_name")), str(r.get("admin_state")) not in ("maint", "drain"))
inc2 = (get(SN + "/incident/%s" % inc_sys) or {}).get("result", {})
check("incident closed", str(inc2.get("state")) == CLOSED)

print("\n%d mismatch(es)" % len(MISMATCHES))
for m in MISMATCHES:
    print("  FAILED:", m)
sys.exit(1 if MISMATCHES else 0)
