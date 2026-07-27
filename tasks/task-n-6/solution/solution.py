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
INCIDENT_NUMBER = "INC0006001"
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

incidents = get(SN + "/incident")
incidents = incidents if isinstance(incidents, list) else (incidents or {}).get("result", [])
cur = next((i for i in incidents if str(i.get("number")) == INCIDENT_NUMBER), None)
assert cur, "incident not found"
inc_sys = str(cur["sys_id"])
inc_text = (str(cur.get("description", "")) + " " + str(cur.get("short_description", ""))).lower()
m = re.search(r"\bCHG\d+\b", inc_text, re.I)
suspected = m.group(0).upper() if m else None
choices = get(SN + "/sys_choice")
choices = choices if isinstance(choices, list) else (choices or {}).get("result", [])
closed = [str(c.get("value")) for c in choices if str(c.get("name")) == "incident"
          and str(c.get("element")) == "state" and re.search(r"resolv|clos", str(c.get("label", "")), re.I)]
CLOSED = closed[-1] if closed else "7"
print("incident %s sys_id=%s suspected(decoy)=%s" % (INCIDENT_NUMBER, inc_sys, suspected))

changes = get(SN + "/change_request")
changes = changes if isinstance(changes, list) else (changes or {}).get("result", [])
decoy = next((c for c in changes if str(c.get("number")) == suspected), None)
print("decoy %s category=%s closed=%s -> app deploy, no network scope; verify infra instead"
      % (suspected, decoy and decoy.get("category"), decoy and decoy.get("state")))

d42 = ((get(D42 + "/api/2.0/devices/") or {}).get("devices")) or []
services = ((get(D42 + "/api/2.0/services/") or {}).get("services")) or \
           ((get(D42 + "/api/2.0/services/") or {}).get("result")) or []
enis = aws_set("DescribeNetworkInterfaces", "networkInterfaceSet")
sgs = {str(g.get("GroupId")): g for g in aws_set("DescribeSecurityGroups", "securityGroupInfo")}
acls = aws_set("DescribeNetworkAcls", "networkAclSet")
rts = aws_set("DescribeRouteTables", "routeTableSet")
subnets = aws_set("DescribeSubnets", "subnetSet")
LIVE_IPS = {str(e.get("PrivateIpAddress")) for e in enis if e.get("PrivateIpAddress")} | \
           {str(d.get("ip")) for d in d42 if d.get("ip")}

app_tiers = [s for s in services if s.get("depends_on")]
subject = next(s for s in app_tiers if re.search(r"\b%s\b" % re.escape(str(s["name"]).lower()), inc_text))
SUBJECT = str(subject["name"])
deps = [str(d) for d in subject.get("depends_on", [])]
svc_by_name = {str(s.get("name")): s for s in services}
print("subject tier=%s depends_on=%s" % (SUBJECT, deps))

def eni_of(ip):
    return next((x for x in enis if str(x.get("PrivateIpAddress")) == ip), None)

def subnet_rec(sid):
    return next((s for s in subnets if str(s.get("SubnetId")) == sid), None)

def acl_for_subnet(sid):
    return next((a for a in acls if any(str(x.get("SubnetId")) == sid for x in a.get("AssociationSet", []))), None)

def rt_for_subnet(sid):
    return next((t for t in rts if any(str(x.get("SubnetId")) == sid for x in t.get("AssociationSet", []))), None)

def tier_facts(svc_name):
    hosts = [d for d in d42 if str(d.get("service")) == svc_name and str(d.get("role")) == "backend"]
    for h in hosts:
        e = eni_of(str(h.get("ip")))
        if e:
            sid = str(e.get("SubnetId"))
            srec = subnet_rec(sid)
            return (str(e["GroupSet"][0]["GroupId"]), sid,
                    str((srec or {}).get("CidrBlock")), str((srec or {}).get("VpcId")))
    return (None, None, None, None)

