import json
import urllib.error
import urllib.request

ZIA = "http://zscaler-zia.local.mock:8080/zia/api/v1"
DNS = "http://infoblox-nios.local.mock:8080/wapi/v2.14"
SN = "http://servicenow.local.mock:8080/api/now/table"

SG_STORE = 301
NS_HTTPS = 401
R_AUTH, R_TOKEN, R_SETTLE, R_OCSP, R_SCORE = 110, 111, 112, 113, 114
DG_AUTH, DG_TOKEN, DG_SETTLE, DG_OCSP, DG_SCORE = 201, 202, 203, 204, 205
DG_RESTRICTED = 209

AUTH_FQDN = "auth.cardinalpay.example"
TOKEN_FQDN = "token.cardinalpay.example"
SETTLE_FQDN = "settle.cardinalpay.example"
OCSP_FQDN = "ocsp.cardinal-ca.example"
SCORE_FQDN = "score.sentinelrisk.example"
LEGACY_FQDN = "cardinalpay-legacy.cardinalpay.example"

LIVE = {AUTH_FQDN: "203.0.113.10", TOKEN_FQDN: "203.0.113.20", SETTLE_FQDN: "203.0.113.30",
        OCSP_FQDN: "203.0.113.40", SCORE_FQDN: "198.51.100.50"}
PAY_LIVE_IPS = list(LIVE.values())
ORPHAN_DEAD_IP = "192.0.2.200"
LEGACY_DEAD_IP = "192.0.2.201"
INC_NUM = "INC0021001"

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    return json.loads(raw) if raw else None

def _rule(rid):
    return _get(ZIA + "/firewallFilteringRules/%d" % rid)

def _rules():
    r = _get(ZIA + "/firewallFilteringRules")
    return r if isinstance(r, list) else []

def _dest_group(gid):
    return _get(ZIA + "/ipDestinationGroups/%d" % gid)

def _refs_id_or_name(refs, wanted_id, wanted_name):
    for x in refs or []:
        if isinstance(x, dict):
            if str(x.get("id")) == str(wanted_id) or str(x.get("name")).lower() == wanted_name.lower():
                return True
        elif str(x) == str(wanted_id) or str(x).lower() == wanted_name.lower():
            return True
    return False

def _has_store_src(rid):
    r = _rule(rid) or {}
    return _refs_id_or_name(r.get("srcIpGroups"), SG_STORE, "Store-POS-Registers")

def _has_https(rid):
    r = _rule(rid) or {}
    return _refs_id_or_name(r.get("nwServices"), NS_HTTPS, "HTTPS")

def _enabled(rid):
    r = _rule(rid) or {}
    return str(r.get("state")).upper() == "ENABLED"

def _dg_ips(gid):
    g = _dest_group(gid) or {}
    return [str(ip) for ip in (g.get("ipAddresses") or [])]

def _dns(name):
    recs = _get(DNS + "/record:a")
    recs = recs if isinstance(recs, list) else []
    return [r for r in recs if str(r.get("name")) == name]

def _resolves_live(fqdn):
    recs = _dns(fqdn)
    return bool(recs) and all(str(r.get("ipv4addr")) == LIVE[fqdn] for r in recs)

def _incident_state():
    r = _get(SN + "/incident")
    rows = r if isinstance(r, list) else (r or {}).get("result", [])
    cur = next((i for i in rows if str(i.get("number")) == INC_NUM), None)
    return str(cur.get("state")) if cur else None

def test_auth_rule_enabled():
    assert _enabled(R_AUTH)

def test_settle_rule_enabled():
    assert _enabled(R_SETTLE)

def test_ocsp_rule_enabled():
    assert _enabled(R_OCSP)

def test_token_rule_has_store_source():
    assert _has_store_src(R_TOKEN)

def test_ocsp_rule_has_store_source():
    assert _has_store_src(R_OCSP)

def test_score_rule_has_store_source():
    assert _has_store_src(R_SCORE)

def test_auth_rule_has_https_service():
    assert _has_https(R_AUTH)

def test_settle_rule_has_https_service():
    assert _has_https(R_SETTLE)

def test_auth_dest_group_has_live_ip():
    assert LIVE[AUTH_FQDN] in _dg_ips(DG_AUTH)

def test_token_dest_group_has_live_ip():
    assert LIVE[TOKEN_FQDN] in _dg_ips(DG_TOKEN)

def test_settle_dest_group_has_live_ip():
    assert LIVE[SETTLE_FQDN] in _dg_ips(DG_SETTLE)

def test_ocsp_dest_group_has_live_ip():
    assert LIVE[OCSP_FQDN] in _dg_ips(DG_OCSP)

def test_score_dest_group_has_live_ip():
    assert LIVE[SCORE_FQDN] in _dg_ips(DG_SCORE)

def test_block_group_excludes_payment_ips():
    ips = _dg_ips(DG_RESTRICTED)
    assert all(ip not in ips for ip in PAY_LIVE_IPS)

def test_auth_dns_resolves_live():
    assert _resolves_live(AUTH_FQDN)

def test_token_dns_resolves_live():
    assert _resolves_live(TOKEN_FQDN)

def test_settle_dns_resolves_live():
    assert _resolves_live(SETTLE_FQDN)

def test_ocsp_dns_resolves_live():
    assert _resolves_live(OCSP_FQDN)

def test_score_dns_resolves_live():
    assert _resolves_live(SCORE_FQDN)

def test_orphan_rule_removed():
    bad = [r for r in _rules() if str(r.get("action")).upper() == "ALLOW"
           and str(r.get("state")).upper() == "ENABLED"
           and ORPHAN_DEAD_IP in [str(a) for a in (r.get("destAddresses") or [])]]
    assert not bad

def test_legacy_dns_record_cleaned():
    assert all(str(r.get("ipv4addr")) != LEGACY_DEAD_IP for r in _dns(LEGACY_FQDN))

def test_incident_closed():
    assert _incident_state() in ("6", "7")
