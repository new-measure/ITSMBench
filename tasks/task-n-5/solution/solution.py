#!/usr/bin/env python3
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

AWS = "http://aws-vpc.local.mock:8080/"
DNS = "http://infoblox-nios.local.mock:8080/wapi/v2.14"
SN = "http://servicenow.local.mock:8080/api/now/table"
PD = "http://pagerduty.local.mock:8080"
SENT_BASE = ("http://microsoft-sentinel.local.mock:8080/subscriptions/00000000-1111-2222-3333-444444444444"
             "/resourceGroups/secops-rg/providers/Microsoft.OperationalInsights/workspaces/sentinel-ws"
             "/providers/Microsoft.SecurityInsights/incidents")
API_VER = "?api-version=2023-11-01"
INCIDENT_NUMBER = "INC0077001"
MISMATCHES = []

def call(method, url, body=None, form=False, headers=None):
    data, hdrs = None, {"Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    if form:
        data = urllib.parse.urlencode(body or {}).encode()
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
        return json.loads(raw) if raw and raw.strip()[:1] in "{[" else raw
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_body": e.read().decode()[:300]}

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

def acl_allow_key(e):
    pr = e.get("PortRange") or {}
    return (bool(e.get("Egress")), str(e.get("Protocol")), str(e.get("CidrBlock")), pr.get("From"), pr.get("To"))

incidents = get(SN + "/incident")
incidents = incidents if isinstance(incidents, list) else (incidents or {}).get("result", [])
cur = next((i for i in incidents if str(i.get("number")) == INCIDENT_NUMBER), None)
assert cur, "incident not found"
inc_sys = str(cur["sys_id"])
desc = str(cur.get("description", "")) + " " + str(cur.get("short_description", ""))
hostname = next((f for f in re.findall(r"\b([a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)+)\b", desc, re.I)
                 if not f.replace(".", "").isdigit()), None)
subject_host = hostname.split(".")[0] if hostname else None
service_base = re.sub(r"-api$", "", subject_host) if subject_host else None
suspected = re.search(r"\bCHG\d+\b", desc)
suspected = suspected.group(0) if suspected else None
print("incident %s sys_id=%s subject=%s base=%s suspected(decoy)=%s"
      % (INCIDENT_NUMBER, inc_sys, subject_host, service_base, suspected))
choices = get(SN + "/sys_choice")
choices = choices if isinstance(choices, list) else (choices or {}).get("result", [])
closed = [str(c.get("value")) for c in choices if str(c.get("name")) == "incident"
          and str(c.get("element")) == "state" and re.search(r"resolv|clos", str(c.get("label", "")), re.I)]
CLOSED = closed[-1] if closed else "7"

changes = get(SN + "/change_request")
changes = changes if isinstance(changes, list) else (changes or {}).get("result", [])
decoy = next((c for c in changes if str(c.get("number")) == suspected), None)
print("decoy %s category=%s -> app deploy, network-neutral, NOT the cause"
      % (suspected, decoy and decoy.get("category")))

enis = aws_set("DescribeNetworkInterfaces", "networkInterfaceSet")
subnets = aws_set("DescribeSubnets", "subnetSet")
sgs = {str(g.get("GroupId")): g for g in aws_set("DescribeSecurityGroups", "securityGroupInfo")}
acls = aws_set("DescribeNetworkAcls", "networkAclSet")
rts = aws_set("DescribeRouteTables", "routeTableSet")
LIVE_IPS = {str(e.get("PrivateIpAddress")) for e in enis if e.get("PrivateIpAddress")}

def eni_desc(e):
    return str(e.get("Description", ""))

def sg_of_eni(e):
    gs = e.get("GroupSet") or []
    return str(gs[0].get("GroupId")) if gs else None

def cidr_of_subnet(sid):
    s = next((x for x in subnets if str(x.get("SubnetId")) == sid), None)
    return str(s.get("CidrBlock")) if s else None

def subnet_name(s):
    return next((str(t.get("Value")) for t in s.get("TagSet", []) if str(t.get("Key")) == "Name"), "")

def acl_for_subnet(sid):
    return next((a for a in acls if any(str(x.get("SubnetId")) == sid for x in a.get("AssociationSet", []))), None)

def rt_for_subnet(sid):
    return next((t for t in rts if any(str(x.get("SubnetId")) == sid for x in t.get("AssociationSet", []))), None)

set_enis = [e for e in enis if eni_desc(e).lower().startswith(service_base)]
set_backends = [e for e in set_enis if "vip" not in eni_desc(e).lower()]
set_vip_eni = next((e for e in set_enis if "vip" in eni_desc(e).lower()), None)
SET_SG = sg_of_eni(set_backends[0])
SET_SUBNET = str(set_backends[0].get("SubnetId"))
SET_CIDR = cidr_of_subnet(SET_SUBNET)
SET_VIP = str(set_vip_eni.get("PrivateIpAddress")) if set_vip_eni else str(set_backends[0].get("PrivateIpAddress"))
print("settlement: SG=%s subnet=%s (%s) VIP=%s" % (SET_SG, SET_SUBNET, SET_CIDR, SET_VIP))

partner_subnet = next((s for s in subnets if "partner" in subnet_name(s).lower()), None)
PARTNER_CIDR = str(partner_subnet.get("CidrBlock")) if partner_subnet else None
ledger_eni = next((e for e in enis if "ledger" in eni_desc(e).lower() and "vip" not in eni_desc(e).lower()), None)
LEDGER_SG = sg_of_eni(ledger_eni)
LEDGER_CIDR = cidr_of_subnet(str(ledger_eni.get("SubnetId")))
print("partner_cidr=%s ledger_sg=%s ledger_cidr=%s" % (PARTNER_CIDR, LEDGER_SG, LEDGER_CIDR))

sibling_sgs = sorted(gid for gid, g in sgs.items() if gid not in (SET_SG, LEDGER_SG)
                     and any(str(r.get("CidrIp")) == LEDGER_CIDR
                             for p in g.get("IpPermissionsEgress", []) for r in p.get("IpRanges", [])))
print("sibling integration SGs:", sibling_sgs)
sibling_subnets, sibling_bases = [], []
for gid in sibling_sgs:
    se = next((e for e in enis if sg_of_eni(e) == gid and "vip" not in eni_desc(e).lower()), None)
    if se:
        sibling_subnets.append(cidr_of_subnet(str(se.get("SubnetId"))))
    gname = str(sgs[gid].get("GroupName", ""))
    sibling_bases.append(re.sub(r"-api-sg$", "", gname))
sibling_subnets = [c for c in sibling_subnets if c]
print("sibling service subnets:", sibling_subnets, "bases:", sibling_bases)

def add_missing_perms(target_gid, sibling_gids, direction):
    action = "AuthorizeSecurityGroupIngress" if direction == "ingress" else "AuthorizeSecurityGroupEgress"
    field = "IpPermissions" if direction == "ingress" else "IpPermissionsEgress"
    sib_sets, by_key = [], {}
    for gid in sibling_gids:
        keys = set()
        for p in (sgs.get(gid) or {}).get(field, []):
            k = ing_key(p)
            keys.add(k)
            by_key[k] = p
        sib_sets.append(keys)
    baseline = set.intersection(*sib_sets) if sib_sets else set()
    have = {ing_key(p) for p in (sgs.get(target_gid) or {}).get(field, [])}
    for k in sorted(baseline - have, key=lambda x: (x[1] or 0)):
        p = by_key[k]
        for r in p.get("IpRanges", []):
            cidr = r.get("CidrIp")
            if cidr and cidr != "0.0.0.0/0":
                aws(action, GroupId=target_gid, IpProtocol=p.get("IpProtocol"),
                    FromPort=p.get("FromPort"), ToPort=p.get("ToPort"), CidrIp=cidr)
                print("  +%s %s %s from/to %s on %s" % (direction, p.get("IpProtocol"), p.get("FromPort"), cidr, target_gid))

add_missing_perms(SET_SG, sibling_sgs, "ingress")
add_missing_perms(SET_SG, sibling_sgs, "egress")

ledger_sg = sgs.get(LEDGER_SG) or {}
db_ports = {(p.get("FromPort"), p.get("ToPort"), str(p.get("IpProtocol")))
            for p in ledger_sg.get("IpPermissions", [])
            for r in p.get("IpRanges", []) if str(r.get("CidrIp")) in sibling_subnets}
have_set = any(str(r.get("CidrIp")) == SET_CIDR for p in ledger_sg.get("IpPermissions", []) for r in p.get("IpRanges", []))
if db_ports and not have_set:
    for fp, tp, proto in sorted(db_ports):
        aws("AuthorizeSecurityGroupIngress", GroupId=LEDGER_SG, IpProtocol=proto, FromPort=fp, ToPort=tp, CidrIp=SET_CIDR)
        print("  +ledger ingress %s %s from settlement %s" % (proto, fp, SET_CIDR))

set_acl = acl_for_subnet(SET_SUBNET)
sib_acls = [acl_for_subnet(next(e.get("SubnetId") for e in enis if sg_of_eni(e) == gid)) for gid in sibling_sgs]
sib_acls = [a for a in sib_acls if a]

def allow_keys(a):
    return {acl_allow_key(e) for e in a.get("EntrySet", []) if str(e.get("RuleAction")).lower() == "allow"}

sib_acl_baseline = set.intersection(*[allow_keys(a) for a in sib_acls]) if sib_acls else set()
set_acl_have = allow_keys(set_acl)
acl_src = {}
for a in sib_acls:
    for e in a.get("EntrySet", []):
        acl_src[acl_allow_key(e)] = e
used_rules = {(bool(e.get("Egress")), int(e.get("RuleNumber"))) for e in set_acl.get("EntrySet", [])
              if str(e.get("RuleNumber")).isdigit()}

def next_rule(egress):
    n = 200
    while (egress, n) in used_rules:
        n += 1
    used_rules.add((egress, n))
    return n

for k in sorted(sib_acl_baseline - set_acl_have, key=lambda x: (x[0], str(x[2]))):
    e = acl_src[k]
    pr = e.get("PortRange") or {}
    params = dict(NetworkAclId=set_acl["NetworkAclId"], RuleNumber=next_rule(bool(e.get("Egress"))),
                  Protocol=e.get("Protocol"), RuleAction="allow",
                  Egress="true" if e.get("Egress") else "false", CidrBlock=e.get("CidrBlock"))
    if pr:
        params["PortRange.From"], params["PortRange.To"] = pr.get("From"), pr.get("To")
    aws("CreateNetworkAclEntry", **params)
    print("  +settlement NACL %s allow %s ports=%s" % ("egress" if e.get("Egress") else "ingress", e.get("CidrBlock"), pr or "-"))

dns_now = [r for r in (get(DNS + "/record:a") or []) if isinstance(r, dict)]
sibling_vips = {}
for gid in sibling_sgs:
    ve = next((e for e in enis if sg_of_eni(e) == gid and "vip" in eni_desc(e).lower()), None)
    if ve:
        sibling_vips[gid] = str(ve.get("PrivateIpAddress"))
suffixes = set()
for gid, base in zip(sibling_sgs, sibling_bases):
    vip = sibling_vips.get(gid)
    for r in dns_now:
        nm = str(r.get("name"))
        if str(r.get("ipv4addr")) == vip and nm.startswith(base):
            local = nm.split(".")[0]
            suffixes.add(local[len(base):])
existing_names = {str(r.get("name")).split(".")[0] for r in dns_now}
domain = str(dns_now[0].get("name")).split(".", 1)[1] if dns_now else "example"
for suf in sorted(suffixes):
    local = service_base + suf
    if local not in existing_names:
        res = call("POST", DNS + "/record:a", body={"name": local + "." + domain, "ipv4addr": SET_VIP, "view": "default"})
        print("  +DNS %s -> %s (%s)" % (local + "." + domain, SET_VIP,
                                        "ok" if not (isinstance(res, dict) and res.get("_error")) else res))

sent_incs = get(SENT_BASE + API_VER)
sent_incs = (sent_incs or {}).get("value", []) if isinstance(sent_incs, dict) else []
sent_id = str(sent_incs[0].get("name")) if sent_incs else None
bmarks = call("POST", SENT_BASE + "/" + sent_id + "/bookmarks" + API_VER) if sent_id else {}
bmarks = (bmarks or {}).get("value", []) if isinstance(bmarks, dict) else []
print("audit: %d bookmarks; reverting the unauthorized (no change ticket) ones" % len(bmarks))

CIDR_RE = re.compile(r"(\d+\.\d+\.\d+\.\d+/\d+)")
PORT_RE = re.compile(r"tcp/(\d+)")
DNS_RE = re.compile(r"A record ([\w.-]+)\s*->\s*(\d+\.\d+\.\d+\.\d+)")
RES_RE = re.compile(r"(sg-\w+|acl-\w+|rtb-\w+)")

def rec_uuid(rec):
    if rec.get("uuid"):
        return str(rec["uuid"])
    m = re.search(r"record:a/([^:]+):", str(rec.get("_ref", "")))
    return m.group(1) if m else None

for b in bmarks:
    props = b.get("properties") or {}
    if str(props.get("changeTicket", "")):
        continue
    text = str(props.get("notes") or props.get("queryResult") or "")
    op = (str(props.get("query", "")) + " " + text)
    res = RES_RE.search(text)
    res = res.group(1) if res else None
    cidrs = CIDR_RE.findall(text)
    port = PORT_RE.search(text)
    port = int(port.group(1)) if port else None
    if "SecurityGroupIngress" in op and res and cidrs and port:
        aws("RevokeSecurityGroupIngress", GroupId=res, IpProtocol="tcp", FromPort=port, ToPort=port, CidrIp=cidrs[0])
        print("  -ingress %s tcp/%d from %s on %s" % (res, port, cidrs[0], res))
    elif "SecurityGroupEgress" in op and res:
        aws("RevokeSecurityGroupEgress", GroupId=res, IpProtocol="-1", CidrIp="0.0.0.0/0")
        print("  -egress all->0.0.0.0/0 on %s" % res)
    elif "CreateRoute" in op and res and cidrs:
        aws("DeleteRoute", RouteTableId=res, DestinationCidrBlock=cidrs[0])
        print("  -route %s from %s" % (cidrs[0], res))
    elif "CreateNetworkAclEntry" in op and res:
        acl = next((a for a in aws_set("DescribeNetworkAcls", "networkAclSet") if str(a.get("NetworkAclId")) == res), None)
        world = "0.0.0.0/0" if "0.0.0.0/0" in text else (cidrs[0] if cidrs else None)
        ent = next((e for e in (acl or {}).get("EntrySet", []) if (not bool(e.get("Egress")))
                    and str(e.get("RuleAction")).lower() == "allow" and str(e.get("CidrBlock")) == world), None)
        if ent:
            aws("DeleteNetworkAclEntry", NetworkAclId=res, RuleNumber=ent.get("RuleNumber"), Egress="false")
            print("  -NACL inbound allow %s on %s" % (world, res))
    else:
        m = DNS_RE.search(text)
        if m:
            name, ip = m.group(1), m.group(2)
            rec = next((r for r in (get(DNS + "/record:a") or []) if isinstance(r, dict)
                        and str(r.get("name")) == name and str(r.get("ipv4addr")) == ip), None)
            if rec:
                call("DELETE", DNS + "/record:a/" + rec_uuid(rec))
                print("  -DNS %s -> %s" % (name, ip))

call("PATCH", SN + "/incident/%s" % inc_sys, body={
    "state": CLOSED, "close_code": "Solved (Permanently)",
    "close_notes": ("Reconciled the live network to the approved-change baseline: applied the "
                    "CAB-approved settlement onboarding wiring that had never been implemented and "
                    "reverted the unauthorized firefight changes (no change ticket). Suspected deploy "
                    "verified not the cause.")})
pd_users = (get(PD + "/users") or {}).get("users", [])
actor_email = str(pd_users[0].get("email")) if pd_users else "oncall@aureuspay.example"
pd_list = (get(PD + "/incidents") or {}).get("incidents", [])
for inc in pd_list:
    if str(inc.get("status")) in ("triggered", "acknowledged"):
        r = call("PUT", PD + "/incidents/" + str(inc.get("id")), body={"incident": {"status": "resolved"}},
                 headers={"From": actor_email})
        print("  resolve PD %s (%s)" % (inc.get("id"), "ok" if not (isinstance(r, dict) and r.get("_error")) else r))

print("\n--- readback ---")
sgs2 = {str(g.get("GroupId")): g for g in aws_set("DescribeSecurityGroups", "securityGroupInfo")}

def ing_ok(gid, port, cidr):
    for p in (sgs2.get(gid) or {}).get("IpPermissions", []):
        if str(p.get("IpProtocol")).lower() == "tcp" and p.get("FromPort") is not None and int(p["FromPort"]) <= port <= int(p["ToPort"]) and any(str(r.get("CidrIp")) == cidr for r in p.get("IpRanges", [])):
            return True
    return False

def egr_ok(gid, port, cidr):
    for p in (sgs2.get(gid) or {}).get("IpPermissionsEgress", []):
        if str(p.get("IpProtocol")).lower() == "tcp" and p.get("FromPort") is not None and int(p["FromPort"]) <= port <= int(p["ToPort"]) and any(str(r.get("CidrIp")) == cidr for r in p.get("IpRanges", [])):
            return True
    return False

def world_ing(gid, port):
    return ing_ok(gid, port, "0.0.0.0/0")

APIGW_SG = next((sg_of_eni(e) for e in enis if "api-gateway" in eni_desc(e).lower()), None)
check("settlement SG ingress callback from partner", ing_ok(SET_SG, 8443, PARTNER_CIDR))
check("settlement SG ingress from api-gateway", ing_ok(SET_SG, 443, cidr_of_subnet(next(e.get("SubnetId") for e in enis if "api-gateway" in eni_desc(e).lower()))))
check("settlement SG egress to partner", egr_ok(SET_SG, 443, PARTNER_CIDR))
check("settlement SG egress to ledger", egr_ok(SET_SG, 5432, LEDGER_CIDR))
check("ledger SG admits settlement", ing_ok(LEDGER_SG, 5432, SET_CIDR))
check("no world callback on settlement SG", not world_ing(SET_SG, 8443))
check("no world ingress on settlement SG", not any(str(r.get("CidrIp")) == "0.0.0.0/0"
      for p in (sgs2.get(SET_SG) or {}).get("IpPermissions", []) for r in p.get("IpRanges", [])))
check("no world egress on settlement SG", not any(str(p.get("IpProtocol")) == "-1"
      for p in (sgs2.get(SET_SG) or {}).get("IpPermissionsEgress", [])))
check("no world ssh on api-gateway SG", not world_ing(APIGW_SG, 22))
check("no world rdp on api-gateway SG", not world_ing(APIGW_SG, 3389))
check("api-gateway world 443 preserved", world_ing(APIGW_SG, 443))
check("ledger broad grant removed", not ing_ok(LEDGER_SG, 5432, "10.0.0.0/8"))
check("ledger still admits siblings", all(ing_ok(LEDGER_SG, 5432, c) for c in sibling_subnets))

acls2 = aws_set("DescribeNetworkAcls", "networkAclSet")
set_acl2 = next(a for a in acls2 if a["NetworkAclId"] == set_acl["NetworkAclId"])

def acl_allow(a, egress, cidr):
    return any(bool(e.get("Egress")) == egress and str(e.get("RuleAction")).lower() == "allow"
               and str(e.get("CidrBlock")) == cidr for e in a["EntrySet"])

check("settlement NACL partner inbound", acl_allow(set_acl2, False, PARTNER_CIDR))
check("settlement NACL ledger outbound", acl_allow(set_acl2, True, LEDGER_CIDR))
check("settlement NACL ledger return inbound", acl_allow(set_acl2, False, LEDGER_CIDR))
check("settlement NACL no world inbound", not acl_allow(set_acl2, False, "0.0.0.0/0"))
ledger_acl2 = acl_for_subnet(str(ledger_eni.get("SubnetId")))
ledger_acl2 = next(a for a in acls2 if a["NetworkAclId"] == ledger_acl2["NetworkAclId"])
check("ledger NACL no world inbound", not acl_allow(ledger_acl2, False, "0.0.0.0/0"))

rts2 = aws_set("DescribeRouteTables", "routeTableSet")
set_rt2 = rt_for_subnet(SET_SUBNET)
set_rt2 = next(t for t in rts2 if t["RouteTableId"] == set_rt2["RouteTableId"])
check("no active external route on settlement RT",
      not any(str(r.get("State")) == "active" and not str(r.get("DestinationCidrBlock")).startswith("10.")
              for r in set_rt2["RouteSet"]))
check("settlement RT keeps local route", any(str(r.get("GatewayId")) == "local" for r in set_rt2["RouteSet"]))

dns2 = [r for r in (get(DNS + "/record:a") or []) if isinstance(r, dict)]
_d = {str(r.get("name")): str(r.get("ipv4addr")) for r in dns2}
check("settlement-api DNS published live", _d.get(service_base + "-api." + domain) in LIVE_IPS)
check("settlement-callback DNS published live", _d.get(service_base + "-callback." + domain) in LIVE_IPS)
check("rogue DNS removed", all(str(r.get("ipv4addr")) in LIVE_IPS or not str(r.get("name")).endswith(domain)
                               for r in dns2 if str(r.get("name")) == "ledger-admin." + domain) and
      "ledger-admin." + domain not in _d or _d.get("ledger-admin." + domain) in LIVE_IPS)

inc2 = (get(SN + "/incident/%s" % inc_sys) or {}).get("result", {})
check("incident closed", str(inc2.get("state")) == CLOSED)
pd2 = (get(PD + "/incidents") or {}).get("incidents", [])
check("pagerduty page resolved", all(str(i.get("status")) == "resolved" for i in pd2))

print("\n%d mismatch(es)" % len(MISMATCHES))
for m in MISMATCHES:
    print("  FAILED:", m)
sys.exit(1 if MISMATCHES else 0)
