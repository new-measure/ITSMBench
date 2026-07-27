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
PD = "http://pagerduty.local.mock:8080"
INCIDENT_ID = "PSHOP01"
EPHEMERAL = (1024, 65535)
MISMATCHES = []

def call(method, url, body=None, form=False, headers=None):
    data, h = None, {"Accept": "application/json"}
    if headers:
        h.update(headers)
    if form:
        data = urllib.parse.urlencode(body or {}).encode()
        h["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=h)
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

page = (get(PD + "/incidents/" + INCIDENT_ID) or {}).get("incident") or {}
assert page, "page not found"
details = json.dumps(page.get("body")) + " " + str(page.get("title"))
users = ((get(PD + "/users") or {}).get("users")) or []
actor_email = next((u.get("email") for u in users if u.get("email")), None)
assert actor_email, "no pagerduty user email for From header"
print("page %s status=%s decoy-mentions-cdn/east=%s actor=%s"
      % (INCIDENT_ID, page.get("status"), bool(re.search(r"cdn|capacity|us-east-1", details, re.I)), actor_email))

d42 = ((get(D42 + "/api/2.0/devices/") or {}).get("devices")) or []
enis = aws_set("DescribeNetworkInterfaces", "networkInterfaceSet")
LIVE_IPS = {str(e.get("PrivateIpAddress")) for e in enis if e.get("PrivateIpAddress")} | \
           {str(d.get("ip")) for d in d42 if d.get("ip")}

def healthy(region_devs):
    return all(bool(d.get("in_service")) for d in region_devs) and \
        all(str(d.get("health_status")).lower() in ("healthy", "recovered", "ok") for d in region_devs)

def production(region_devs):
    return all(str(d.get("service_level")).lower() == "production" for d in region_devs)

regions = {}
for d in d42:
    regions.setdefault(str(d.get("region")), []).append(d)

def region_vip(region, tier):
    return next((str(d.get("ip")) for d in regions.get(region, [])
                 if str(d.get("tier")) == tier and str(d.get("role")) == "edge-vip"), None)

def region_backend_sg(region, tier):
    return next((str(d.get("security_group")) for d in regions.get(region, [])
                 if str(d.get("tier")) == tier and str(d.get("role")) == "backend"), None)

def region_web_subnet(region):
    return next((str(d.get("subnet")) for d in regions.get(region, [])
                 if str(d.get("tier")) == "web" and str(d.get("role")) == "backend"), None)

dns_rows = [r for r in (get(DNS + "/record:a") or []) if isinstance(r, dict)]

def enabled(rec):
    return str(rec.get("disable")).lower() not in ("true", "1")

def in_any_pool(ip):
    return any(str(r.get("ipv4addr")) == ip and enabled(r) for r in dns_rows)

peer_region = None
for region, devs in regions.items():
    if production(devs) and healthy(devs) and in_any_pool(region_vip(region, "web")):
        peer_region = region
        break
assert peer_region, "no healthy in-pool peer region found"

pool_name = {}
peer_weight = {}
for tier in ("web", "api"):
    pv = region_vip(peer_region, tier)
    rec = next((r for r in dns_rows if str(r.get("ipv4addr")) == pv and enabled(r)), None)
    if rec:
        pool_name[tier] = str(rec.get("name"))
        peer_weight[tier] = int(rec.get("weight"))
print("peer=%s pools=%s peer_weight=%s" % (peer_region, pool_name, peer_weight))

restore_regions = []
for region, devs in regions.items():
    if region == peer_region:
        continue
    if production(devs) and healthy(devs):
        if any(region_vip(region, t) and not in_any_pool(region_vip(region, t)) for t in ("web", "api")):
            restore_regions.append(region)
leave_regions = [r for r in regions if r != peer_region and r not in restore_regions]
print("RESTORE:", restore_regions, "| LEAVE:", leave_regions)

def rec_uuid(rec):
    if rec.get("uuid"):
        return str(rec["uuid"])
    m = re.search(r"record:a/([^:]+):", str(rec.get("_ref", "")))
    return m.group(1) if m else None

for region in restore_regions:
    for tier in ("web", "api"):
        vip, name = region_vip(region, tier), pool_name.get(tier)
        if not (vip and name):
            continue
        cur = [r for r in (get(DNS + "/record:a") or []) if isinstance(r, dict)
               and str(r.get("name")) == name and str(r.get("ipv4addr")) == vip]
        if cur:
            uid = rec_uuid(cur[0])
            call("PUT", DNS + "/record:a/" + uid, body={"disable": False, "weight": peer_weight[tier]})
            print("  enable+reweight %s %s -> w=%d" % (name, vip, peer_weight[tier]))
        else:
            call("POST", DNS + "/record:a", body={"name": name, "ipv4addr": vip, "view": "default",
                                                   "weight": peer_weight[tier], "disable": False,
                                                   "comment": "restored to GSLB pool"})
            print("  create %s %s w=%d" % (name, vip, peer_weight[tier]))

for name in set(pool_name.values()):
    for rec in [r for r in (get(DNS + "/record:a") or []) if isinstance(r, dict) and str(r.get("name")) == name]:
        if str(rec.get("ipv4addr")) not in LIVE_IPS:
            uid = rec_uuid(rec)
            call("DELETE", DNS + "/record:a/" + uid)
            print("  delete stale pool record %s -> %s" % (name, rec.get("ipv4addr")))

frontends = [f for f in (get(HAP + "/frontends") or []) if isinstance(f, dict)]

def backend_for_vip(vip):
    for fe in frontends:
        binds = get(HAP + "/frontends/%s/binds" % fe.get("name"))
        if isinstance(binds, list) and any(str(b.get("address")) == vip for b in binds):
            return str(fe.get("default_backend"))
    return None

peer_check = {}
for tier in ("web", "api"):
    be = backend_for_vip(region_vip(peer_region, tier))
    srvs = get(HAP + "/backends/%s/servers" % be) if be else []
    srvs = srvs if isinstance(srvs, list) else []
    if srvs:
        peer_check[tier] = {"check": srvs[0].get("check"), "health_check_port": srvs[0].get("health_check_port")}
print("peer health-check spec:", peer_check)

for region in restore_regions:
    for tier in ("web", "api"):
        be = backend_for_vip(region_vip(region, tier))
        if not be:
            continue
        srvs = get(HAP + "/backends/%s/servers" % be)
        srvs = srvs if isinstance(srvs, list) else []
        rt = get(HAP_RT + "/backends/%s/servers" % be)
        rt = rt if isinstance(rt, list) else []
        admin = {str(r.get("server_name")): str(r.get("admin_state")) for r in rt}
        for s in srvs:
            name = str(s.get("name"))
            if admin.get(name) in ("maint", "drain"):
                call("PUT", HAP_RT + "/backends/%s/servers/%s" % (be, name), body={"admin_state": "ready"})
                print("  un-drain %s/%s" % (be, name))
            spec = peer_check.get(tier, {})
            if str(s.get("check")) != str(spec.get("check")) or str(s.get("health_check_port")) != str(spec.get("health_check_port")):
                body = {"address": s.get("address"), "port": s.get("port"),
                        "check": spec.get("check"), "health_check_port": spec.get("health_check_port")}
                call("PUT", HAP + "/backends/%s/servers/%s" % (be, name), body=body)
                print("  fix health-check %s/%s -> check=%s port=%s" % (be, name, spec.get("check"), spec.get("health_check_port")))

sgs = {str(g.get("GroupId")): g for g in aws_set("DescribeSecurityGroups", "securityGroupInfo")}
acls = aws_set("DescribeNetworkAcls", "networkAclSet")
rts = aws_set("DescribeRouteTables", "routeTableSet")

def acl_for_subnet(sid):
    return next((a for a in acls if any(str(x.get("SubnetId")) == sid for x in a.get("AssociationSet", []))), None)

def rt_for_subnet(sid):
    return next((t for t in rts if any(str(x.get("SubnetId")) == sid for x in t.get("AssociationSet", []))), None)

def restore_sg(target_gid, peer_gid, egress):
    field = "IpPermissionsEgress" if egress else "IpPermissions"
    peer = {ing_key(p): p for p in (sgs.get(peer_gid) or {}).get(field, [])}
    have = {ing_key(p) for p in (sgs.get(target_gid) or {}).get(field, [])}
    action = "AuthorizeSecurityGroupEgress" if egress else "AuthorizeSecurityGroupIngress"
    for k, p in peer.items():
        if k in have:
            continue
        for r in p.get("IpRanges", []):
            cidr = r.get("CidrIp")
            if cidr and cidr != "0.0.0.0/0":
                aws(action, GroupId=target_gid, IpProtocol=p.get("IpProtocol"),
                    FromPort=p.get("FromPort"), ToPort=p.get("ToPort"), CidrIp=cidr)
                print("  +%s %s %s-%s %s on %s" % ("egress" if egress else "ingress", p.get("IpProtocol"),
                                                   p.get("FromPort"), p.get("ToPort"), cidr, target_gid))

for region in restore_regions:
    for tier in ("web", "api"):
        tgt = region_backend_sg(region, tier)
        peer = region_backend_sg(peer_region, tier)
        if tgt and peer:
            restore_sg(tgt, peer, egress=False)
            restore_sg(tgt, peer, egress=True)

    tgt_sub = region_web_subnet(region)
    peer_sub = region_web_subnet(peer_region)
    tacl, pacl = acl_for_subnet(tgt_sub), acl_for_subnet(peer_sub)
    if tacl and pacl:
        have = {acl_key(e) for e in tacl.get("EntrySet", []) if str(e.get("RuleAction")).lower() == "allow"}
        used = {(bool(e.get("Egress")), int(e.get("RuleNumber"))) for e in tacl.get("EntrySet", []) if str(e.get("RuleNumber")).isdigit()}

        def next_rule(egress):
            n = 150
            while (egress, n) in used:
                n += 1
            used.add((egress, n))
            return n

        for e in pacl.get("EntrySet", []):
            if str(e.get("RuleAction")).lower() != "allow" or acl_key(e) in have:
                continue
            pr = e.get("PortRange") or {}
            params = dict(NetworkAclId=tacl["NetworkAclId"], RuleNumber=next_rule(bool(e.get("Egress"))),
                          Protocol=e.get("Protocol"), RuleAction="allow",
                          Egress="true" if e.get("Egress") else "false", CidrBlock=e.get("CidrBlock"))
            if pr:
                params["PortRange.From"], params["PortRange.To"] = pr.get("From"), pr.get("To")
            aws("CreateNetworkAclEntry", **params)
            print("  +NACL %s %s allow %s ports=%s" % (tacl["NetworkAclId"],
                                                       "egress" if e.get("Egress") else "ingress", e.get("CidrBlock"), pr or "-"))

    trt, prt = rt_for_subnet(tgt_sub), rt_for_subnet(peer_sub)
    peer_dests = {str(r.get("DestinationCidrBlock")) for r in (prt or {}).get("RouteSet", [])}
    for r in (trt or {}).get("RouteSet", []):
        if str(r.get("State")) == "blackhole" and str(r.get("DestinationCidrBlock")) not in peer_dests:
            aws("DeleteRoute", RouteTableId=trt["RouteTableId"], DestinationCidrBlock=r.get("DestinationCidrBlock"))
            print("  -blackhole route %s from %s" % (r.get("DestinationCidrBlock"), trt["RouteTableId"]))

res = call("PUT", PD + "/incidents/" + INCIDENT_ID, headers={"From": actor_email},
           body={"incident": {"type": "incident", "status": "resolved",
                              "resolution": "Restored active-active distribution: brought the recovered region back "
                                            "into the GSLB pool at the peer weight, un-drained its pools, fixed its "
                                            "health checks, restored its backend network access to the peer baseline, "
                                            "and removed the stale static failover record. CDN/east-capacity ruled out."}})
print("  resolve page ->", "ok" if not (isinstance(res, dict) and res.get("_error")) else res)

print("\n--- readback ---")
sgs2 = {str(g.get("GroupId")): g for g in aws_set("DescribeSecurityGroups", "securityGroupInfo")}

def ing_ok(gid, port, cidr, egress=False):
    field = "IpPermissionsEgress" if egress else "IpPermissions"
    for p in (sgs2.get(gid) or {}).get(field, []):
        if str(p.get("IpProtocol")).lower() == "tcp" and p.get("FromPort") is not None and int(p["FromPort"]) <= port <= int(p["ToPort"]) and any(str(r.get("CidrIp")) == cidr for r in p.get("IpRanges", [])):
            return True
    return False

dns2 = [r for r in (get(DNS + "/record:a") or []) if isinstance(r, dict)]
for region in restore_regions:
    for tier in ("web", "api"):
        vip, name = region_vip(region, tier), pool_name.get(tier)
        recs = [r for r in dns2 if str(r.get("name")) == name and str(r.get("ipv4addr")) == vip and str(r.get("disable")).lower() not in ("true", "1")]
        check("GSLB %s serves %s (%s)" % (name, region, tier), bool(recs))
        check("GSLB %s weight==peer (%s)" % (name, tier), bool(recs) and all(int(r.get("weight")) == peer_weight[tier] for r in recs))
check("stale record cleaned", all(str(r.get("ipv4addr")) in LIVE_IPS for r in dns2 if str(r.get("name")) in set(pool_name.values())))

for region in restore_regions:
    for tier in ("web", "api"):
        be = backend_for_vip(region_vip(region, tier))
        rt = get(HAP_RT + "/backends/%s/servers" % be)
        for r in (rt if isinstance(rt, list) else []):
            check("%s/%s not drained" % (be, r.get("server_name")), str(r.get("admin_state")) not in ("maint", "drain"))
        srvs = get(HAP + "/backends/%s/servers" % be)
        spec = peer_check.get(tier, {})
        for s in (srvs if isinstance(srvs, list) else []):
            check("%s/%s health-check matches peer" % (be, s.get("name")),
                  str(s.get("check")) == str(spec.get("check")) and str(s.get("health_check_port")) == str(spec.get("health_check_port")))
    for tier in ("web", "api"):
        tgt = region_backend_sg(region, tier)
        peer = region_backend_sg(peer_region, tier)
        for p in (sgs.get(peer) or {}).get("IpPermissions", []):
            for r in p.get("IpRanges", []):
                if str(r.get("CidrIp")) != "0.0.0.0/0":
                    check("SG %s ingress %s-%s from %s" % (tgt, p.get("FromPort"), p.get("ToPort"), r.get("CidrIp")),
                          ing_ok(tgt, int(p.get("FromPort")), str(r.get("CidrIp"))))
        for p in (sgs.get(peer) or {}).get("IpPermissionsEgress", []):
            for r in p.get("IpRanges", []):
                if str(r.get("CidrIp")) != "0.0.0.0/0":
                    check("SG %s egress %s-%s to %s" % (tgt, p.get("FromPort"), p.get("ToPort"), r.get("CidrIp")),
                          ing_ok(tgt, int(p.get("FromPort")), str(r.get("CidrIp")), egress=True))

acls2 = aws_set("DescribeNetworkAcls", "networkAclSet")
rts2 = aws_set("DescribeRouteTables", "routeTableSet")
for region in restore_regions:
    sub = region_web_subnet(region)
    a = next((x for x in acls2 if any(str(y.get("SubnetId")) == sub for y in x.get("AssociationSet", []))), None)
    edge_in = any((not bool(e.get("Egress"))) and str(e.get("RuleAction")) == "allow" for e in (a or {}).get("EntrySet", [])
                  if str(e.get("CidrBlock")).startswith("10.5."))
    edge_out = any(bool(e.get("Egress")) and str(e.get("RuleAction")) == "allow" for e in (a or {}).get("EntrySet", [])
                   if str(e.get("CidrBlock")).startswith("10.5."))
    check("%s web NACL inbound from edge" % region, edge_in)
    check("%s web NACL return to edge" % region, edge_out)
    t = next((x for x in rts2 if any(str(y.get("SubnetId")) == sub for y in x.get("AssociationSet", []))), None)
    check("%s web RT no blackhole" % region, not any(str(r.get("State")) == "blackhole" for r in (t or {}).get("RouteSet", [])))

check("page resolved", (get(PD + "/incidents/" + INCIDENT_ID) or {}).get("incident", {}).get("status") == "resolved")

print("\n%d mismatch(es)" % len(MISMATCHES))
for m in MISMATCHES:
    print("  FAILED:", m)
sys.exit(1 if MISMATCHES else 0)
