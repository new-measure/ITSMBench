import ipaddress
import json
import urllib.parse
import urllib.request

AWS = "http://aws-vpc.local.mock:8080/"
ZIA = "http://zscaler-zia.local.mock:8080/zia/api/v1"
SN = "http://servicenow.local.mock:8080/api/now/table"

SG_APP, SG_DB, SG_TOK = "sg-0cdeaapp000001", "sg-0cdeadb0000001", "sg-0cdeatok000001"
NACL_APP, NACL_DB, NACL_TOK = "acl-0cdeaapp0001", "acl-0cdeadb00001", "acl-0cdeatok0001"

APP_A, DB_A, TOK_A = "10.20.0.0/24", "10.20.1.0/24", "10.20.2.0/24"
WEB_CIDR, SHARED_CIDR = "10.40.0.0/24", "10.50.0.0/24"
WEB_IP, JUMP_IP, SCANNER_IP = "10.40.0.10", "10.50.0.10", "10.50.0.20"
CORP_IP, DEV_IP = "10.10.5.5", "10.30.0.5"
APP_A_IP = "10.20.0.10"
P_APP, P_DB, P_TOK, P_SSH, P_DEBUG = 443, 5432, 9000, 22, 8080
PROC_LIVE = {"198.51.100.10", "198.51.100.11"}
PROC_DEAD, PROC_EXTRA = "192.0.2.50", "203.0.113.99"
ZDG_PROCESSOR = 251
INC_SYS = "e9a1b70d932382674c24ee6a31038719"
SUBJECT_CDE = (APP_A, DB_A, TOK_A)

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode()
    return json.loads(raw) if raw else None

