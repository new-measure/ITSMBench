import json
import urllib.error
import urllib.request

HAP = "http://haproxy.local.mock:8080/v3/services/haproxy/configuration"
HAP_RT = "http://haproxy.local.mock:8080/v3/services/haproxy/runtime"
SN = "http://servicenow.local.mock:8080/api/now/table"

INC_SYS = "bd4b4e4e43c34f1e2b2e59b13ed36db8"

FE_MAXCONN = 65536
SRV_MAXCONN = 2000
CHK_INTER = 2000
CHK_FALL = 3

WEIGHT0 = [("be_api_app", "app-2"), ("be_api_app", "app-4"), ("be_api_app", "app-6"),
           ("be_api_search", "srch-3"), ("be_api_search", "srch-8"), ("be_api_media", "media-2"),
           ("be_api_media", "media-7"), ("be_api_ws", "ws-4")]
MAXCONN_LOW = [("be_api_app", "app-3"), ("be_api_app", "app-7"), ("be_api_app", "app-10"),
               ("be_api_search", "srch-1"), ("be_api_search", "srch-2"), ("be_api_media", "media-1"),
               ("be_api_ws", "ws-1")]
HEALTH_AGGR = [("be_api_app", "app-1"), ("be_api_app", "app-5"), ("be_api_search", "srch-4"),
               ("be_api_search", "srch-7"), ("be_api_media", "media-4"), ("be_api_media", "media-8"),
               ("be_api_ws", "ws-7")]
CHECK_OFF = [("be_api_app", "app-8"), ("be_api_search", "srch-5"), ("be_api_media", "media-5"),
             ("be_api_media", "media-6"), ("be_api_ws", "ws-2")]
BALANCE_BROKEN = ["be_api_app", "be_api_search", "be_api_media"]
DRIFT_DRAINED = [("be_api_app", "app-4"), ("be_api_search", "srch-2"), ("be_api_media", "media-5"),
                 ("be_api_ws", "ws-3")]

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError:
        return None
    return json.loads(raw) if raw else None

def _server(be, name):
    return _get(HAP + "/backends/%s/servers/%s" % (be, name))

def _backend(be):
    return _get(HAP + "/backends/%s" % be)

def _runtime_admin(be, name):
    rec = _get(HAP_RT + "/backends/%s/servers/%s" % (be, name))
    return str((rec or {}).get("admin_state")) if isinstance(rec, dict) else None

def _frontend_maxconn(name):
    rec = _get(HAP + "/frontends/%s" % name)
    if not isinstance(rec, dict):
        return None
    v = rec.get("maxconn")
    return int(v) if isinstance(v, (int, float)) or (isinstance(v, str) and str(v).isdigit()) else None

def _incident():
    r = _get(SN + "/incident/" + INC_SYS)
    return (r or {}).get("result") if isinstance(r, dict) else None

def _weight_ok(s):
    if not isinstance(s, dict):
        return False
    w = s.get("weight")
    return isinstance(w, (int, float)) and 64 <= int(w) <= 512

def _maxconn_ok(s):
    if not isinstance(s, dict):
        return False
    m = s.get("maxconn")
    return isinstance(m, (int, float)) and (int(m) == 0 or int(m) >= SRV_MAXCONN)

def _health_ok(s):
    if not isinstance(s, dict):
        return False
    inter = s.get("inter")
    fall = s.get("fall")
    return (isinstance(inter, (int, float)) and int(inter) >= 1000
            and isinstance(fall, (int, float)) and int(fall) >= 2)

def _check_ok(s):
    if not isinstance(s, dict):
        return False
    return str(s.get("check")).strip().lower() in ("enabled", "true", "1", "yes")

def _balance_ok(be):
    if not isinstance(be, dict):
        return False
    alg = str((be.get("balance") or {}).get("algorithm") or "").strip().lower()
    return alg not in ("", "first", "static-rr")

