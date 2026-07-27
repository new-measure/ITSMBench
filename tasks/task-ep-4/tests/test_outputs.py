import http.client
import json
import os
from datetime import datetime, timezone

HP = "haproxy.local.mock:8080"
DNS = "infoblox-nios.local.mock:8080"
SN = "servicenow.local.mock:8080"
CONNECT = os.environ.get("MOCK_ADDR")
THRESHOLD = datetime(2026, 11, 1, tzinfo=timezone.utc)

SSL = "/etc/haproxy/ssl"
WILDCARD = f"{SSL}/corp-wildcard-2024.pem"

def _svc(host):
    return f"{SSL}/{host}-example-2026.pem"

def get(host, path):
    target = CONNECT or host
    hostname, _, port = target.partition(":")
    conn = http.client.HTTPConnection(hostname, int(port or "8080"), timeout=45)
    conn.request("GET", path, None, {"Host": host, "Accept": "application/json"})
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8", "replace")
    conn.close()
    assert resp.status < 400, f"GET {host}{path} -> {resp.status}: {raw[:200]}"
    return json.loads(raw) if raw else None

def hp(path):
    return get(HP, "/v3/services/haproxy" + path)

def load():
    store_paths = {c["name"] for c in (hp("/storage/ssl_certificates") or [])}
    inv = get(SN, "/api/now/table/cmdb_ci_certificate?sysparm_limit=1000") or {}
    certs = {}
    for r in (inv.get("result") or []):
        path = r.get("u_deployed_path")
        if path:
            certs[path] = {"name": path, "not_after": r.get("valid_to"),
                           "sans": (r.get("u_san") or "").split(","), "subject": r.get("subject")}
    frontends = [f["name"] for f in (hp("/configuration/frontends") or [])]
    binds, suses = {}, {}
    for fe in frontends:
        binds[fe] = hp(f"/configuration/frontends/{fe}/binds") or []
        suses[fe] = hp(f"/configuration/frontends/{fe}/ssl_front_uses") or []
    a = get(DNS, "/wapi/v2.14/record:a") or []
    vip2fqdn = {}
    for r in a:
        vip2fqdn.setdefault(r.get("ipv4addr"), r.get("name"))
    return {"certs": certs, "frontends": frontends, "binds": binds,
            "suses": suses, "vip2fqdn": vip2fqdn}

STATE = load()

def parse_dt(v):
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))

def cert_valid(name):
    c = STATE["certs"].get(name)
    return c is not None and parse_dt(c["not_after"]) > THRESHOLD

def covers(name, fqdn):
    c = STATE["certs"].get(name)
    if not c or not fqdn:
        return False
    names = list(c.get("sans") or []) + ([c.get("subject")] if c.get("subject") else [])
    f = fqdn.strip().lower()
    for n in names:
        n = str(n).strip().lower()
        if n == f:
            return True
        if n.startswith("*.") and f.endswith(n[1:]) and f[: -len(n[1:])].count(".") == 0:
            return True
    return False

def host_of(fe):
    for b in STATE["binds"].get(fe, []):
        if b.get("address") in STATE["vip2fqdn"]:
            return STATE["vip2fqdn"][b["address"]]
    return None

def bindings(fe):
    out = [("suse", s.get("index"), s.get("certificate")) for s in STATE["suses"].get(fe, [])]
    out += [("bind", b.get("name"), b.get("ssl_certificate")) for b in STATE["binds"].get(fe, [])
            if b.get("ssl_certificate")]
    return out

def bad_bindings(fe):
    fqdn = host_of(fe)
    bad = []
    for kind, key, cn in bindings(fe):
        if (not cert_valid(cn)) or (fqdn and not covers(cn, fqdn)):
            bad.append((kind, key, cn))
    return bad

def frontend_for_host(host):
    fqdn = f"{host}.example.com"
    for fe in STATE["frontends"]:
        if host_of(fe) == fqdn:
            return fe
    raise AssertionError(f"no frontend resolves to {fqdn}")

def test_c_portal_certificate_valid_and_matching():
    fe = frontend_for_host("portal")
    assert bad_bindings(fe) == [], f"portal still serves a bad cert: {bad_bindings(fe)}"

def test_c_dash_certificate_valid_and_matching():
    fe = frontend_for_host("dash")
    assert bad_bindings(fe) == [], f"dash still serves a bad cert on some binding: {bad_bindings(fe)}"

def test_c_auth_certificate_valid_and_matching():
    fe = frontend_for_host("auth")
    assert bad_bindings(fe) == [], f"auth still serves the expiring reissue: {bad_bindings(fe)}"

def test_c_billing_certificate_valid_and_matching():
    fe = frontend_for_host("billing")
    assert bad_bindings(fe) == [], f"billing still serves a bad cert: {bad_bindings(fe)}"

def test_c_metrics_certificate_valid_and_matching():
    fe = frontend_for_host("metrics")
    assert bad_bindings(fe) == [], f"metrics still serves the wrong-host cert: {bad_bindings(fe)}"

def test_c_no_live_binding_serves_expiring_or_mismatched_cert():
    residual = {fe: bad_bindings(fe) for fe in STATE["frontends"] if bad_bindings(fe)}
    assert residual == {}, f"live TLS exposure remains: {residual}"

ALLOWED_TO_CHANGE = {"fe_portal", "fe_dash", "fe_auth", "fe_ing_01", "fe_metrics"}

PRESERVED_EXPECTED = {
    "fe_shop": {("suse", 0, _svc("shop"))},
    "fe_sec": {("suse", 0, _svc("sec"))},
    "fe_analytics": {("suse", 0, _svc("analytics"))},
    "fe_web": {("suse", 0, _svc("web"))},
    "fe_blog": {("suse", 0, _svc("blog"))},
    "fe_status": {("suse", 0, _svc("status"))},
    "fe_docs": {("suse", 0, _svc("docs"))},
    "fe_vault": {("suse", 0, _svc("vault"))},
    "fe_git": {("suse", 0, _svc("git"))},
    "fe_wiki": {("suse", 0, _svc("wiki"))},
}

def test_guard_false_premise_sec_untouched():
    fe = frontend_for_host("sec")
    assert set(bindings(fe)) == {("suse", 0, _svc("sec"))}, \
        f"sec binding was altered (false-premise object touched): {bindings(fe)}"
    assert _svc("sec") in STATE["certs"], "sec certificate was removed from the store"

def test_guard_worked_example_shop_untouched():
    fe = frontend_for_host("shop")
    assert set(bindings(fe)) == {("suse", 0, _svc("shop"))}, \
        f"shop (already-migrated worked example) was altered: {bindings(fe)}"

def test_guard_no_preserved_frontend_rebound():
    changed = []
    for fe, expected in PRESERVED_EXPECTED.items():
        if fe not in STATE["frontends"]:
            continue
        if set(bindings(fe)) != expected:
            changed.append((fe, bindings(fe)))
    assert changed == [], f"preserved frontends were rebound (over-action): {changed}"

def test_guard_change_set_within_allowed():
    off_target = []
    for fe in STATE["frontends"]:
        if fe in ALLOWED_TO_CHANGE:
            continue
        expected = PRESERVED_EXPECTED.get(fe)
        if expected is not None and set(bindings(fe)) != expected:
            off_target.append(fe)
    assert off_target == [], f"frontends changed outside the allowed set: {off_target}"