def _aws(action, **params):
    params["Action"] = action
    body = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(AWS, data=body, method="POST",
                                 headers={"Accept": "application/json",
                                          "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode()
    return json.loads(raw) if raw else None

def _items(resp, setname):
    return (((resp or {}).get(setname) or {}).get("item")) or []

def _sg(gid):
    return next((g for g in _items(_aws("DescribeSecurityGroups"), "securityGroupInfo")
                 if str(g.get("GroupId")) == gid), None)

def _nacl(aid):
    return next((a for a in _items(_aws("DescribeNetworkAcls"), "networkAclSet")
                 if str(a.get("NetworkAclId")) == aid), None)

def _covers(cidr, ip):
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(str(cidr), strict=False)
    except ValueError:
        return False

def _within(cidr, supernet):
    try:
        return ipaddress.ip_network(str(cidr), strict=False).subnet_of(
            ipaddress.ip_network(supernet, strict=False))
    except (ValueError, TypeError):
        return False

def _ing_cidrs(gid, port):
    g = _sg(gid)
    out = []
    for p in (g or {}).get("IpPermissions", []):
        if str(p.get("IpProtocol")).lower() not in ("tcp", "-1"):
            continue
        fp, tp = p.get("FromPort"), p.get("ToPort")
        if fp is not None and tp is not None and not (int(fp) <= port <= int(tp)):
            continue
        out += [str(r.get("CidrIp")) for r in p.get("IpRanges", []) if r.get("CidrIp")]
    return out

def _nacl_in_cidrs(aid):
    a = _nacl(aid)
    return [str(e.get("CidrBlock")) for e in (a or {}).get("EntrySet", [])
            if not bool(e.get("Egress")) and str(e.get("RuleAction")).lower() == "allow"
            and e.get("CidrBlock")]

def _rules():
    r = _get(ZIA + "/firewallFilteringRules")
    return r if isinstance(r, list) else []

def _groups(kind):
    r = _get(ZIA + "/" + kind)
    return {str(g.get("id")): g for g in (r if isinstance(r, list) else [])}

def _rule_src_cidrs(rule, src_groups):
    cidrs = [str(x) for x in rule.get("srcIps") or []]
    for g in rule.get("srcIpGroups") or []:
        grp = src_groups.get(str((g or {}).get("id")))
        cidrs += [str(x) for x in (grp or {}).get("ipAddresses") or []]
    return cidrs

def _overlaps(cidr, subnet):
    try:
        return ipaddress.ip_network(str(cidr), strict=False).overlaps(ipaddress.ip_network(subnet))
    except ValueError:
        return False

def _enabled_allow_from(subnet):
    srcg = _groups("ipSourceGroups")
    return [r for r in _rules()
            if str(r.get("action")).upper() == "ALLOW" and str(r.get("state")).upper() == "ENABLED"
            and any(_overlaps(c, subnet) for c in _rule_src_cidrs(r, srcg))]

def _rule_dest_ips(rule, dest_groups):
    ips = [str(x) for x in rule.get("destAddresses") or []]
    for g in rule.get("destIpGroups") or []:
        grp = dest_groups.get(str((g or {}).get("id")))
        ips += [str(x) for x in (grp or {}).get("ipAddresses") or []]
    return ips

def _world(dest):
    return str(dest) in ("0.0.0.0/0", "::/0", "any", "ANY", "*")

def test_app_sg_443_no_noncde_source():
    assert not any(_covers(c, CORP_IP) or _covers(c, DEV_IP) for c in _ing_cidrs(SG_APP, P_APP))

def test_app_sg_443_admits_web_frontend():
    assert any(_within(c, WEB_CIDR) and _covers(c, WEB_IP) for c in _ing_cidrs(SG_APP, P_APP))

def test_app_sg_debug_8080_removed():
    assert not any(any(_covers(c, ip) for ip in (CORP_IP, DEV_IP, WEB_IP, JUMP_IP, SCANNER_IP))
                   for c in _ing_cidrs(SG_APP, P_DEBUG))

def test_app_sg_ssh_admits_bastion():
    assert any(_within(c, SHARED_CIDR) and _covers(c, JUMP_IP) for c in _ing_cidrs(SG_APP, P_SSH))

def test_db_sg_5432_no_corp():
    assert not any(_covers(c, CORP_IP) for c in _ing_cidrs(SG_DB, P_DB))

def test_db_sg_5432_no_dev():
    assert not any(_covers(c, DEV_IP) for c in _ing_cidrs(SG_DB, P_DB))

def test_db_sg_5432_admits_app_tier():
    assert any(_within(c, APP_A) and _covers(c, APP_A_IP) for c in _ing_cidrs(SG_DB, P_DB))

def test_tok_sg_9000_no_corp():
    assert not any(_covers(c, CORP_IP) for c in _ing_cidrs(SG_TOK, P_TOK))

def test_tok_sg_9000_no_dev():
    assert not any(_covers(c, DEV_IP) for c in _ing_cidrs(SG_TOK, P_TOK))

def test_tok_sg_9000_admits_app_tier():
    assert any(_within(c, APP_A) and _covers(c, APP_A_IP) for c in _ing_cidrs(SG_TOK, P_TOK))

def test_app_nacl_no_noncde_inbound():
    assert not any(_covers(c, CORP_IP) or _covers(c, DEV_IP) for c in _nacl_in_cidrs(NACL_APP))

def test_app_nacl_admits_web():
    assert any(_within(c, WEB_CIDR) and _covers(c, WEB_IP) for c in _nacl_in_cidrs(NACL_APP))

def test_app_nacl_admits_bastion():
    assert any(_within(c, SHARED_CIDR) and _covers(c, JUMP_IP) for c in _nacl_in_cidrs(NACL_APP))

def test_db_nacl_no_noncde_inbound():
    assert not any(_covers(c, CORP_IP) or _covers(c, DEV_IP) for c in _nacl_in_cidrs(NACL_DB))

def test_db_nacl_admits_app_tier():
    assert any(_within(c, APP_A) and _covers(c, APP_A_IP) for c in _nacl_in_cidrs(NACL_DB))

def test_db_nacl_admits_scanner():
    assert any(_within(c, SHARED_CIDR) and _covers(c, SCANNER_IP) for c in _nacl_in_cidrs(NACL_DB))

def test_tok_nacl_no_noncde_inbound():
    assert not any(_covers(c, CORP_IP) or _covers(c, DEV_IP) for c in _nacl_in_cidrs(NACL_TOK))

def test_tok_nacl_admits_app_tier():
    assert any(_within(c, APP_A) and _covers(c, APP_A_IP) for c in _nacl_in_cidrs(NACL_TOK))

def test_zia_app_egress_not_world_open():
    assert not any(any(_world(d) for d in r.get("destAddresses") or [])
                   for r in _enabled_allow_from(APP_A))

def test_zia_app_egress_scoped_to_processor():
    destg = _groups("ipDestinationGroups")
    ok = False
    for r in _enabled_allow_from(APP_A):
        ips = _rule_dest_ips(r, destg)
        if ips and all(str(i) in PROC_LIVE for i in ips):
            ok = True
    assert ok

def test_zia_db_egress_removed():
    assert _enabled_allow_from(DB_A) == []

def test_zia_orphan_rule_removed():
    assert not any(PROC_DEAD in [str(d) for d in r.get("destAddresses") or []]
                   for r in _rules()
                   if str(r.get("action")).upper() == "ALLOW" and str(r.get("state")).upper() == "ENABLED")

def test_zia_processor_group_no_unapproved_ip():
    g = _get(ZIA + "/ipDestinationGroups/%d" % ZDG_PROCESSOR)
    assert PROC_EXTRA not in [str(x) for x in (g or {}).get("ipAddresses") or []]

def test_zia_processor_group_covers_live_gateways():
    g = _get(ZIA + "/ipDestinationGroups/%d" % ZDG_PROCESSOR)
    assert PROC_LIVE <= {str(x) for x in (g or {}).get("ipAddresses") or []}

def test_incident_resolved():
    r = _get(SN + "/incident/" + INC_SYS)
    rec = (r or {}).get("result") if isinstance(r, dict) else None
    assert str((rec or {}).get("state")) in ("6", "7")