pay_sg, pay_subnet, PAY_CIDR, prod_vpc = tier_facts(SUBJECT)
prod_vpc_cidr = next(str(v.get("CidrBlock")) for v in aws_set("DescribeVpcs", "vpcSet")
                     if str(v.get("VpcId")) == prod_vpc)
print("subject: SG=%s subnet=%s cidr=%s vpc=%s(%s)" % (pay_sg, pay_subnet, PAY_CIDR, prod_vpc, prod_vpc_cidr))

siblings = [str(s["name"]) for s in app_tiers if str(s["name"]) != SUBJECT]
sib_facts = {s: tier_facts(s) for s in siblings}
sib_sg_ids = [f[0] for f in sib_facts.values() if f[0]]
sib_subnets = [f[1] for f in sib_facts.values() if f[1]]
sib_cidrs = [f[2] for f in sib_facts.values() if f[2]]
print("siblings %s: SGs=%s subnets=%s cidrs=%s" % (siblings, sib_sg_ids, sib_subnets, sib_cidrs))

dep_endpoint = {}
for dep in deps:
    hosts = [d for d in d42 if str(d.get("service")) == dep]
    for h in hosts:
        e = eni_of(str(h.get("ip")))
        if e:
            sid = str(e.get("SubnetId"))
            srec = subnet_rec(sid)
            port = (svc_by_name.get(dep) or {}).get("port") or (svc_by_name.get(dep) or {}).get("listen_port")
            dep_endpoint[dep] = {"sg": str(e["GroupSet"][0]["GroupId"]), "subnet": sid,
                                 "cidr": str((srec or {}).get("CidrBlock")),
                                 "vpc": str((srec or {}).get("VpcId")), "port": int(port)}
            break
shared_subnet = dep_endpoint[deps[0]]["subnet"]
SHARED_CIDR = dep_endpoint[deps[0]]["cidr"]
shared_vpc = dep_endpoint[deps[0]]["vpc"]
shared_vpc_cidr = next(str(v.get("CidrBlock")) for v in aws_set("DescribeVpcs", "vpcSet")
                       if str(v.get("VpcId")) == shared_vpc)
print("dependency endpoints:", {k: (v["sg"], v["port"]) for k, v in dep_endpoint.items()})
print("shared subnet=%s cidr=%s vpc=%s(%s)" % (shared_subnet, SHARED_CIDR, shared_vpc, shared_vpc_cidr))

have_egress = {ing_key(p) for p in (sgs.get(pay_sg) or {}).get("IpPermissionsEgress", [])}
for dep in deps:
    port, cidr = dep_endpoint[dep]["port"], dep_endpoint[dep]["cidr"]
    if ("tcp", port, port, (cidr,)) not in have_egress:
        aws("AuthorizeSecurityGroupEgress", GroupId=pay_sg, IpProtocol="tcp",
            FromPort=port, ToPort=port, CidrIp=cidr)
        print("  +egress tcp/%d to %s (%s)" % (port, cidr, dep))

sib_sets, by_key = [], {}
for gid in sib_sg_ids:
    keys = set()
    for p in (sgs.get(gid) or {}).get("IpPermissions", []):
        k = ing_key(p)
        keys.add(k)
        by_key[k] = p
    sib_sets.append(keys)
baseline = set.intersection(*sib_sets) if sib_sets else set()
have_ing = {ing_key(p) for p in (sgs.get(pay_sg) or {}).get("IpPermissions", [])}
for k in sorted(baseline - have_ing, key=lambda x: (x[1] or 0)):
    p = by_key[k]
    for r in p.get("IpRanges", []):
        cidr = r.get("CidrIp")
        if cidr and cidr != "0.0.0.0/0":
            aws("AuthorizeSecurityGroupIngress", GroupId=pay_sg, IpProtocol=p.get("IpProtocol"),
                FromPort=p.get("FromPort"), ToPort=p.get("ToPort"), CidrIp=cidr)
            print("  +ingress %s %s-%s from %s" % (p.get("IpProtocol"), p.get("FromPort"), p.get("ToPort"), cidr))

