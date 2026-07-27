import json
import re
import urllib.error
import urllib.parse
import urllib.request

AWS = "http://aws-vpc.local.mock:8080/"
DNS = "http://infoblox-nios.local.mock:8080/wapi/v2.14"
D42 = "http://device42.local.mock:8080"
SN = "http://servicenow.local.mock:8080/api/now/table"
ZONE = "beacon.example"
FINDING_NUMBER = "INC0409001"

DANGLING_A = [
    "promo-fall", "promo-spring", "promo-winter", "launch-2024", "webinar-old", "landing-legacy",
    "microsite-old", "event-2023", "campaign-q1", "offer-old", "promo-2022", "promo-2021", "teaser-old",
    "preview-legacy", "splash-old", "giveaway-old", "survey-legacy", "beta-old", "holiday-2023",
    "roadshow-old",
    "app-old01", "app-old02", "worker-legacy", "batch-old", "cache-retired", "reporting-old", "queue-old",
    "etl-old", "indexer-old", "scheduler-old", "render-legacy", "ingest-old", "search-legacy", "media-old",
    "upload-legacy", "thumb-old",
    "legacy-lb", "old-edge", "stale-svc", "drained-node",
]
DANGLING_CNAME = [
    "shop-promo", "signup-old", "jobs-legacy", "cart-old", "dash-old", "media-legacy", "search-old",
    "render-old",
    "assets-legacy", "blog-old", "status-legacy", "ship-legacy", "docs-legacy", "help-old", "cdn-legacy",
    "api-legacy",
    "vanity-old", "promo-link", "go-legacy", "short-old", "link-legacy",
    "deep-old", "deep-legacy",
]
DANGLING_MX = ["send", "bounce", "notify", "news", "txn", "alerts"]
DANGLING_NS = ["eu", "apac", "archive", "labs", "sandbox", "demo"]

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        return {"_error": e.code}
    return json.loads(raw) if raw and raw.strip()[:1] in "{[" else raw

