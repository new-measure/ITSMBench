import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request

AWS = "http://aws-vpc.local.mock:8080/"
DNS = "http://infoblox-nios.local.mock:8080/wapi/v2.14"
SN = "http://servicenow.local.mock:8080/api/now/table"
PD = "http://pagerduty.local.mock:8080"

SG_APIGW = "sg-0apigateway00001"
SG_SET = "sg-0settlementapi01"
SG_LEDGER = "sg-0ledgerdb000001"
NACL_SET = "acl-0settlement01"
NACL_LEDGER = "acl-0ledger00001"
RT_SET = "rtb-0settlement1"

APIGW_CIDR, SET_CIDR, LEDGER_CIDR, PARTNER_CIDR = "10.10.0.0/24", "10.20.0.0/24", "10.30.0.0/24", "10.90.0.0/24"
INTERNAL_SUPERNET = "10.0.0.0/8"
EXT_ROUTE_CIDR = "203.0.113.0/24"
EXT_DNS_IP = "203.0.113.45"
CALLBACK_PORT, PARTNER_OUT_PORT, LEDGER_PORT, API_PORT, SSH_PORT, RDP_PORT = 8443, 443, 5432, 443, 22, 3389
EPHEMERAL = (1024, 65535)
DOMAIN = "aureuspay.example"
LIVE_SETTLEMENT = {"10.20.0.100", "10.20.0.11", "10.20.0.12"}
VPC_SUPERNET = "10.0.0.0/8"
INC_SYS = "2e31b68847d76a4d2e68c219abab4e2a"
PD_INCIDENT = "PDSETTLE01"

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

def _rt(rid):
    return next((t for t in _items(_aws("DescribeRouteTables"), "routeTableSet")
                 if str(t.get("RouteTableId")) == rid), None)

def _perm_allows(perms, port, cidr):
    for p in perms or []:
        if str(p.get("IpProtocol")).lower() != "tcp":
            continue
        fp, tp = p.get("FromPort"), p.get("ToPort")
        if fp is None or tp is None or not (int(fp) <= port <= int(tp)):
            continue
        if any(str(r.get("CidrIp")) == cidr for r in p.get("IpRanges", [])):
            return True
    return False

def _ingress_allows(gid, port, cidr):
    g = _sg(gid)
    return bool(g) and _perm_allows(g.get("IpPermissions"), port, cidr)

def _egress_allows(gid, port, cidr):
    g = _sg(gid)
    return bool(g) and _perm_allows(g.get("IpPermissionsEgress"), port, cidr)

def _egress_world_all(gid):
    g = _sg(gid)
    if not g:
        return False
    for p in g.get("IpPermissionsEgress", []):
        if str(p.get("IpProtocol")) in ("-1", "all") and any(str(r.get("CidrIp")) == "0.0.0.0/0"
                                                             for r in p.get("IpRanges", [])):
            return True
    return False

def _nacl_allows(aid, egress, cidr_options, cover=None):
    a = _nacl(aid)
    if not a:
        return False
    for e in a.get("EntrySet", []):
        if bool(e.get("Egress")) != egress or str(e.get("RuleAction")).lower() != "allow":
            continue
        if str(e.get("Protocol")) not in ("6", "-1", "tcp"):
            continue
        if str(e.get("CidrBlock")) not in cidr_options:
            continue
        if cover is None:
            return True
        pr = e.get("PortRange") or {}
        frm, to = pr.get("From"), pr.get("To")
        if frm is None and to is None:
            return True
        try:
            if int(frm) <= cover[0] and int(to) >= cover[1]:
                return True
        except (TypeError, ValueError):
            continue
    return False

def _nacl_has_world_inbound(aid):
    a = _nacl(aid)
    return bool(a) and any((not bool(e.get("Egress"))) and str(e.get("RuleAction")).lower() == "allow"
                           and str(e.get("CidrBlock")) == "0.0.0.0/0" for e in a.get("EntrySet", []))

