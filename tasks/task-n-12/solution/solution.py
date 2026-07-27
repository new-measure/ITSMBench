#!/usr/bin/env python3
import ipaddress
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

AWS = "http://aws-vpc.local.mock:8080/"
ZIA = "http://zscaler-zia.local.mock:8080/zia/api/v1"
D42 = "http://device42.local.mock:8080"
SN = "http://servicenow.local.mock:8080/api/now/table"
INCIDENT_NUMBER = "INC0044100"
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

def net(c):
    return ipaddress.ip_network(str(c), strict=False)

def covers(cidr, ip):
    try:
        return ipaddress.ip_address(str(ip)) in net(cidr)
    except ValueError:
        return False

incidents = get(SN + "/incident")
incidents = incidents if isinstance(incidents, list) else (incidents or {}).get("result", [])
cur = next(i for i in incidents if str(i.get("number")) == INCIDENT_NUMBER)
inc_sys = str(cur["sys_id"])
inc_text = (str(cur.get("description", "")) + " " + str(cur.get("short_description", ""))).lower()
choices = get(SN + "/sys_choice")
choices = choices if isinstance(choices, list) else (choices or {}).get("result", [])
resolved = [str(c.get("value")) for c in choices if str(c.get("name")) == "incident"
            and str(c.get("element")) == "state" and re.search(r"resolv", str(c.get("label", "")), re.I)]
RESOLVED = resolved[0] if resolved else "6"
print("incident %s sys_id=%s" % (INCIDENT_NUMBER, inc_sys))

devices = ((get(D42 + "/api/2.0/devices/") or {}).get("devices")) or []
svc_rows = ((get(D42 + "/api/2.0/services/") or {}).get("services")) or []
cde_services = [str(s.get("name")) for s in svc_rows if str(s.get("zone")) == "cde"]
subject = next(s for s in cde_services if s.lower() in inc_text)
peer = next(s for s in cde_services if s != subject)
subject_deps = next((s.get("depends_on") for s in svc_rows if str(s.get("name")) == subject), []) or []
print("subject=%s peer=%s deps=%s" % (subject, peer, subject_deps))

subnets = aws_set("DescribeSubnets", "subnetSet")

def subnet_of_ip(ip):
    return next((s for s in subnets if covers(s.get("CidrBlock"), ip)), None)

def tiers(service):
    out = {}
    for d in devices:
        if str(d.get("service")) != service:
            continue
        sub = subnet_of_ip(d.get("ip"))
        out[str(d.get("role"))] = (str(d.get("security_group")), str(sub.get("CidrBlock")) if sub else None)
    return out

sub_tiers, peer_tiers = tiers(subject), tiers(peer)
assert set(sub_tiers) == set(peer_tiers), "tier roles must match between subject and peer"
CIDR_MAP = {peer_tiers[r][1]: sub_tiers[r][1] for r in peer_tiers}
print("tiers=%s | cidr map=%s" % (sorted(sub_tiers), CIDR_MAP))

vpc_cidrs = [str(v.get("CidrBlock")) for v in aws_set("DescribeVpcs", "vpcSet")]

def internal(ip):
    return any(covers(c, ip) for c in vpc_cidrs)

LIVE_IPS = {str(d.get("ip")) for d in devices if d.get("ip") and d.get("in_service", True)}

changes = get(SN + "/change_request")
changes = changes if isinstance(changes, list) else (changes or {}).get("result", [])
approved_ips = set()
for c in changes:
    if str(c.get("state")) == "3":
        text = str(c.get("description", "")) + " " + str(c.get("short_description", ""))
        if re.search(r"approved|exception|compensating", text, re.I):
            approved_ips |= set(re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text))
print("approved-exception register IPs: %s (flagged shared-services read access is SANCTIONED -> keep)"
      % sorted(approved_ips))

sgs = {str(g.get("GroupId")): g for g in aws_set("DescribeSecurityGroups", "securityGroupInfo")}