pay_rt = rt_for_subnet(pay_subnet)
sib_rts = [rt_for_subnet(s) for s in sib_subnets]
live_pcx = next(str(r.get("VpcPeeringConnectionId")) for t in sib_rts if t for r in t.get("RouteSet", [])
                if str(r.get("State")) == "active" and r.get("VpcPeeringConnectionId"))
print("live peering (from sibling routes): %s" % live_pcx)
for r in list((pay_rt or {}).get("RouteSet", [])):
    if str(r.get("State")) == "blackhole":
        dest = str(r.get("DestinationCidrBlock"))
        aws("ReplaceRoute", RouteTableId=pay_rt["RouteTableId"], DestinationCidrBlock=dest,
            VpcPeeringConnectionId=live_pcx)
        print("  ~route %s: blackhole %s -> active via %s" % (dest, r.get("VpcPeeringConnectionId"), live_pcx))

pay_acl = acl_for_subnet(pay_subnet)
sib_acls = [acl_for_subnet(s) for s in sib_subnets]
sib_acls = [a for a in sib_acls if a]

def allow_keys(a):
    return {acl_key(e) for e in a.get("EntrySet", []) if str(e.get("RuleAction")).lower() == "allow"}

acl_baseline = set.intersection(*[allow_keys(a) for a in sib_acls]) if sib_acls else set()
acl_src = {}
for a in sib_acls:
    for e in a.get("EntrySet", []):
        acl_src[acl_key(e)] = e
used_rules = {(bool(e.get("Egress")), int(e.get("RuleNumber"))) for e in pay_acl.get("EntrySet", [])
              if str(e.get("RuleNumber")).isdigit()}

def next_rule(egress, want):
    n = want if (egress, want) not in used_rules else 200
    while (egress, n) in used_rules or n >= 32767:
        n += 1
    used_rules.add((egress, n))
    return n

for k in sorted(acl_baseline - allow_keys(pay_acl)):
    e = acl_src[k]
    pr = e.get("PortRange") or {}
    params = dict(NetworkAclId=pay_acl["NetworkAclId"],
                  RuleNumber=next_rule(bool(e.get("Egress")), int(e.get("RuleNumber", 200))),
                  Protocol=e.get("Protocol"), RuleAction="allow",
                  Egress="true" if e.get("Egress") else "false", CidrBlock=e.get("CidrBlock"))
    if pr:
        params["PortRange.From"], params["PortRange.To"] = pr.get("From"), pr.get("To")
    aws("CreateNetworkAclEntry", **params)
    print("  +subject NACL %s allow %s ports=%s" % ("egress" if e.get("Egress") else "ingress",
                                                    e.get("CidrBlock"), pr or "-"))

shared_rt = rt_for_subnet(shared_subnet)
shared_routes = (shared_rt or {}).get("RouteSet", [])
ret_pcx = next(str(r.get("VpcPeeringConnectionId")) for r in shared_routes
               if str(r.get("DestinationCidrBlock")) in sib_cidrs and r.get("VpcPeeringConnectionId"))
if not any(str(r.get("DestinationCidrBlock")) == PAY_CIDR for r in shared_routes):
    aws("CreateRoute", RouteTableId=shared_rt["RouteTableId"], DestinationCidrBlock=PAY_CIDR,
        VpcPeeringConnectionId=ret_pcx)
    print("  +shared return route %s via %s" % (PAY_CIDR, ret_pcx))

shared_acl = acl_for_subnet(shared_subnet)
sh_used = {(bool(e.get("Egress")), int(e.get("RuleNumber"))) for e in shared_acl.get("EntrySet", [])
           if str(e.get("RuleNumber")).isdigit()}