def _aws_set(action, setname):
    body = urllib.parse.urlencode({"Action": action}).encode()
    req = urllib.request.Request(AWS, data=body, method="POST",
                                 headers={"Accept": "application/json",
                                          "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode()
    node = ((json.loads(raw) if raw else {}) or {}).get(setname)
    if isinstance(node, dict) and isinstance(node.get("item"), list):
        return node["item"]
    return node if isinstance(node, list) else []

def _truthy(v):
    return v in (True, "true", "True", "yes", "1", 1)

def _eni_ips():
    ips = set()
    for e in _aws_set("DescribeNetworkInterfaces", "networkInterfaceSet"):
        if str(e.get("Status")) != "in-use":
            continue
        if e.get("PrivateIpAddress"):
            ips.add(str(e.get("PrivateIpAddress")))
        for pa in e.get("PrivateIpAddressesSet") or []:
            if pa.get("PrivateIpAddress"):
                ips.add(str(pa.get("PrivateIpAddress")))
    return ips

def _live_sets():
    eni_ips = _eni_ips()
    eip_ips = {str(a.get("PublicIp")) for a in _aws_set("DescribeAddresses", "addressesSet")}
    devices = ((_get(D42 + "/api/2.0/devices/") or {}).get("devices")) or []
    d42_live_ips = {str(d.get("ip")) for d in devices if d.get("ip") and _truthy(d.get("in_service"))}
    d42_by_name = {str(d.get("name")): d for d in devices}
    return eni_ips, eip_ips, d42_live_ips, d42_by_name

def _recs(rtype):
    recs = _get(DNS + "/record:" + rtype)
    return [r for r in (recs if isinstance(recs, list) else []) if isinstance(r, dict)]

def _ip_live(ip, sets):
    eni_ips, eip_ips, d42_live_ips, _ = sets
    ip = str(ip)
    return ip in eni_ips or ip in eip_ips or ip in d42_live_ips

def _resolve_live(target, a_by_name, cname_by_name, sets, seen=None):
    target = str(target)
    seen = seen or set()
    if target in seen:
        return False
    seen = seen | {target}
    if target in cname_by_name:
        return _resolve_live(cname_by_name[target], a_by_name, cname_by_name, sets, seen)
    if target in a_by_name:
        return _ip_live(a_by_name[target], sets)
    d = sets[3].get(target)
    return bool(d and _truthy(d.get("in_service")))

def _name_maps(sets):
    a_by_name = {str(r.get("name")): str(r.get("ipv4addr")) for r in _recs("a")}
    cname_by_name = {str(r.get("name")): str(r.get("canonical")) for r in _recs("cname")}
    return a_by_name, cname_by_name

def _a_remediated(host):
    name = host + "." + ZONE
    sets = _live_sets()
    return not any(str(r.get("name")) == name and not _ip_live(r.get("ipv4addr"), sets) for r in _recs("a"))

def _chain_remediated(host, rtype, field):
    name = host + "." + ZONE
    sets = _live_sets()
    a_by_name, cname_by_name = _name_maps(sets)
    return not any(str(r.get("name")) == name and not _resolve_live(r.get(field), a_by_name, cname_by_name, sets)
                   for r in _recs(rtype))

def _slug(name):
    return re.sub(r"[^0-9a-z]+", "_", name.lower()).strip("_")

def _make_a(host):
    def _t():
        assert _a_remediated(host)
    return _t

def _make_chain(host, rtype, field):
    def _t():
        assert _chain_remediated(host, rtype, field)
    return _t

for _h in DANGLING_A:
    globals()["test_dangling_a_%s_remediated" % _slug(_h)] = _make_a(_h)
for _h in DANGLING_CNAME:
    globals()["test_dangling_cname_%s_remediated" % _slug(_h)] = _make_chain(_h, "cname", "canonical")
for _h in DANGLING_MX:
    globals()["test_dangling_mx_%s_remediated" % _slug(_h)] = _make_chain(_h, "mx", "mail_exchanger")
for _h in DANGLING_NS:
    globals()["test_dangling_ns_%s_remediated" % _slug(_h)] = _make_chain(_h, "ns", "nameserver")

def test_finding_resolved():
    incs = _get(SN + "/incident")
    incs = incs.get("result", []) if isinstance(incs, dict) else incs
    rec = next((c for c in incs if str(c.get("number")) == FINDING_NUMBER), None)
    assert rec is not None
    state = str(rec.get("state")).strip().lower()
    assert state in ("6", "7", "resolved", "closed", "closed complete") or bool(rec.get("close_code"))

LIVE_A = [
    ("app01", "10.60.1.11"), ("app02", "10.60.1.12"), ("app03", "10.60.1.13"), ("api01", "10.60.1.21"),
    ("api02", "10.60.1.22"), ("db01", "10.60.2.11"), ("db02", "10.60.2.12"), ("cache01", "10.60.2.21"),
    ("cache02", "10.60.2.22"), ("worker01", "10.60.1.31"),
    ("www", "198.51.100.10"), ("api", "198.51.100.11"),
    ("partner-api", "203.0.113.50"), ("gw-ext", "203.0.113.51"),
    ("svc-mesh", "10.60.1.51"), ("metrics", "10.60.2.51"),
]
LIVE_CNAME = [
    ("cdn", "beacon.global-cdn.example"),
    ("shop", "app01." + ZONE), ("portal", "api01." + ZONE),
    ("admin", "app03." + ZONE), ("data", "db02." + ZONE),
    ("store", "shop." + ZONE), ("dashboard", "portal." + ZONE),
    ("deep-live", "store." + ZONE),
]
LIVE_MX = [
    ("mail", "aspmx.approved-mail.example"), ("inbound", "mx.corp-mail.example"),
    ("relay", "smtp.approved-relay.example"),
]
LIVE_NS = [
    ("dev", "ns1.approved-dns.example"), ("stage", "ns2.approved-dns.example"),
    ("qa", "ns1.approved-dns2.example"),
]
OOS_A = [
    ("legacy.partners.example", "203.0.113.90"),
    ("old.partners.example", "10.99.9.9"),
]
LIVE_EIP_IPS = ["198.51.100.10", "198.51.100.11"]
APPROVED_EXT = ["partner-payments-gateway", "partner-gateway-ext", "beacon.global-cdn.example",
                "aspmx.approved-mail.example", "mx.corp-mail.example", "smtp.approved-relay.example",
                "ns1.approved-dns.example", "ns2.approved-dns.example", "ns1.approved-dns2.example"]

def _slug(name):
    return re.sub(r"[^0-9a-z]+", "_", name.lower()).strip("_")

def _device_by_name(name):
    devices = ((_get(D42 + "/api/2.0/devices/") or {}).get("devices")) or []
    return next((d for d in devices if str(d.get("name")) == name), None)

def _a_records():
    return _recs("a")

def _cname_records():
    return _recs("cname")

def _sn_rows(table):
    return ((_get(SN + "/" + table) or {}).get("result")) or []

def _change_by_number(num):
    return next((r for r in _sn_rows("change_request") if str(r.get("number")) == num), None)

def _incident_by_number(num):
    return next((r for r in _sn_rows("incident") if str(r.get("number")) == num), None)

def _make_live_a(host, ip):
    full = host + "." + ZONE

    def _t():
        assert any(str(r.get("name")) == full and str(r.get("ipv4addr")) == ip for r in _a_records())
    return _t

def _make_live_cname(host, target):
    full = host + "." + ZONE

    def _t():
        assert any(str(r.get("name")) == full and str(r.get("canonical")) == target for r in _cname_records())
    return _t

def _make_oos_a(full, ip):
    def _t():
        assert any(str(r.get("name")) == full and str(r.get("ipv4addr")) == ip for r in _a_records())
    return _t

def _make_live_rec(host, target, rtype, field):
    full = host + "." + ZONE

    def _t():
        assert any(str(r.get("name")) == full and str(r.get(field)) == target for r in _recs(rtype))
    return _t

for _h, _ip in LIVE_A:
    globals()["test_live_a_%s_preserved" % _slug(_h)] = _make_live_a(_h, _ip)
for _h, _t in LIVE_CNAME:
    globals()["test_live_cname_%s_preserved" % _slug(_h)] = _make_live_cname(_h, _t)
for _h, _t in LIVE_MX:
    globals()["test_live_mx_%s_preserved" % _slug(_h)] = _make_live_rec(_h, _t, "mx", "mail_exchanger")
for _h, _t in LIVE_NS:
    globals()["test_live_ns_%s_preserved" % _slug(_h)] = _make_live_rec(_h, _t, "ns", "nameserver")
for _n, _ip in OOS_A:
    globals()["test_oos_%s_untouched" % _slug(_n)] = _make_oos_a(_n, _ip)

def test_live_eips_still_allocated():
    pubs = {str(a.get("PublicIp")) for a in _aws_set("DescribeAddresses", "addressesSet")}
    assert all(ip in pubs for ip in LIVE_EIP_IPS)

def test_approved_external_deps_in_service():
    assert all((_device_by_name(n) or {}).get("in_service") not in (False, "false", "no", "0")
               and _device_by_name(n) is not None for n in APPROVED_EXT)

def test_decoy_migration_change_untouched():
    rec = _change_by_number("CHG0407090")
    assert rec is not None and str(rec.get("state")) == "3"

def test_unrelated_incident_untouched():
    rec = _incident_by_number("INC0409044")
    assert rec is not None and str(rec.get("state")) == "2" and not rec.get("close_code")