def _dns_records(name):
    recs = _get(DNS + "/record:a")
    recs = recs if isinstance(recs, list) else []
    return [r for r in recs if str(r.get("name")) == name]

def _incident_state(sys_id):
    r = _get(SN + "/incident/" + sys_id)
    rec = (r or {}).get("result") if isinstance(r, dict) else None
    return str((rec or {}).get("state")) if rec else None

def _pd_status(incident_id):
    r = _get(PD + "/incidents/" + incident_id)
    rec = (r or {}).get("incident") if isinstance(r, dict) else None
    return str((rec or {}).get("status")) if rec else None

def test_settlement_sg_ingress_partner_callback():
    assert _ingress_allows(SG_SET, CALLBACK_PORT, PARTNER_CIDR)

def test_settlement_sg_ingress_apigw():
    assert _ingress_allows(SG_SET, API_PORT, APIGW_CIDR)

def test_settlement_sg_egress_partner():
    assert _egress_allows(SG_SET, PARTNER_OUT_PORT, PARTNER_CIDR)

def test_settlement_sg_egress_ledger():
    assert _egress_allows(SG_SET, LEDGER_PORT, LEDGER_CIDR)

def test_ledger_sg_allows_settlement():
    assert _ingress_allows(SG_LEDGER, LEDGER_PORT, SET_CIDR)

def test_settlement_nacl_partner_inbound():
    assert _nacl_allows(NACL_SET, egress=False, cidr_options={PARTNER_CIDR})

def test_settlement_nacl_ledger_outbound():
    assert _nacl_allows(NACL_SET, egress=True, cidr_options={LEDGER_CIDR})

def test_settlement_nacl_ledger_return_inbound():
    assert _nacl_allows(NACL_SET, egress=False, cidr_options={LEDGER_CIDR}, cover=EPHEMERAL)

def test_settlement_api_dns_published():
    recs = _dns_records("settlement-api." + DOMAIN)
    assert bool(recs) and all(str(r.get("ipv4addr")) in LIVE_SETTLEMENT for r in recs)

def test_settlement_callback_dns_published():
    recs = _dns_records("settlement-callback." + DOMAIN)
    assert bool(recs) and all(str(r.get("ipv4addr")) in LIVE_SETTLEMENT for r in recs)

def test_apigw_sg_world_ssh_reverted():
    assert not _ingress_allows(SG_APIGW, SSH_PORT, "0.0.0.0/0")

def test_apigw_sg_world_rdp_reverted():
    assert not _ingress_allows(SG_APIGW, RDP_PORT, "0.0.0.0/0")

def test_ledger_sg_broad_grant_reverted():
    assert not _ingress_allows(SG_LEDGER, LEDGER_PORT, INTERNAL_SUPERNET)

def test_settlement_sg_world_callback_reverted():
    assert not _ingress_allows(SG_SET, CALLBACK_PORT, "0.0.0.0/0")

def test_settlement_sg_world_egress_reverted():
    assert not _egress_world_all(SG_SET)

def test_settlement_route_external_reverted():
    t = _rt(RT_SET)
    assert t is not None
    for r in t.get("RouteSet", []):
        if str(r.get("DestinationCidrBlock")) == EXT_ROUTE_CIDR and str(r.get("State")) == "active":
            assert False, "unauthorized active external route still present"

def test_ledger_nacl_world_inbound_reverted():
    assert not _nacl_has_world_inbound(NACL_LEDGER)

def test_settlement_nacl_world_inbound_reverted():
    assert not _nacl_has_world_inbound(NACL_SET)

def test_rogue_dns_reverted():
    assert all(str(r.get("ipv4addr")) != EXT_DNS_IP for r in _dns_records("ledger-admin." + DOMAIN))

def test_servicenow_incident_closed():
    assert _incident_state(INC_SYS) in ("6", "7")

def test_pagerduty_incident_resolved():
    assert _pd_status(PD_INCIDENT) == "resolved"
