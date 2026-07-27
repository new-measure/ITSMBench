import json
import urllib.parse
import urllib.request

AWS = "http://aws-vpc.local.mock:8080/"
DNS = "http://infoblox-nios.local.mock:8080/wapi/v2.14"
SN = "http://servicenow.local.mock:8080/api/now/table"

SG_PAY = "sg-0payments00001"
ENDPOINT_SG = {"auth": "sg-0auth00000001", "database": "sg-0db0000000001", "cache": "sg-0cache0000001",
               "secrets": "sg-0secrets00001", "broker": "sg-0broker000001", "config": "sg-0config000001"}
NACL_PAY, NACL_SHARED = "acl-0payments001", "acl-0shared0001"
RT_PAY, RT_SHARED = "rtb-0payments01", "rtb-0shared001"
PCX_LIVE = "pcx-0live00000001"

PROD_VPC_CIDR, SHARED_VPC_CIDR = "10.20.0.0/16", "10.80.0.0/16"
PAY_CIDR, SHARED_SUBNET_CIDR = "10.20.10.0/24", "10.80.0.0/24"
DEP_PORT = {"auth": 8443, "database": 5432, "cache": 6379, "secrets": 8200, "broker": 5672, "config": 8500}
CALLBACK_PORT = 8082
EPHEMERAL = (1024, 65535)
DOMAIN = "svc.vantage.internal"
DEAD_IPS = {"auth-legacy": "10.70.0.10", "db-old": "10.70.0.11", "cache-stale": "10.70.0.12"}
INC_SYS = "de130c8185abf111552e88a243b423df"

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

def _perm_allows(perms, port, cidr_options):
    for p in perms or []:
        proto = str(p.get("IpProtocol")).lower()
        if proto not in ("tcp", "-1"):
            continue
        fp, tp = p.get("FromPort"), p.get("ToPort")
        if proto == "tcp":
            if fp is None or tp is None or not (int(fp) <= port <= int(tp)):
                continue
        if any(str(r.get("CidrIp")) in cidr_options for r in p.get("IpRanges", [])):
            return True
    return False

def _ingress_allows(gid, port, cidr_options):
    g = _sg(gid)
    return bool(g) and _perm_allows(g.get("IpPermissions"), port, cidr_options)

def _egress_allows(gid, port, cidr_options):
    g = _sg(gid)
    return bool(g) and _perm_allows(g.get("IpPermissionsEgress"), port, cidr_options)

def _nacl_allows(aid, egress, cidr_options, ports):
    a = _nacl(aid)
    if not a:
        return False
    for port in ports:
        ok = False
        for e in a.get("EntrySet", []):
            if bool(e.get("Egress")) != egress or str(e.get("RuleAction")).lower() != "allow":
                continue
            if str(e.get("Protocol")) not in ("6", "-1", "tcp"):
                continue
            if str(e.get("CidrBlock")) not in cidr_options:
                continue
            pr = e.get("PortRange") or {}
            frm, to = pr.get("From"), pr.get("To")
            if frm is None and to is None:
                ok = True
                break
            try:
                if int(frm) <= port <= int(to):
                    ok = True
                    break
            except (TypeError, ValueError):
                continue
        if not ok:
            return False
    return True

def _active_route_covers(rid, dest_options, pcx):
    t = _rt(rid)
    if not t:
        return False
    for r in t.get("RouteSet", []):
        if (str(r.get("DestinationCidrBlock")) in dest_options and str(r.get("State")) == "active"
                and str(r.get("VpcPeeringConnectionId", "")) == pcx):
            return True
    return False

def _dns_records(name):
    recs = _get(DNS + "/record:a")
    recs = recs if isinstance(recs, list) else []
    return [r for r in recs if str(r.get("name")) == name]

def _incident_state(sys_id):
    r = _get(SN + "/incident/" + sys_id)
    rec = (r or {}).get("result") if isinstance(r, dict) else None
    return str((rec or {}).get("state")) if rec else None

SHARED_DEST = {SHARED_SUBNET_CIDR, SHARED_VPC_CIDR}
PAY_DEST = {PAY_CIDR, PROD_VPC_CIDR}