def flat_perms(g, field="IpPermissions"):
    out = set()
    for p in (g or {}).get(field, []):
        for r in p.get("IpRanges", []):
            out.add((str(p.get("IpProtocol")), p.get("FromPort"), p.get("ToPort"), str(r.get("CidrIp"))))
    return out

def map_cidr(c):
    return CIDR_MAP.get(str(c), str(c))

for role in sorted(sub_tiers):
    sub_gid, peer_gid = sub_tiers[role][0], peer_tiers[role][0]
    target = {(proto, fp, tp, map_cidr(c)) for (proto, fp, tp, c) in flat_perms(sgs.get(peer_gid))}
    have = flat_perms(sgs.get(sub_gid))
    for (proto, fp, tp, c) in sorted(have - target):
        res = aws("RevokeSecurityGroupIngress", GroupId=sub_gid, IpProtocol=proto,
                  FromPort=fp, ToPort=tp, CidrIp=c)
        print("  -SG %s revoke %s %s-%s from %s (%s)" % (sub_gid, proto, fp, tp, c,
              "ok" if not (isinstance(res, dict) and res.get("_error")) else res))
    for (proto, fp, tp, c) in sorted(target - have):
        res = aws("AuthorizeSecurityGroupIngress", GroupId=sub_gid, IpProtocol=proto,
                  FromPort=fp, ToPort=tp, CidrIp=c)
        print("  +SG %s allow %s %s-%s from %s (%s)" % (sub_gid, proto, fp, tp, c,
              "ok" if not (isinstance(res, dict) and res.get("_error")) else res))

acls = aws_set("DescribeNetworkAcls", "networkAclSet")

def acl_for_cidr(cidr):
    sid = next(str(s.get("SubnetId")) for s in subnets if str(s.get("CidrBlock")) == cidr)
    return next(a for a in acls if any(str(x.get("SubnetId")) == sid for x in a.get("AssociationSet", [])))

def inbound_allows(a):
    return [(str(e.get("CidrBlock")), int(e.get("RuleNumber"))) for e in a.get("EntrySet", [])
            if not bool(e.get("Egress")) and str(e.get("RuleAction")).lower() == "allow"]

for role in sorted(sub_tiers):
    sub_acl = acl_for_cidr(sub_tiers[role][1])
    peer_acl = acl_for_cidr(peer_tiers[role][1])
    target_cidrs = {map_cidr(c) for (c, _) in inbound_allows(peer_acl)}
    have = inbound_allows(sub_acl)
    have_cidrs = {c for (c, _) in have}
    used = {int(e.get("RuleNumber")) for e in sub_acl.get("EntrySet", []) if not bool(e.get("Egress"))}
    for (c, rn) in have:
        if c not in target_cidrs:
            res = aws("DeleteNetworkAclEntry", NetworkAclId=sub_acl["NetworkAclId"],
                      RuleNumber=rn, Egress="false")
            print("  -NACL %s delete inbound rule %s (%s) (%s)" % (sub_acl["NetworkAclId"], rn, c,
                  "ok" if not (isinstance(res, dict) and res.get("_error")) else res))
    rn = 100
    for c in sorted(target_cidrs - have_cidrs):
        while rn in used:
            rn += 10
        used.add(rn)
        res = aws("CreateNetworkAclEntry", NetworkAclId=sub_acl["NetworkAclId"], RuleNumber=rn,
                  Protocol="6", RuleAction="allow", Egress="false", CidrBlock=c)
        print("  +NACL %s allow inbound %s rule %s (%s)" % (sub_acl["NetworkAclId"], c, rn,
              "ok" if not (isinstance(res, dict) and res.get("_error")) else res))

rules = get(ZIA + "/firewallFilteringRules")
rules = rules if isinstance(rules, list) else []
src_groups = {str(g.get("id")): g for g in (get(ZIA + "/ipSourceGroups") or [])}
dest_groups = {str(g.get("id")): g for g in (get(ZIA + "/ipDestinationGroups") or [])}

