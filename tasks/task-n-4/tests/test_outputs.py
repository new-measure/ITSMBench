import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request

AWS = "http://aws-vpc.local.mock:8080/"
HAP = "http://haproxy.local.mock:8080/v3/services/haproxy/configuration"
DNS = "http://infoblox-nios.local.mock:8080/wapi/v2.14"
D42 = "http://device42.local.mock:8080"
SN = "http://servicenow.local.mock:8080/api/now/table"

SG_BILLING = "sg-0billing000001"
SG_LICENSE = "sg-0licensing0001"
RT_LEGACY = "rtb-0legacywms01"
SUB_LEGACY = "subnet-0legacywms01"
LIC_HOST_IP = "10.20.0.30"
LIC_VIP = "10.20.0.31"
APP_CIDR = "10.10.0.0/24"
FLEXLM_PORT = 27000
RT_APP = "rtb-0appbilling01"
DOMAIN = "cascade.example"
CHG_SYS = "3e165bf7102f8b862f691573b6e49522"

WMS_IPS = ["10.20.0.11", "10.20.0.12", "10.20.0.13"]
WMS_DB_IP = "10.20.0.20"
WMS_VIP = "10.20.0.100"
RETIRED_HOST_IPS = WMS_IPS + [WMS_DB_IP]
RETIRED_DNS_IPS = set(RETIRED_HOST_IPS) | {WMS_VIP}
WMS_SYNC_PORT = 8900
WMS_DB_PORT = 1521

RETIRED_DEVICES = ["legacy-wms-01", "legacy-wms-02", "legacy-wms-03", "legacy-wms-db"]
RETIRED_CNAMES = ["wms-portal." + DOMAIN, "wms-legacy." + DOMAIN]
ACTIVE_LIFECYCLE = {"in production", "installed", "operational", "active", "in service", "deployed"}

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        return {"_error": e.code}
    return json.loads(raw) if raw and raw.strip()[:1] in "{[" else raw

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

def _sg_has_ingress(gid, port, cidr):
    g = _sg(gid)
    if not g:
        return False
    for p in g.get("IpPermissions", []):
        if str(p.get("IpProtocol")).lower() != "tcp":
            continue
        fp, tp = p.get("FromPort"), p.get("ToPort")
        if fp is None or tp is None or not (int(fp) <= port <= int(tp)):
            continue
        if any(str(r.get("CidrIp")) == cidr for r in p.get("IpRanges", [])):
            return True
    return False

def _all_eni_ips():
    return {str(e.get("PrivateIpAddress")) for e in _items(_aws("DescribeNetworkInterfaces"), "networkInterfaceSet")}

def _route_table(rid):
    return next((t for t in _items(_aws("DescribeRouteTables"), "routeTableSet")
                 if str(t.get("RouteTableId")) == rid), None)

def _a_records():
    recs = _get(DNS + "/record:a")
    return recs if isinstance(recs, list) else []

def _cname_records():
    recs = _get(DNS + "/record:cname")
    return recs if isinstance(recs, list) else []

def _no_a_resolves_to(ip):
    return all(str(r.get("ipv4addr")) != ip for r in _a_records())

def _hap_backend_names():
    r = _get(HAP + "/backends")
    return {str(b.get("name")) for b in (r if isinstance(r, list) else [])}

def _hap_frontend_names():
    r = _get(HAP + "/frontends")
    return {str(f.get("name")) for f in (r if isinstance(r, list) else [])}

def _hap_all_server_addresses():
    addrs = set()
    for be in _hap_backend_names():
        r = _get(HAP + "/backends/%s/servers" % be)
        for s in (r if isinstance(r, list) else []):
            addrs.add(str(s.get("address")))
    return addrs

def _device_by_name(name):
    r = _get(D42 + "/api/2.0/devices/?name=" + urllib.parse.quote(name))
    devs = (r or {}).get("devices") if isinstance(r, dict) else None
    return (devs or [None])[0] if devs else None

def _is_decommissioned(name):
    d = _device_by_name(name)
    if d is None:
        return True
    if str(d.get("in_service")).lower() in ("false", "no", "0", "none"):
        return True
    if str(d.get("archived")).lower() in ("true", "yes", "1"):
        return True
    lc = str(d.get("lifecycle_status", "")).strip().lower()
    return bool(lc) and lc not in ACTIVE_LIFECYCLE

def _in_service(name):
    d = _device_by_name(name)
    if d is None:
        return False
    if str(d.get("in_service")).lower() in ("false", "no", "0", "none"):
        return False
    if str(d.get("archived")).lower() in ("true", "yes", "1"):
        return False
    lc = str(d.get("lifecycle_status", "")).strip().lower()
    return (not lc) or lc in ACTIVE_LIFECYCLE

def _services():
    r = _get(D42 + "/api/2.0/services/")
    return (r or {}).get("services") or [] if isinstance(r, dict) else []

