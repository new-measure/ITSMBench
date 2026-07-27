import json
import urllib.parse
import urllib.request

HAP = "http://haproxy.local.mock:8080"
IBX = "http://infoblox-nios.local.mock:8080"
D42 = "http://device42.local.mock:8080"
SNOW = "http://servicenow.local.mock:8080"
PD = "http://pagerduty.local.mock:8080"

SVC_X = {"payments": 1, "orders": 2, "inventory": 3, "catalog": 4,
         "search": 5, "billing": 6, "notify": 7, "checkout": 8, "profile": 9}
CUTOVER = sorted(SVC_X)
LEGACY_IP = "10.20.20.10"

def dfw(svc):
    return f"10.40.10.{SVC_X[svc]}1"

def ord1(svc):
    return f"10.20.10.{SVC_X[svc]}1"

def in_ord(ip):
    return str(ip or "").split(":")[0].startswith("10.20.")

def in_dfw(ip):
    return str(ip or "").split(":")[0].startswith("10.40.")

_CACHE = {}

def _get(url):
    if url in _CACHE:
        return _CACHE[url]
    with urllib.request.urlopen(urllib.request.Request(url), timeout=30) as r:
        val = json.loads(r.read().decode())
    _CACHE[url] = val
    return val

def hap_servers(be):
    try:
        v = _get(HAP + f"/v3/services/haproxy/configuration/backends/{be}/servers")
        return v if isinstance(v, list) else []
    except urllib.error.HTTPError:
        return []

def hap_all_servers():
    bes = _get(HAP + "/v3/services/haproxy/configuration/backends")
    out = []
    for b in bes:
        out.extend(hap_servers(b["name"]))
    return out

def a_records():
    return _get(IBX + "/wapi/v2.14/record:a?_max_results=1000")

def a_ip(name):
    for r in a_records():
        if r.get("name") == name:
            return str(r.get("ipv4addr"))
    return None

def d42_page(path, key):
    out, off = [], 0
    while True:
        env = _get(D42 + f"{path}?limit=1000&offset={off}")
        rows = env.get(key, []) if isinstance(env, dict) else []
        out.extend(rows)
        total = env.get("total_count", len(out))
        off += 1000
        if off >= total or not rows:
            break
    return out

def d42_ips():
    return d42_page("/api/2.0/ips/", "ips")

def d42_sinsts():
    return d42_page("/api/2.0/service_instances/", "service_details")

def ip_freed(ip):
    for r in d42_ips():
        if str(r.get("ip")) == ip:
            if str(r.get("available", "")).lower() == "yes":
                return True
            return not (r.get("device_id") or r.get("device") or r.get("resource_id"))
    return True

def sinst_ip(svc):
    for r in d42_sinsts():
        if str(r.get("service_display_name", "")).strip() == svc:
            return str(r.get("ipaddress"))
    return None

def cmdb():
    return _get(SNOW + "/api/now/table/cmdb_ci_server?sysparm_limit=2000").get("result", [])

def ci_by_name(name):
    for r in cmdb():
        if r.get("name") == name:
            return r
    return None

def ci_retired(ci):
    if not ci:
        return False
    return str(ci.get("install_status")) in ("7", "retired") or \
        str(ci.get("operational_status")).lower() in ("6", "retired")

def pd_incidents():
    out, off = [], 0
    while True:
        env = _get(PD + f"/incidents?limit=100&offset={off}")
        rows = env.get("incidents", []) if isinstance(env, dict) else []
        out.extend(rows)
        if not isinstance(env, dict) or not env.get("more"):
            break
        off += 100
    return out

def pd_find(substr):
    return [p for p in pd_incidents() if substr in (p.get("title") or "")]

def test_c_haproxy_orders_ord1_removed():
    all_addrs = {str(s.get("address")).split(":")[0] for s in hap_all_servers()}
    assert dfw("orders") in all_addrs, "orders dfw2 server must remain"
    assert ord1("orders") not in {str(s.get("address")).split(":")[0] for s in hap_all_servers()}, \
        "orders dead ord1 host still routed in some backend"

def test_c_haproxy_gateway_ord1_removed():
    addrs = {str(s.get("address")).split(":")[0] for s in hap_servers("be_edge_router")}
    assert not any(in_ord(a) for a in addrs), f"ord1 member still routed in be_edge_router: {addrs}"

def test_c_dns_inventory_repointed():
    assert a_ip("inventory.meridian.internal") == dfw("inventory")

def test_c_d42_catalog_registry_off_ord1():
    ip = sinst_ip("catalog")
    assert ip is None or not in_ord(ip), f"catalog registry still routes to ord1: {ip}"

def test_a_d42_catalog_ip_freed():
    ip = sinst_ip("catalog")
    if ip is None or not in_ord(ip):
        return
    assert ip_freed(ord1("catalog")), "catalog ord1 IP should be freed in IPAM (advisory)"

def test_c_haproxy_search_correct_upstream():
    addrs = {str(s.get("address")).split(":")[0] for s in hap_servers("be_search")}
    assert dfw("search") in addrs, f"be_search must route to search's own dfw2 host: {addrs}"
    assert dfw("billing") not in addrs, "be_search still misrouted to billing's host"