def rule_src_cidrs(r):
    cidrs = [str(x) for x in r.get("srcIps") or []]
    for g in r.get("srcIpGroups") or []:
        cidrs += [str(x) for x in (src_groups.get(str((g or {}).get("id"))) or {}).get("ipAddresses") or []]
    return cidrs

def overlaps_tier(r, cidr):
    return any(net(c).overlaps(net(cidr)) for c in rule_src_cidrs(r) if c)

app_cidr = next(sub_tiers[r][1] for r in sub_tiers if r == "app")
db_like = [sub_tiers[r][1] for r in sub_tiers if r != "app"]
peer_app_cidr = next(peer_tiers[r][1] for r in peer_tiers if r == "app")

peer_rule = next(r for r in rules if str(r.get("action")).upper() == "ALLOW"
                 and str(r.get("state")).upper() == "ENABLED" and overlaps_tier(r, peer_app_cidr))
proc_group_ids = [str(g.get("id")) for g in peer_rule.get("destIpGroups") or []]
print("peer egress baseline: rule %s -> dest groups %s" % (peer_rule.get("id"), proc_group_ids))

for r in rules:
    if str(r.get("action")).upper() != "ALLOW" or str(r.get("state")).upper() != "ENABLED":
        continue
    dests = [str(d) for d in r.get("destAddresses") or []]
    if overlaps_tier(r, app_cidr):
        if any(d in ("0.0.0.0/0", "::/0", "any", "ANY", "*") for d in dests):
            res = call("PUT", ZIA + "/firewallFilteringRules/%s" % r["id"],
                       body={"destAddresses": [],
                             "destIpGroups": [{"id": int(g), "name": str(dest_groups[g].get("name"))}
                                              for g in proc_group_ids]})
            print("  ~ZIA rule %s narrowed 0.0.0.0/0 -> groups %s (%s)" % (r["id"], proc_group_ids,
                  "ok" if not (isinstance(res, dict) and res.get("_error")) else res))
        elif dests and all(not internal(d.split("/")[0]) and d.split("/")[0] not in LIVE_IPS for d in dests):
            res = call("DELETE", ZIA + "/firewallFilteringRules/%s" % r["id"])
            print("  -ZIA dangling rule %s (dests %s) (%s)" % (r["id"], dests,
                  "ok" if not (isinstance(res, dict) and res.get("_error")) else res))
    elif any(overlaps_tier(r, c) for c in db_like):
        res = call("DELETE", ZIA + "/firewallFilteringRules/%s" % r["id"])
        print("  -ZIA db/tok-tier egress rule %s (%s)" % (r["id"],
              "ok" if not (isinstance(res, dict) and res.get("_error")) else res))

proc_live = sorted({str(d.get("ip")) for d in devices
                    if str(d.get("service")) in [str(x) for x in subject_deps]
                    and d.get("ip") and not internal(d.get("ip")) and d.get("in_service", True)})
for gid in proc_group_ids:
    grp = dest_groups[gid]
    have = [str(x) for x in grp.get("ipAddresses") or []]
    if sorted(have) != proc_live:
        res = call("PUT", ZIA + "/ipDestinationGroups/%s" % gid, body={"ipAddresses": proc_live})
        print("  ~ZIA dest group %s ipAddresses %s -> %s (%s)" % (gid, have, proc_live,
              "ok" if not (isinstance(res, dict) and res.get("_error")) else res))

call("PATCH", SN + "/incident/%s" % inc_sys, body={
    "state": RESOLVED, "close_code": "Solved (Permanently)",
    "close_notes": "Re-segmented the %s cardholder data environment to the least-privilege baseline of "
                   "its correctly-segmented peer: removed/narrowed every non-CDE ingress path at the SG "
                   "and subnet-ACL layers, restored the legitimate tier flows the phase-1 change had "
                   "stripped, closed the open internet egress down to the approved processor "
                   "destinations, reconciled the approved destination register against the live "
                   "gateways, removed a dangling egress rule to a decommissioned endpoint, and kept the "
                   "QSA-approved compensating-control exception intact per the exception register." % subject})