def _change_state(sys_id):
    r = _get(SN + "/change_request/" + sys_id)
    rec = (r or {}).get("result") if isinstance(r, dict) else None
    return rec or {}

def test_dns_a_legacy_wms_01_cleaned():
    assert _no_a_resolves_to(WMS_IPS[0])

def test_dns_a_legacy_wms_02_cleaned():
    assert _no_a_resolves_to(WMS_IPS[1])

def test_dns_a_legacy_wms_03_cleaned():
    assert _no_a_resolves_to(WMS_IPS[2])

def test_dns_a_legacy_wms_db_cleaned():
    assert _no_a_resolves_to(WMS_DB_IP)

def test_dns_a_legacy_wms_vip_cleaned():
    assert _no_a_resolves_to(WMS_VIP)

def test_dns_cname_wms_portal_removed():
    assert all(str(r.get("name")) != RETIRED_CNAMES[0] for r in _cname_records())

def test_dns_cname_wms_legacy_removed():
    assert all(str(r.get("name")) != RETIRED_CNAMES[1] for r in _cname_records())

def test_haproxy_member_wms_01_removed():
    assert WMS_IPS[0] not in _hap_all_server_addresses()

def test_haproxy_member_wms_02_removed():
    assert WMS_IPS[1] not in _hap_all_server_addresses()

def test_haproxy_member_wms_03_removed():
    assert WMS_IPS[2] not in _hap_all_server_addresses()

def test_haproxy_legacy_backend_removed():
    assert "legacy-wms-be" not in _hap_backend_names()

def test_haproxy_legacy_frontend_removed():
    assert "legacy-wms-fe" not in _hap_frontend_names()

def test_device_legacy_wms_01_decommissioned():
    assert _is_decommissioned("legacy-wms-01")

def test_device_legacy_wms_02_decommissioned():
    assert _is_decommissioned("legacy-wms-02")

def test_device_legacy_wms_03_decommissioned():
    assert _is_decommissioned("legacy-wms-03")

def test_device_legacy_wms_db_decommissioned():
    assert _is_decommissioned("legacy-wms-db")

def test_billing_sg_ref_wms_01_revoked():
    assert not _sg_has_ingress(SG_BILLING, WMS_SYNC_PORT, WMS_IPS[0] + "/32")

def test_billing_sg_ref_wms_02_revoked():
    assert not _sg_has_ingress(SG_BILLING, WMS_SYNC_PORT, WMS_IPS[1] + "/32")

def test_billing_sg_ref_wms_03_revoked():
    assert not _sg_has_ingress(SG_BILLING, WMS_SYNC_PORT, WMS_IPS[2] + "/32")

def test_billing_sg_ref_wms_db_revoked():
    assert not _sg_has_ingress(SG_BILLING, WMS_DB_PORT, WMS_DB_IP + "/32")

def test_blackhole_route_to_retired_db_removed():
    t = _route_table(RT_APP)
    assert t is not None
    for r in t.get("RouteSet", []):
        if str(r.get("DestinationCidrBlock")) == WMS_DB_IP + "/32" and str(r.get("State")) == "blackhole":
            assert False, "blackhole route to the retired DB still present"

def test_eni_wms_01_deleted():
    assert WMS_IPS[0] not in _all_eni_ips()

def test_eni_wms_02_deleted():
    assert WMS_IPS[1] not in _all_eni_ips()

def test_eni_wms_03_deleted():
    assert WMS_IPS[2] not in _all_eni_ips()

def test_eni_wms_db_deleted():
    assert WMS_DB_IP not in _all_eni_ips()

def test_change_request_closed():
    rec = _change_state(CHG_SYS)
    state = str(rec.get("state")).strip().lower()
    assert state in ("3", "4", "closed", "closed complete") or bool(rec.get("close_code"))

def test_license_device_still_in_service():
    assert _in_service("wms-license-01")

def test_license_dns_a_present():
    assert any(str(r.get("name")) == "license." + DOMAIN and str(r.get("ipv4addr")) == LIC_VIP
               for r in _a_records())

def test_license_flexlm_cname_present():
    assert any(str(r.get("name")) == "flexlm." + DOMAIN for r in _cname_records())

def test_licensing_backend_present():
    assert "licensing-be" in _hap_backend_names()

def test_licensing_frontend_present():
    assert "licensing-fe" in _hap_frontend_names()

def test_license_sg_rule_preserved():
    assert _sg_has_ingress(SG_LICENSE, FLEXLM_PORT, APP_CIDR)

def test_license_eni_present():
    assert LIC_HOST_IP in _all_eni_ips()

def test_retired_subnet_route_table_present():
    t = _route_table(RT_LEGACY)
    assert t is not None and any(str(a.get("SubnetId")) == SUB_LEGACY
                                 for a in t.get("AssociationSet", []))

def test_licensing_service_dependency_intact():
    fb = next((s for s in _services() if str(s.get("name")) == "freight-billing"), None)
    assert fb is not None and "licensing" in (fb.get("depends_on") or [])