def test_fe_api_maxconn_restored():
    assert (_frontend_maxconn("fe_api") or 0) >= FE_MAXCONN

def test_weight_app2_restored():
    assert _weight_ok(_server("be_api_app", "app-2"))

def test_weight_app4_restored():
    assert _weight_ok(_server("be_api_app", "app-4"))

def test_weight_app6_restored():
    assert _weight_ok(_server("be_api_app", "app-6"))

def test_weight_srch3_restored():
    assert _weight_ok(_server("be_api_search", "srch-3"))

def test_weight_srch8_restored():
    assert _weight_ok(_server("be_api_search", "srch-8"))

def test_weight_media2_restored():
    assert _weight_ok(_server("be_api_media", "media-2"))

def test_weight_media7_restored():
    assert _weight_ok(_server("be_api_media", "media-7"))

def test_weight_ws4_restored():
    assert _weight_ok(_server("be_api_ws", "ws-4"))

def test_maxconn_app3_restored():
    assert _maxconn_ok(_server("be_api_app", "app-3"))

def test_maxconn_app7_restored():
    assert _maxconn_ok(_server("be_api_app", "app-7"))

def test_maxconn_app10_restored():
    assert _maxconn_ok(_server("be_api_app", "app-10"))

def test_maxconn_srch1_restored():
    assert _maxconn_ok(_server("be_api_search", "srch-1"))

def test_maxconn_srch2_restored():
    assert _maxconn_ok(_server("be_api_search", "srch-2"))

def test_maxconn_media1_restored():
    assert _maxconn_ok(_server("be_api_media", "media-1"))

def test_maxconn_ws1_restored():
    assert _maxconn_ok(_server("be_api_ws", "ws-1"))

def test_health_app1_sane():
    assert _health_ok(_server("be_api_app", "app-1"))

def test_health_app5_sane():
    assert _health_ok(_server("be_api_app", "app-5"))

def test_health_srch4_sane():
    assert _health_ok(_server("be_api_search", "srch-4"))

def test_health_srch7_sane():
    assert _health_ok(_server("be_api_search", "srch-7"))

def test_health_media4_sane():
    assert _health_ok(_server("be_api_media", "media-4"))

def test_health_media8_sane():
    assert _health_ok(_server("be_api_media", "media-8"))

def test_health_ws7_sane():
    assert _health_ok(_server("be_api_ws", "ws-7"))

def test_check_app8_enabled():
    assert _check_ok(_server("be_api_app", "app-8"))

def test_check_srch5_enabled():
    assert _check_ok(_server("be_api_search", "srch-5"))

def test_check_media5_enabled():
    assert _check_ok(_server("be_api_media", "media-5"))

def test_check_media6_enabled():
    assert _check_ok(_server("be_api_media", "media-6"))

def test_check_ws2_enabled():
    assert _check_ok(_server("be_api_ws", "ws-2"))

def test_balance_be_api_app_restored():
    assert _balance_ok(_backend("be_api_app"))

def test_balance_be_api_search_restored():
    assert _balance_ok(_backend("be_api_search"))

def test_balance_be_api_media_restored():
    assert _balance_ok(_backend("be_api_media"))

def test_admin_app4_ready():
    assert _runtime_admin("be_api_app", "app-4") not in ("maint", "drain")

def test_admin_srch2_ready():
    assert _runtime_admin("be_api_search", "srch-2") not in ("maint", "drain")

def test_admin_media5_ready():
    assert _runtime_admin("be_api_media", "media-5") not in ("maint", "drain")

def test_admin_ws3_ready():
    assert _runtime_admin("be_api_ws", "ws-3") not in ("maint", "drain")

def test_incident_resolved():
    inc = _incident()
    assert inc is not None and str(inc.get("state")) in ("6", "7")

def test_incident_documented():
    inc = _incident()
    assert inc is not None and str(inc.get("close_notes") or "").strip() != ""