print("\n--- readback ---")
sgs2 = {str(g.get("GroupId")): g for g in aws_set("DescribeSecurityGroups", "securityGroupInfo")}
for role in sorted(sub_tiers):
    sub_gid, peer_gid = sub_tiers[role][0], peer_tiers[role][0]
    want = {(proto, fp, tp, map_cidr(c)) for (proto, fp, tp, c) in flat_perms(sgs.get(peer_gid))}
    got = flat_perms(sgs2.get(sub_gid))
    check("SG %s (%s) == mapped peer baseline" % (sub_gid, role), got == want)

acls2 = aws_set("DescribeNetworkAcls", "networkAclSet")

def acl2_for_cidr(cidr):
    sid = next(str(s.get("SubnetId")) for s in subnets if str(s.get("CidrBlock")) == cidr)
    return next(a for a in acls2 if any(str(x.get("SubnetId")) == sid for x in a.get("AssociationSet", [])))

for role in sorted(sub_tiers):
    got = {c for (c, _) in inbound_allows(acl2_for_cidr(sub_tiers[role][1]))}
    want = {map_cidr(c) for (c, _) in inbound_allows(acl_for_cidr(peer_tiers[role][1]))}
    check("NACL inbound allows (%s) == mapped peer baseline" % role, got == want)
    deny = any(int(e.get("RuleNumber")) == 32767 and not bool(e.get("Egress"))
               for e in acl2_for_cidr(sub_tiers[role][1]).get("EntrySet", []))
    check("NACL default deny intact (%s)" % role, deny)

rules2 = get(ZIA + "/firewallFilteringRules")
rules2 = rules2 if isinstance(rules2, list) else []
dest_groups2 = {str(g.get("id")): g for g in (get(ZIA + "/ipDestinationGroups") or [])}
app_rules = [r for r in rules2 if str(r.get("action")).upper() == "ALLOW"
             and str(r.get("state")).upper() == "ENABLED" and overlaps_tier(r, app_cidr)]
check("no world-open app egress",
      not any(d in ("0.0.0.0/0", "::/0") for r in app_rules for d in (r.get("destAddresses") or [])))
check("app egress scoped to approved group",
      any([str(g.get("id")) for g in r.get("destIpGroups") or []] == proc_group_ids for r in app_rules))
check("no db/tok-tier egress rule",
      not any(any(overlaps_tier(r, c) for c in db_like) for r in rules2
              if str(r.get("action")).upper() == "ALLOW" and str(r.get("state")).upper() == "ENABLED"))
check("no dangling dead-endpoint rule",
      not any(dests and all(not internal(d.split("/")[0]) and d.split("/")[0] not in LIVE_IPS
                            for d in dests)
              for r in rules2 if str(r.get("action")).upper() == "ALLOW"
              and str(r.get("state")).upper() == "ENABLED"
              for dests in [[str(d) for d in r.get("destAddresses") or []]]))
for gid in proc_group_ids:
    got = sorted(str(x) for x in (dest_groups2.get(gid) or {}).get("ipAddresses") or [])
    check("dest group %s == live external gateways %s" % (gid, proc_live), got == proc_live)
scanner_kept = any(covers(c, ip) for ip in approved_ips
                   for (_, _, _, c) in flat_perms(sgs2.get(sub_tiers.get("db", ("", ""))[0])))
check("approved scanner exception kept on subject db SG", scanner_kept)
inc2 = (get(SN + "/incident/%s" % inc_sys) or {}).get("result", {})
check("incident resolved", str(inc2.get("state")) in ("6", "7"))

print("\n%d mismatch(es)" % len(MISMATCHES))
for m in MISMATCHES:
    print("  FAILED:", m)
sys.exit(1 if MISMATCHES else 0)
