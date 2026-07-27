import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request

SN = "http://servicenow.local.mock:8080/api/now/table"

def _h(*p):
    return hashlib.md5("|".join(str(x) for x in p).encode()).hexdigest()

def sid(k):
    return _h("ops5", k)[:32]

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    return json.loads(raw) if raw else None

def _rows(obj):
    if isinstance(obj, dict) and isinstance(obj.get("result"), list):
        return obj["result"]
    if isinstance(obj, dict) and isinstance(obj.get("result"), dict):
        return [obj["result"]]
    return obj if isinstance(obj, list) else []

def rec(table, sys_id):
    r = _rows(_get("%s/%s?sysparm_query=%s" % (SN, table, urllib.parse.quote("sys_id=" + sys_id))))
    return r[0] if r else {}

def _truthy(v):
    return str(v).strip().lower() in ("true", "1", "yes")

def _is_p1(inc):
    return str(inc.get("priority")) == "1" or (str(inc.get("impact")) == "1" and str(inc.get("urgency")) == "1")

def _is_major(inc):
    if str(inc.get("major_incident_state", "")).lower() in ("proposed", "accepted"):
        return True
    return _truthy(inc.get("u_major_incident")) or _truthy(inc.get("u_escalated"))

def _escalated_p1(key):
    return _is_p1(rec("incident", sid(key)))

def _severe_done(key):
    inc = rec("incident", sid(key))
    return _is_p1(inc) and _is_major(inc)

def test_hidden_auth_token_svc_p1():
    assert _is_p1(rec("incident", sid("hs_auth")))

def test_hidden_auth_token_svc_major():
    assert _is_major(rec("incident", sid("hs_auth")))

def test_hidden_session_cache_p1():
    assert _is_p1(rec("incident", sid("hs_sess")))

def test_hidden_session_cache_major():
    assert _is_major(rec("incident", sid("hs_sess")))

def test_hidden_config_service_p1():
    assert _is_p1(rec("incident", sid("hs_conf")))

def test_hidden_config_service_major():
    assert _is_major(rec("incident", sid("hs_conf")))

def test_hidden_service_mesh_gateway_p1():
    assert _is_p1(rec("incident", sid("hs_mesh")))

def test_hidden_service_mesh_gateway_major():
    assert _is_major(rec("incident", sid("hs_mesh")))

def test_hidden_primary_pg_cluster_p1():
    assert _is_p1(rec("incident", sid("hs_pg")))

def test_hidden_primary_pg_cluster_major():
    assert _is_major(rec("incident", sid("hs_pg")))

def test_hidden_event_bus_2hop_p1():
    assert _is_p1(rec("incident", sid("hs_bus")))

def test_hidden_event_bus_2hop_major():
    assert _is_major(rec("incident", sid("hs_bus")))

def test_hidden_secrets_manager_p1():
    assert _is_p1(rec("incident", sid("hs_sec")))

def test_hidden_secrets_manager_major():
    assert _is_major(rec("incident", sid("hs_sec")))

def test_hidden_feature_flag_svc_2hop_p1():
    assert _is_p1(rec("incident", sid("hs_flag")))

def test_hidden_feature_flag_svc_2hop_major():
    assert _is_major(rec("incident", sid("hs_flag")))

def test_sla_breach_wallet_svc_p1():
    assert _escalated_p1("se_wallet")

def test_sla_breach_merchant_portal_p1():
    assert _escalated_p1("se_merch")