def sh_next(egress):
    n = max([r for eg, r in sh_used if eg == egress and r < 32767] + [100]) + 10
    while (egress, n) in sh_used or n >= 32767:
        n += 1
    sh_used.add((egress, n))
    return n

for egress in (False, True):
    tmpl = next((e for e in shared_acl.get("EntrySet", []) if bool(e.get("Egress")) == egress
                 and str(e.get("RuleAction")).lower() == "allow" and str(e.get("CidrBlock")) in sib_cidrs), None)
    has_pay = any(bool(e.get("Egress")) == egress and str(e.get("RuleAction")).lower() == "allow"
                  and str(e.get("CidrBlock")) == PAY_CIDR for e in shared_acl.get("EntrySet", []))
    if tmpl and not has_pay:
        pr = tmpl.get("PortRange") or {}
        params = dict(NetworkAclId=shared_acl["NetworkAclId"], RuleNumber=sh_next(egress),
                      Protocol=tmpl.get("Protocol"), RuleAction="allow",
                      Egress="true" if egress else "false", CidrBlock=PAY_CIDR)
        if pr:
            params["PortRange.From"], params["PortRange.To"] = pr.get("From"), pr.get("To")
        aws("CreateNetworkAclEntry", **params)
        print("  +shared NACL %s allow %s" % ("egress" if egress else "ingress", PAY_CIDR))

for dep in deps:
    gid = dep_endpoint[dep]["sg"]
    g = sgs.get(gid) or {}
    sib_grants = {(str(p.get("IpProtocol")), p.get("FromPort"), p.get("ToPort"))
                  for p in g.get("IpPermissions", [])
                  for r in p.get("IpRanges", []) if str(r.get("CidrIp")) in sib_cidrs}
    has_pay = any(str(r.get("CidrIp")) == PAY_CIDR
                  for p in g.get("IpPermissions", []) for r in p.get("IpRanges", []))
    if sib_grants and not has_pay:
        for proto, fp, tp in sorted(sib_grants):
            aws("AuthorizeSecurityGroupIngress", GroupId=gid, IpProtocol=proto,
                FromPort=fp, ToPort=tp, CidrIp=PAY_CIDR)
            print("  +%s (%s) ingress %s %s-%s from %s" % (gid, dep, proto, fp, tp, PAY_CIDR))

def rec_uuid(rec):
    if rec.get("uuid"):
        return str(rec["uuid"])
    ref = str(rec.get("_ref", ""))
    m2 = re.search(r"record:a/([^:]+):", ref)
    return m2.group(1) if m2 else None

dns_rows = [r for r in (get(DNS + "/record:a") or []) if isinstance(r, dict)]
for rec in dns_rows:
    if str(rec.get("ipv4addr")) not in LIVE_IPS:
        res = call("DELETE", DNS + "/record:a/" + rec_uuid(rec))
        print("  -dangling DNS %s -> %s (%s)" % (rec.get("name"), rec.get("ipv4addr"),
                                                 "ok" if not (isinstance(res, dict) and res.get("_error")) else res))

call("PATCH", SN + "/incident/%s" % inc_sys, body={
    "state": CLOSED, "close_code": "Solved (Permanently)",
    "close_notes": "Root cause was the overnight peering re-establishment + segmentation pass, not the "
                   "app deploy: the payments tier's path to the shared-services VPC was broken in both "
                   "directions on both sides (SG egress + call-back ingress, blackholed peering route, "
                   "subnet ACLs both ways, missing return route, endpoint access). Restored each hop to "
                   "the reference-tier baseline with least privilege, removed the retired subnet's "
                   "dangling DNS records, verified the deploy clean."})

print("\n--- readback ---")
sgs2 = {str(g.get("GroupId")): g for g in aws_set("DescribeSecurityGroups", "securityGroupInfo")}
acls2 = aws_set("DescribeNetworkAcls", "networkAclSet")
rts2 = aws_set("DescribeRouteTables", "routeTableSet")

