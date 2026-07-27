import json
import urllib.error
import urllib.parse
import urllib.request

AWS = "http://aws-vpc.local.mock:8080/"
HAP = "http://haproxy.local.mock:8080/v3/services/haproxy/configuration"
HAP_RT = "http://haproxy.local.mock:8080/v3/services/haproxy/runtime"
DNS = "http://infoblox-nios.local.mock:8080/wapi/v2.14"
PD = "http://pagerduty.local.mock:8080"

DOMAIN = "shopwave.example"
EDGE_CIDR = "10.5.0.0/24"
ORIGIN_CIDR = "10.50.0.0/24"
BASELINE_WEIGHT = 100
STALE_FAILOVER_IP = "10.99.0.9"

WEST_WEB_VIP, WEST_API_VIP = "10.20.0.10", "10.20.0.20"
EAST_WEB_VIP, EAST_API_VIP = "10.10.0.10", "10.10.0.20"

SG_WEST_WEB = "sg-0webwest000001"
SG_WEST_API = "sg-0apiwest000001"
NACL_WEST_WEB = "acl-0webwest01"
RT_WEST_WEB = "rtb-0webwest01"

WEB_APP, WEB_CHK, AGENT_CHK = 443, 8081, 8404
API_APP, API_CHK = 8443, 8082
EPHEMERAL = (1024, 65535)

BE_WEST_WEB, BE_WEST_API = "web-be-west", "api-be-west"
PAGE_ID = "PSHOP01"

def _get(url, headers=None):
    h = {"Accept": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
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

def _in_rotation(name, ip):
    for r in _dns_records(name + "." + DOMAIN):
        if str(r.get("ipv4addr")) == ip and str(r.get("disable")).lower() not in ("true", "1"):
            return r
    return None

def _config_servers(backend):
    r = _get(HAP + "/backends/%s/servers" % backend)
    return r if isinstance(r, list) else []

def _runtime_admin(backend, server):
    try:
        rec = _get(HAP_RT + "/backends/%s/servers/%s" % (backend, server))
    except urllib.error.HTTPError:
        return None
    return str((rec or {}).get("admin_state")) if rec else None

def _incident_status(iid):
    r = _get(PD + "/incidents/" + iid)
    inc = (r or {}).get("incident") if isinstance(r, dict) else None
    return str((inc or {}).get("status")) if inc else None

def _check_enabled(server):
    return str(server.get("check")).lower() in ("enabled", "on", "true", "1", "active")

def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None

def test_www_rotation_includes_west():
    assert _in_rotation("www", WEST_WEB_VIP) is not None

def test_www_west_weight_matches_baseline():
    rec = _in_rotation("www", WEST_WEB_VIP)
    assert rec is not None and _int(rec.get("weight")) == BASELINE_WEIGHT

def test_api_rotation_includes_west():
    assert _in_rotation("api", WEST_API_VIP) is not None

def test_api_west_weight_restored():
    rec = _in_rotation("api", WEST_API_VIP)
    assert rec is not None and _int(rec.get("weight")) == BASELINE_WEIGHT

def test_stale_failover_record_cleaned():
    assert all(str(r.get("ipv4addr")) != STALE_FAILOVER_IP for r in _dns_records("www." + DOMAIN))

def test_web_west_w1_undrained():
    assert _runtime_admin(BE_WEST_WEB, "web-w1") not in ("maint", "drain", "None", None)

def test_web_west_w2_undrained():
    assert _runtime_admin(BE_WEST_WEB, "web-w2") not in ("maint", "drain", "None", None)

def test_api_west_w1_undrained():
    assert _runtime_admin(BE_WEST_API, "api-w1") not in ("maint", "drain", "None", None)

def test_api_west_w2_undrained():
    assert _runtime_admin(BE_WEST_API, "api-w2") not in ("maint", "drain", "None", None)

def test_web_west_healthcheck_port_fixed():
    srvs = _config_servers(BE_WEST_WEB)
    assert srvs and all(_check_enabled(s) and int(s.get("health_check_port")) == WEB_CHK for s in srvs)

def test_api_west_healthcheck_enabled():
    srvs = _config_servers(BE_WEST_API)
    assert srvs and all(_check_enabled(s) for s in srvs)

def test_web_west_sg_ingress_443():
    assert _ingress_allows(SG_WEST_WEB, WEB_APP, EDGE_CIDR)

def test_web_west_sg_ingress_8081():
    assert _ingress_allows(SG_WEST_WEB, WEB_CHK, EDGE_CIDR)

def test_web_west_sg_ingress_8404():
    assert _ingress_allows(SG_WEST_WEB, AGENT_CHK, EDGE_CIDR)

def test_api_west_sg_ingress_8443():
    assert _ingress_allows(SG_WEST_API, API_APP, EDGE_CIDR)

def test_api_west_sg_ingress_8082():
    assert _ingress_allows(SG_WEST_API, API_CHK, EDGE_CIDR)

def test_web_west_sg_egress_to_origin():
    assert _egress_allows(SG_WEST_WEB, API_APP, ORIGIN_CIDR)

def test_web_west_nacl_inbound_from_edge():
    assert _nacl_allows(NACL_WEST_WEB, egress=False, cidr_options={EDGE_CIDR, "0.0.0.0/0"}, cover_ephemeral=False)

def test_web_west_nacl_return_egress_to_edge():
    assert _nacl_allows(NACL_WEST_WEB, egress=True, cidr_options={EDGE_CIDR, "0.0.0.0/0"}, cover_ephemeral=True)

def test_web_west_route_not_blackholed():
    t = _rt(RT_WEST_WEB)
    assert t is not None
    for r in t.get("RouteSet", []):
        if str(r.get("DestinationCidrBlock")) == EDGE_CIDR and str(r.get("State")) == "blackhole":
            assert False, "blackhole route to the edge/health tier still present"

def test_page_resolved():
    assert _incident_status(PAGE_ID) == "resolved"
