import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request

AWS = "http://aws-vpc.local.mock:8080/"
HAP = "http://haproxy.local.mock:8080/v3/services/haproxy/configuration"
HAP_RT = "http://haproxy.local.mock:8080/v3/services/haproxy/runtime"
DNS = "http://infoblox-nios.local.mock:8080/wapi/v2.14"
SN = "http://servicenow.local.mock:8080/api/now/table"

SG_PAY = "sg-0payments00000001"
SG_IAPI = "sg-0internalapi0001"
SG_DB = "sg-0db0000000000001"
SG_CACHE = "sg-0cache00000001"
NACL_PAY = "acl-0payments0001"
NACL_SHARED = "acl-0shared00001"
RT_PAY = "rtb-0payments001"

LB_CIDR, PAY_CIDR, SHARED_CIDR = "10.60.0.0/24", "10.30.0.0/24", "10.50.0.0/24"
LB_PORTS = [443, 8081, 8404]
DEP_PORT = {"internal-api": 8443, "payments-db": 5432, "cache": 6379}
EPHEMERAL = (1024, 65535)
DECOMMISSIONED = "10.40.0.0/16"
LIVE = {"internal-api": {"10.50.0.50", "10.50.0.51", "10.50.0.52"},
        "payments-db": {"10.50.0.60", "10.50.0.61"},
        "cache": {"10.50.0.70", "10.50.0.71"}}
LEGACY_DEAD_IP = "10.40.0.51"
DEAD_BACKEND_IP = "10.30.0.9"
DOMAIN = "rialto.example"
INC_SYS = "2e31b68847d76a4d2e68c219abab4e2a"

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

def _nacl_allows(aid, egress, cidr_options, cover_ephemeral):
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
        pr = e.get("PortRange") or {}
        frm, to = pr.get("From"), pr.get("To")
        if frm is None and to is None:
            if str(e.get("Protocol")) == "-1" or not cover_ephemeral:
                return True
            continue
        try:
            if not cover_ephemeral or (int(frm) <= EPHEMERAL[0] and int(to) >= EPHEMERAL[1]):
                return True
        except (TypeError, ValueError):
            continue
    return False

def _dns_records(name):
    recs = _get(DNS + "/record:a")
    recs = recs if isinstance(recs, list) else []
    return [r for r in recs if str(r.get("name")) == name]

def _resolves_live(short, service):
    recs = _dns_records(short + "." + DOMAIN)
    return bool(recs) and all(str(r.get("ipv4addr")) in LIVE[service] for r in recs)

def _runtime_admin(backend, server):
    try:
        rec = _get(HAP_RT + "/backends/%s/servers/%s" % (backend, server))
    except urllib.error.HTTPError:
        return None
    return str((rec or {}).get("admin_state")) if rec else None

def _pay_servers():
    r = _get(HAP + "/backends/payments-be/servers")
    return r if isinstance(r, list) else []

def _incident_state(sys_id):
    r = _get(SN + "/incident/" + sys_id)
    rec = (r or {}).get("result") if isinstance(r, dict) else None
    return str((rec or {}).get("state")) if rec else None

def _in(ip, cidr):
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(cidr)
    except ValueError:
        return False

def test_payments_sg_ingress_443_from_lb():
    assert _ingress_allows(SG_PAY, 443, LB_CIDR)

def test_payments_sg_ingress_8081_from_lb():
    assert _ingress_allows(SG_PAY, 8081, LB_CIDR)

def test_payments_sg_ingress_8404_from_lb():
    assert _ingress_allows(SG_PAY, 8404, LB_CIDR)

def test_payments_nacl_edge_return_egress():
    assert _nacl_allows(NACL_PAY, egress=True, cidr_options={LB_CIDR, "0.0.0.0/0"}, cover_ephemeral=True)

def test_payments_backend_02_undrained():
    assert _runtime_admin("payments-be", "payments-api-02") not in ("maint", "drain", "None", None)

def test_payments_sg_egress_internal_api():
    assert _egress_allows(SG_PAY, DEP_PORT["internal-api"], SHARED_CIDR)

def test_payments_sg_egress_db():
    assert _egress_allows(SG_PAY, DEP_PORT["payments-db"], SHARED_CIDR)

def test_payments_sg_egress_cache():
    assert _egress_allows(SG_PAY, DEP_PORT["cache"], SHARED_CIDR)

def test_payments_route_to_shared_not_blackholed():
    t = _rt(RT_PAY)
    assert t is not None
    for r in t.get("RouteSet", []):
        if str(r.get("DestinationCidrBlock")) == SHARED_CIDR and str(r.get("State")) == "blackhole":
            assert False, "blackhole route to shared-services still present"

def test_payments_nacl_dependency_return_ingress():
    assert _nacl_allows(NACL_PAY, egress=False, cidr_options={SHARED_CIDR, "0.0.0.0/0"}, cover_ephemeral=True)

def test_shared_nacl_allows_payments_inbound():
    assert _nacl_allows(NACL_SHARED, egress=False, cidr_options={PAY_CIDR, "0.0.0.0/0"}, cover_ephemeral=False)

def test_internal_api_sg_allows_payments():
    assert _ingress_allows(SG_IAPI, DEP_PORT["internal-api"], PAY_CIDR)

def test_db_sg_allows_payments():
    assert _ingress_allows(SG_DB, DEP_PORT["payments-db"], PAY_CIDR)

def test_cache_sg_allows_payments():
    assert _ingress_allows(SG_CACHE, DEP_PORT["cache"], PAY_CIDR)

def test_internal_api_dns_points_live():
    assert _resolves_live("internal-api", "internal-api")

def test_db_dns_points_live():
    assert _resolves_live("payments-db", "payments-db")

def test_cache_dns_points_live():
    assert _resolves_live("cache", "cache")

def test_internal_api_02_undrained():
    assert _runtime_admin("internal-api-be", "internal-api-02") not in ("maint", "drain", "None", None)

def test_legacy_dns_record_cleaned():
    assert all(str(r.get("ipv4addr")) != LEGACY_DEAD_IP for r in _dns_records("internal-api-legacy." + DOMAIN))

def test_dead_backend_server_removed():
    assert all(str(s.get("address")) != DEAD_BACKEND_IP for s in _pay_servers())

def test_incident_closed():
    assert _incident_state(INC_SYS) in ("6", "7")
