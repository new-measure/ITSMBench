import json
import urllib.error
import urllib.request

HAP = "http://haproxy.local.mock:8080/v3/services/haproxy/configuration"
DNS = "http://infoblox-nios.local.mock:8080/wapi/v2.14"
D42 = "http://device42.local.mock:8080"
SN = "http://servicenow.local.mock:8080/api/now/table"

CERT_EXPIRED = "wildcard-meridian-2025.pem"
CERT_VALID = "wildcard-meridian-2026.pem"
DEAD_DELEG = "acme-dns-2025"
LIVE_DELEG = "acme-dns-2026"
DOMAIN = "meridian-retail.example"

BIND_AFFECTED = ["shop", "checkout", "account", "api", "catalog"]
CRTLIST_AFFECTED = ["webhooks"]
AFFECTED = BIND_AFFECTED + CRTLIST_AFFECTED
DNS_STALE = ["shop", "checkout", "account"]

INC_SYS = "35c86fa1865b2e04acd513e722eb63ee"
RETIRED_STATUS = {"retired", "expired", "replaced", "revoked", "inactive", "decommissioned",
                  "superseded", "not in use", "removed"}
DEPLOYED_STATUS = {"deployed", "active", "in service", "in use", "current", "live", "installed"}

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode()
    return json.loads(raw) if raw else None

def _truthy(v):
    return v is True or str(v).strip().lower() in ("true", "1", "yes", "y")

def _frontends():
    r = _get(HAP + "/frontends")
    return [str(f.get("name")) for f in (r if isinstance(r, list) else [])]

def _bind_cert(fe):
    r = _get(HAP + "/frontends/%s/binds" % fe)
    for b in (r if isinstance(r, list) else []):
        if b.get("ssl_certificate") is not None:
            return str(b.get("ssl_certificate"))
    return None

def _frontuse_certs(fe):
    r = _get(HAP + "/frontends/%s/ssl_front_uses" % fe)
    return [str(u.get("certificate")) for u in (r if isinstance(r, list) else [])]

def _presents_valid_only(fe):
    certs = set()
    r = _get(HAP + "/frontends/%s/binds" % fe)
    for b in (r if isinstance(r, list) else []):
        if b.get("ssl_certificate") is not None:
            certs.add(str(b.get("ssl_certificate")))
    certs |= set(_frontuse_certs(fe))
    return CERT_VALID in certs and CERT_EXPIRED not in certs

def _all_bind_certs():
    out = []
    for fe in _frontends():
        r = _get(HAP + "/frontends/%s/binds" % fe)
        for b in (r if isinstance(r, list) else []):
            if b.get("ssl_certificate") is not None:
                out.append(str(b.get("ssl_certificate")))
    return out

def _all_frontuse_certs():
    out = []
    for fe in _frontends():
        out += _frontuse_certs(fe)
    return out

def _cname(short):
    recs = _get(DNS + "/record:cname")
    recs = recs if isinstance(recs, list) else []
    name = "_acme-challenge." + short + "." + DOMAIN
    return [str(r.get("canonical")) for r in recs if str(r.get("name")) == name]

def _all_acme_canonicals():
    recs = _get(DNS + "/record:cname")
    recs = recs if isinstance(recs, list) else []
    return [str(r.get("canonical")) for r in recs if str(r.get("name")).startswith("_acme-challenge.")]

def _d42_certs():
    d = _get(D42 + "/api/1.0/software/license_keys/") or {}
    return d.get("software_license_keys") or []

def _cert_by_name(name):
    return next((c for c in _d42_certs() if str(c.get("license_key")) == name), None)

def _d42_services():
    d = _get(D42 + "/api/2.0/services/") or {}
    return d.get("services") or []

def _svc(sid):
    return next((s for s in _d42_services() if str(s.get("id")) == sid), None)

def _incident():
    r = _get(SN + "/incident/" + INC_SYS)
    return (r or {}).get("result") if isinstance(r, dict) else None

def _cert_out_of_service(c):
    return c is not None and (not _truthy(c.get("in_service")) or str(c.get("status", "")).lower() in RETIRED_STATUS)

def _cert_deployed(c):
    return c is not None and (_truthy(c.get("in_service")) or str(c.get("status", "")).lower() in DEPLOYED_STATUS)

def _acme_fixed(canonical):
    return DEAD_DELEG not in canonical and LIVE_DELEG in canonical

def test_fe_shop_on_valid_cert():
    assert _presents_valid_only("fe_shop")

def test_fe_checkout_on_valid_cert():
    assert _presents_valid_only("fe_checkout")

def test_fe_account_on_valid_cert():
    assert _presents_valid_only("fe_account")

def test_fe_api_on_valid_cert():
    assert _presents_valid_only("fe_api")

def test_fe_catalog_on_valid_cert():
    assert _presents_valid_only("fe_catalog")

def test_fe_webhooks_on_valid_cert():
    assert _presents_valid_only("fe_webhooks")

def test_no_bind_still_presents_expired_cert():
    assert CERT_EXPIRED not in _all_bind_certs()

def test_no_crtlist_still_presents_expired_cert():
    assert CERT_EXPIRED not in _all_frontuse_certs()

def test_acme_shop_repointed_live():
    c = _cname("shop")
    assert bool(c) and all(_acme_fixed(x) for x in c)

def test_acme_checkout_repointed_live():
    c = _cname("checkout")
    assert bool(c) and all(_acme_fixed(x) for x in c)

def test_acme_account_repointed_live():
    c = _cname("account")
    assert bool(c) and all(_acme_fixed(x) for x in c)

def test_no_acme_cname_references_decommissioned_validator():
    assert all(DEAD_DELEG not in x for x in _all_acme_canonicals())

def test_cmdb_expired_cert_out_of_service():
    assert _cert_out_of_service(_cert_by_name(CERT_EXPIRED))

def test_cmdb_valid_cert_deployed():
    assert _cert_deployed(_cert_by_name(CERT_VALID))

def test_cmdb_shop_bound_to_valid():
    assert str((_svc("svc-shop") or {}).get("bound_certificate")) == CERT_VALID

def test_cmdb_checkout_bound_to_valid():
    assert str((_svc("svc-checkout") or {}).get("bound_certificate")) == CERT_VALID

def test_cmdb_account_bound_to_valid():
    assert str((_svc("svc-account") or {}).get("bound_certificate")) == CERT_VALID

def test_cmdb_api_bound_to_valid():
    assert str((_svc("svc-api") or {}).get("bound_certificate")) == CERT_VALID

def test_cmdb_catalog_bound_to_valid():
    assert str((_svc("svc-catalog") or {}).get("bound_certificate")) == CERT_VALID

def test_cmdb_webhooks_bound_to_valid():
    assert str((_svc("svc-webhooks") or {}).get("bound_certificate")) == CERT_VALID

def test_cmdb_no_service_still_bound_to_expired():
    assert all(str(s.get("bound_certificate")) != CERT_EXPIRED for s in _d42_services())

def test_incident_resolved():
    inc = _incident()
    assert inc is not None and str(inc.get("state")) in ("6", "7")

def test_incident_documented():
    inc = _incident()
    assert inc is not None and str(inc.get("close_notes") or "").strip() != ""