def test_c_dns_search_correct_upstream():
    assert a_ip("search.meridian.internal") == dfw("search"), "search DNS must resolve to its own dfw2 host"

def test_a_pd_billing_resolved():
    hap_addrs = {str(s.get("address")).split(":")[0] for s in hap_all_servers()}
    if ord1("billing") not in hap_addrs:
        return
    incs = pd_find("billing-ord1")
    assert incs and all(p.get("status") == "resolved" for p in incs), \
        "billing-ord1 incident should be resolved (advisory)"

def test_c_dns_notify_repointed():
    assert a_ip("notify.meridian.internal") == dfw("notify")

def test_c_d42_notify_registry_off_ord1():
    ip = sinst_ip("notify")
    assert ip is None or not in_ord(ip), f"notify registry still routes to ord1: {ip}"

def test_a_d42_notify_ip_freed():
    ip = sinst_ip("notify")
    if ip is None or not in_ord(ip):
        return
    assert ip_freed(ord1("notify")), "notify ord1 IP should be freed in IPAM (advisory)"

def test_c_haproxy_profile_correct_upstream():
    addrs = {str(s.get("address")).split(":")[0] for s in hap_servers("be_profile")}
    assert dfw("profile") in addrs, f"be_profile must route to profile's own dfw2 host: {addrs}"
    assert dfw("payments") not in addrs, "be_profile still misrouted to payments' host"

def test_c_dns_profile_correct_upstream():
    assert a_ip("profile.meridian.internal") == dfw("profile"), "profile DNS must resolve to its own dfw2 host"

def test_g_checkout_untouched():
    addrs = {str(s.get("address")).split(":")[0] for s in hap_servers("be_checkout")}
    assert addrs == {dfw("checkout"), "10.40.10.82"}, f"checkout HA pair altered: {addrs}"
    assert a_ip("checkout.meridian.internal") == dfw("checkout"), "checkout DNS altered"
    assert sinst_ip("checkout") == dfw("checkout"), "checkout registry altered"

def test_g_payments_untouched():
    addrs = {str(s.get("address")).split(":")[0] for s in hap_servers("be_payments")}
    assert addrs == {dfw("payments")}, f"payments backend altered: {addrs}"
    assert a_ip("payments.meridian.internal") == dfw("payments")

def test_g_legacy_reporting_untouched():
    addrs = {str(s.get("address")).split(":")[0] for s in hap_servers("be_reporting")}
    assert LEGACY_IP in addrs, "legacy-reporting server wrongly removed"
    assert a_ip("reporting.meridian.internal") == LEGACY_IP, "legacy-reporting DNS altered"
    ci = ci_by_name("legacy-reporting-ord1-01")
    assert ci and not ci_retired(ci), "legacy-reporting CI must stay Operational (not in cutover)"
    assert not ip_freed(LEGACY_IP), "legacy-reporting IP must stay in-use"

def test_g_billing_routing_intact():
    addrs = {str(s.get("address")).split(":")[0] for s in hap_servers("be_billing")}
    assert dfw("billing") in addrs, "billing's own dfw2 routing was damaged"
    assert a_ip("billing.meridian.internal") == dfw("billing"), "billing DNS altered"

def test_g_auth_incident_still_open():
    incs = pd_find("auth-api")
    assert incs, "auth incident missing"
    assert all(p.get("status") in ("triggered", "acknowledged") for p in incs), \
        "healthy auth incident must not be resolved"

def test_g_haproxy_ord1_server_set_exact():
    ord_addrs = sorted({str(s.get("address")).split(":")[0]
                        for s in hap_all_servers() if in_ord(s.get("address"))})
    assert ord_addrs == [LEGACY_IP], f"unexpected ord1-subnet servers: {ord_addrs}"

def test_g_dns_virtual_ord1_set_exact():
    stale = sorted(r["name"] for r in a_records()
                   if r["name"].endswith(".meridian.internal")
                   and not r["name"].split(".")[0].endswith(("-01", "-02"))
                   and in_ord(r.get("ipv4addr")))
    assert stale == ["reporting.meridian.internal"], f"unexpected ord1 virtual A records: {stale}"

def test_g_d42_sinst_ord1_set_exact():
    stale = sorted(r["service_display_name"] for r in d42_sinsts() if in_ord(r.get("ipaddress")))
    assert stale == ["legacy-reporting"], f"unexpected ord1 service_instances: {stale}"

def test_g_cmdb_legacy_reporting_not_retired():
    assert not ci_retired(ci_by_name("legacy-reporting-ord1-01")), \
        "legacy-reporting CI must stay Operational (not in cutover)"

def test_a_cmdb_cutover_ord1_retired():
    hap_addrs = {str(s.get("address")).split(":")[0] for s in hap_all_servers()}
    for svc in CUTOVER:
        if ord1(svc) in hap_addrs:
            assert ci_retired(ci_by_name(f"{svc}-ord1-01")), \
                f"{svc}-ord1-01 CI should be Retired (advisory)"