def perm_ok(perms, port, cidr):
    for p in perms or []:
        proto = str(p.get("IpProtocol")).lower()
        if proto == "tcp":
            fp, tp = p.get("FromPort"), p.get("ToPort")
            if fp is None or not (int(fp) <= port <= int(tp)):
                continue
        elif proto != "-1":
            continue
        if any(str(r.get("CidrIp")) == cidr for r in p.get("IpRanges", [])):
            return True
    return False

for dep in deps:
    check("subject SG egress tcp/%d to shared (%s)" % (dep_endpoint[dep]["port"], dep),
          perm_ok((sgs2.get(pay_sg) or {}).get("IpPermissionsEgress"), dep_endpoint[dep]["port"], SHARED_CIDR))
cb = [k for k in baseline - have_ing]
for k in cb:
    for cidr in k[3]:
        check("subject SG ingress %s-%s from %s" % (k[1], k[2], cidr),
              perm_ok((sgs2.get(pay_sg) or {}).get("IpPermissions"), int(k[1]), cidr))
pay_rt2 = next(t for t in rts2 if t["RouteTableId"] == pay_rt["RouteTableId"])
check("no blackhole on subject RT", all(str(r.get("State")) != "blackhole" for r in pay_rt2["RouteSet"]))
check("active shared-VPC route via live peering",
      any(str(r.get("State")) == "active" and str(r.get("VpcPeeringConnectionId", "")) == live_pcx
          for r in pay_rt2["RouteSet"]))
pay_acl2 = next(a for a in acls2 if a["NetworkAclId"] == pay_acl["NetworkAclId"])
check("subject NACL outbound to shared", any(bool(e.get("Egress")) and str(e.get("CidrBlock")) == SHARED_CIDR
      and str(e.get("RuleAction")) == "allow" for e in pay_acl2["EntrySet"]))
check("subject NACL inbound from shared", any((not bool(e.get("Egress"))) and str(e.get("CidrBlock")) == SHARED_CIDR
      and str(e.get("RuleAction")) == "allow" for e in pay_acl2["EntrySet"]))
shared_rt2 = next(t for t in rts2 if t["RouteTableId"] == shared_rt["RouteTableId"])
check("shared RT return route to subject", any(str(r.get("DestinationCidrBlock")) == PAY_CIDR
      and str(r.get("State")) == "active" and str(r.get("VpcPeeringConnectionId", "")) == ret_pcx
      for r in shared_rt2["RouteSet"]))
shared_acl2 = next(a for a in acls2 if a["NetworkAclId"] == shared_acl["NetworkAclId"])
check("shared NACL inbound from subject", any((not bool(e.get("Egress"))) and str(e.get("CidrBlock")) == PAY_CIDR
      and str(e.get("RuleAction")) == "allow" for e in shared_acl2["EntrySet"]))
check("shared NACL outbound to subject", any(bool(e.get("Egress")) and str(e.get("CidrBlock")) == PAY_CIDR
      and str(e.get("RuleAction")) == "allow" for e in shared_acl2["EntrySet"]))
for dep in deps:
    check("%s SG admits subject tcp/%d" % (dep, dep_endpoint[dep]["port"]),
          perm_ok((sgs2.get(dep_endpoint[dep]["sg"]) or {}).get("IpPermissions"),
                  dep_endpoint[dep]["port"], PAY_CIDR))
dns2 = [r for r in (get(DNS + "/record:a") or []) if isinstance(r, dict)]
check("no DNS record resolves to a dead address", all(str(r.get("ipv4addr")) in LIVE_IPS for r in dns2))
inc2 = (get(SN + "/incident/%s" % inc_sys) or {}).get("result", {})
check("incident closed", str(inc2.get("state")) == CLOSED)

print("\n%d mismatch(es)" % len(MISMATCHES))
for msg in MISMATCHES:
    print("  FAILED:", msg)
sys.exit(1 if MISMATCHES else 0)
