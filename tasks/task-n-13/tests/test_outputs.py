import json
import urllib.error
import urllib.request

DNS = "http://infoblox-nios.local.mock:8080/wapi/v2.14"
SN = "http://servicenow.local.mock:8080/api/now/table"

DOMAIN = "meridian.example"
APPS = "apps." + DOMAIN
INTERNAL = "internal"
INC_SYS = "2e31b68847d76a4d2e68c219abab4e2a"

VIP = {
    "billing": "10.20.1.10", "orders": "10.20.1.11", "reports": "10.20.1.12",
    "inventory": "10.20.1.13", "api": "10.20.1.14", "auth": "10.20.1.15",
    "payments": "10.20.1.16", "search": "10.20.1.17", "catalog": "10.20.1.18",
    "messaging": "10.20.1.19",
}
NS_IPS = {"10.20.0.11", "10.20.0.12"}
PEER_VIP = {"directory": "10.20.1.20", "identity": "10.20.1.21"}
LIVE_INTERNAL = set(VIP.values()) | set(PEER_VIP.values()) | NS_IPS
ALIAS = {
    "billing-web." + APPS: "billing", "orders-web." + APPS: "orders",
    "reports-web." + APPS: "reports", "catalog-web." + APPS: "catalog",
    "messaging-web." + APPS: "messaging", "shop." + APPS: "search", "portal." + APPS: "api",
}

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode()
    return json.loads(raw) if raw else None

def _rows(kind):
    r = _get(DNS + "/" + kind)
    return r if isinstance(r, list) else []

def _a_internal(name):
    return [r for r in _rows("record:a") if str(r.get("name")) == name and str(r.get("view")) == INTERNAL]

def _cname_internal(name):
    return [r for r in _rows("record:cname") if str(r.get("name")) == name and str(r.get("view")) == INTERNAL]

def _ns_internal(name):
    return [r for r in _rows("record:ns") if str(r.get("name")) == name and str(r.get("view")) == INTERNAL]

def _resolves_internal_live(name, depth=0):
    if depth > 8:
        return False
    a = _a_internal(name)
    if a and all(str(r.get("ipv4addr")) in LIVE_INTERNAL for r in a):
        return True
    c = _cname_internal(name)
    if c:
        return all(_resolves_internal_live(str(r.get("canonical")), depth + 1) for r in c)
    return False

def _nameserver_live(ns_host):
    a = _a_internal(ns_host)
    return bool(a) and all(str(r.get("ipv4addr")) in LIVE_INTERNAL for r in a)

def _incident_state(sys_id):
    r = _get(SN + "/incident/" + sys_id)
    rec = (r or {}).get("result") if isinstance(r, dict) else None
    return str((rec or {}).get("state")) if rec else None

def _service_internal_ok(svc):
    recs = _a_internal(svc + "." + APPS)
    return bool(recs) and all(str(r.get("ipv4addr")) == VIP[svc] for r in recs)

def test_billing_internal_a():
    assert _service_internal_ok("billing")

def test_orders_internal_a():
    assert _service_internal_ok("orders")

def test_reports_internal_a():
    assert _service_internal_ok("reports")

def test_catalog_internal_a():
    assert _service_internal_ok("catalog")

def test_messaging_internal_a():
    assert _service_internal_ok("messaging")

def test_inventory_internal_a():
    assert _service_internal_ok("inventory")

def test_search_internal_a():
    assert _service_internal_ok("search")

def test_api_internal_a():
    assert _service_internal_ok("api")

def test_auth_internal_a():
    assert _service_internal_ok("auth")

def test_payments_internal_a():
    assert _service_internal_ok("payments")

def test_billing_web_alias_resolves():
    assert _resolves_internal_live("billing-web." + APPS)

def test_orders_web_alias_resolves():
    assert _resolves_internal_live("orders-web." + APPS)

def test_reports_web_alias_resolves():
    assert _resolves_internal_live("reports-web." + APPS)

def test_catalog_web_alias_resolves():
    assert _resolves_internal_live("catalog-web." + APPS)

def test_messaging_web_alias_resolves():
    assert _resolves_internal_live("messaging-web." + APPS)

def test_shop_alias_resolves():
    assert _resolves_internal_live("shop." + APPS)

def test_portal_alias_resolves():
    assert _resolves_internal_live("portal." + APPS)

def test_apps_delegation_has_live_ns():
    ns = _ns_internal(APPS)
    assert ns and any(_nameserver_live(str(r.get("nameserver"))) for r in ns)

def test_apps_delegation_no_dead_ns():
    ns = _ns_internal(APPS)
    assert ns and all(_nameserver_live(str(r.get("nameserver"))) for r in ns)

def test_legacy_portal_a_cleaned():
    recs = _a_internal("legacy-portal." + APPS)
    assert all(str(r.get("ipv4addr")) != "10.10.1.90" for r in recs)

def test_old_auth_cname_cleaned():
    recs = _cname_internal("old-auth." + APPS)
    assert len(recs) == 0 or _resolves_internal_live("old-auth." + APPS)

def test_beta_delegation_cleaned():
    ns = _ns_internal("beta.apps." + DOMAIN)
    assert len(ns) == 0 or all(_nameserver_live(str(r.get("nameserver"))) for r in ns)

def test_incident_closed():
    assert _incident_state(INC_SYS) in ("6", "7")