def test_payments_sg_egress_auth():
    assert _egress_allows(SG_PAY, DEP_PORT["auth"], SHARED_DEST)

def test_payments_sg_egress_database():
    assert _egress_allows(SG_PAY, DEP_PORT["database"], SHARED_DEST)

def test_payments_sg_egress_cache():
    assert _egress_allows(SG_PAY, DEP_PORT["cache"], SHARED_DEST)

def test_payments_sg_egress_secrets():
    assert _egress_allows(SG_PAY, DEP_PORT["secrets"], SHARED_DEST)

def test_payments_sg_egress_broker():
    assert _egress_allows(SG_PAY, DEP_PORT["broker"], SHARED_DEST)

def test_payments_sg_egress_config():
    assert _egress_allows(SG_PAY, DEP_PORT["config"], SHARED_DEST)

def test_payments_sg_ingress_auth_callback():
    assert _ingress_allows(SG_PAY, CALLBACK_PORT, SHARED_DEST)

def test_payments_route_no_blackhole():
    t = _rt(RT_PAY)
    assert t is not None and all(str(r.get("State")) != "blackhole" for r in t.get("RouteSet", []))

def test_payments_route_active_via_live_peering():
    assert _active_route_covers(RT_PAY, SHARED_DEST, PCX_LIVE)

def test_payments_nacl_outbound_to_shared():
    assert _nacl_allows(NACL_PAY, egress=True,
                        cidr_options=SHARED_DEST | {"0.0.0.0/0"},
                        ports=sorted(DEP_PORT.values()))

def test_payments_nacl_inbound_return_from_shared():
    assert _nacl_allows(NACL_PAY, egress=False, cidr_options=SHARED_DEST,
                        ports=[EPHEMERAL[0], CALLBACK_PORT, EPHEMERAL[1]])

def test_shared_route_returns_to_payments():
    assert _active_route_covers(RT_SHARED, PAY_DEST, PCX_LIVE)

def test_shared_nacl_inbound_from_payments():
    assert _nacl_allows(NACL_SHARED, egress=False, cidr_options=PAY_DEST,
                        ports=sorted(DEP_PORT.values()))

def test_shared_nacl_outbound_return_to_payments():
    assert _nacl_allows(NACL_SHARED, egress=True, cidr_options=PAY_DEST | {"0.0.0.0/0"},
                        ports=[EPHEMERAL[0], EPHEMERAL[1]])

def test_auth_sg_allows_payments():
    assert _ingress_allows(ENDPOINT_SG["auth"], DEP_PORT["auth"], {PAY_CIDR})

def test_database_sg_allows_payments():
    assert _ingress_allows(ENDPOINT_SG["database"], DEP_PORT["database"], {PAY_CIDR})

def test_cache_sg_allows_payments():
    assert _ingress_allows(ENDPOINT_SG["cache"], DEP_PORT["cache"], {PAY_CIDR})

def test_secrets_sg_allows_payments():
    assert _ingress_allows(ENDPOINT_SG["secrets"], DEP_PORT["secrets"], {PAY_CIDR})

def test_broker_sg_allows_payments():
    assert _ingress_allows(ENDPOINT_SG["broker"], DEP_PORT["broker"], {PAY_CIDR})

def test_config_sg_allows_payments():
    assert _ingress_allows(ENDPOINT_SG["config"], DEP_PORT["config"], {PAY_CIDR})

def test_dangling_dns_auth_legacy_cleaned():
    assert all(str(r.get("ipv4addr")) != DEAD_IPS["auth-legacy"]
               for r in _dns_records("auth-legacy." + DOMAIN))

def test_dangling_dns_db_old_cleaned():
    assert all(str(r.get("ipv4addr")) != DEAD_IPS["db-old"]
               for r in _dns_records("db-old." + DOMAIN))

def test_dangling_dns_cache_stale_cleaned():
    assert all(str(r.get("ipv4addr")) != DEAD_IPS["cache-stale"]
               for r in _dns_records("cache-stale." + DOMAIN))

def test_incident_closed():
    assert _incident_state(INC_SYS) in ("6", "7")
