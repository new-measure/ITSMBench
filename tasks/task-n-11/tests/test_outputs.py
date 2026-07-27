import json
import urllib.error
import urllib.request

DNS = "http://infoblox-nios.local.mock:8080/wapi/v2.14"
SN = "http://servicenow.local.mock:8080/api/now/table"
DOMAIN = "halcyon.example"
INC_SYS = "2e31b68847d76a4d2e68c219abab4e2a"

LIVE_V4 = {
    "10.10.20.11", "10.10.20.12", "10.10.20.13", "10.10.20.14", "10.10.20.21", "10.10.20.22",
    "10.10.20.23", "10.10.20.24", "10.10.20.25", "10.10.20.30", "10.10.20.31", "10.10.20.40",
    "10.10.20.41", "10.10.20.50", "10.10.20.51", "10.10.20.60", "10.10.20.61", "10.10.20.70",
    "10.10.20.71", "10.10.20.72", "10.10.20.73", "10.10.20.80", "10.10.21.11", "10.10.21.12",
    "10.10.21.30", "10.20.10.90",
}
EXPECT = {
    "dispatch-api-01": "10.10.20.11", "dispatch-api-02": "10.10.20.12", "dispatch-api-03": "10.10.20.13",
    "dispatch-api-04": "10.10.20.14", "dispatch-worker-01": "10.10.20.21", "dispatch-worker-02": "10.10.20.22",
    "dispatch-worker-03": "10.10.20.23", "dispatch-worker-04": "10.10.20.24", "dispatch-worker-05": "10.10.20.25",
    "dispatch-db-01": "10.10.20.30", "dispatch-db-02": "10.10.20.31", "dispatch-cache-01": "10.10.20.40",
    "dispatch-search-01": "10.10.20.50", "dispatch-queue-01": "10.10.20.60", "dispatch-etl-01": "10.10.20.61",
    "dispatch-gw-01": "10.10.20.70", "dispatch-gw-02": "10.10.20.71", "dispatch-gw-03": "10.10.20.72",
    "dispatch-ledger-01": "10.10.20.80",
}
ALL_DISPATCH_HOSTS = dict(EXPECT, **{
    "dispatch-analytics-01": "10.10.20.41", "dispatch-metrics-01": "10.10.20.51",
    "dispatch-gw-04": "10.10.20.73", "dispatch-archive-01": "10.20.10.90",
})
GONE_HOSTS = ["dispatch-legacy-01", "dispatch-canary-01", "dispatch-retired-01"]
V6_EXPECT = {"dispatch-api-01": "2001:db8:10::11", "dispatch-api-02": "2001:db8:10::12",
             "dispatch-worker-01": "2001:db8:10::21"}

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode()
    return json.loads(raw) if raw else None

def _a(name):
    recs = _get(DNS + "/record:a")
    recs = recs if isinstance(recs, list) else []
    return [r for r in recs if str(r.get("name")) == name + "." + DOMAIN]

def _aaaa(name):
    recs = _get(DNS + "/record:aaaa")
    recs = recs if isinstance(recs, list) else []
    return [r for r in recs if str(r.get("name")) == name + "." + DOMAIN]

def _cname(name):
    recs = _get(DNS + "/record:cname")
    recs = recs if isinstance(recs, list) else []
    return [r for r in recs if str(r.get("name")) == name + "." + DOMAIN]

def _live_a_names():
    recs = _get(DNS + "/record:a")
    recs = recs if isinstance(recs, list) else []
    return {str(r.get("name")) for r in recs if str(r.get("ipv4addr")) in LIVE_V4}

def _resolves_to(name, ip):
    recs = _a(name)
    return bool(recs) and all(str(r.get("ipv4addr")) == ip for r in recs)

def _incident_state(sys_id):
    r = _get(SN + "/incident/" + sys_id)
    rec = (r or {}).get("result") if isinstance(r, dict) else None
    return str((rec or {}).get("state")) if rec else None

def test_api_01_repointed_live():
    assert _resolves_to("dispatch-api-01", EXPECT["dispatch-api-01"])

def test_api_02_repointed_live():
    assert _resolves_to("dispatch-api-02", EXPECT["dispatch-api-02"])

def test_api_04_repointed_live():
    assert _resolves_to("dispatch-api-04", EXPECT["dispatch-api-04"])

def test_worker_01_repointed_live():
    assert _resolves_to("dispatch-worker-01", EXPECT["dispatch-worker-01"])

def test_worker_02_repointed_live():
    assert _resolves_to("dispatch-worker-02", EXPECT["dispatch-worker-02"])

def test_worker_04_repointed_live():
    assert _resolves_to("dispatch-worker-04", EXPECT["dispatch-worker-04"])

def test_db_01_repointed_live():
    assert _resolves_to("dispatch-db-01", EXPECT["dispatch-db-01"])

def test_queue_01_repointed_live():
    assert _resolves_to("dispatch-queue-01", EXPECT["dispatch-queue-01"])

def test_etl_01_repointed_live():
    assert _resolves_to("dispatch-etl-01", EXPECT["dispatch-etl-01"])

def test_gw_01_repointed_live():
    assert _resolves_to("dispatch-gw-01", EXPECT["dispatch-gw-01"])

def test_gw_02_repointed_live():
    assert _resolves_to("dispatch-gw-02", EXPECT["dispatch-gw-02"])

def test_cache_01_conflict_resolved():
    assert _resolves_to("dispatch-cache-01", EXPECT["dispatch-cache-01"])

def test_search_01_conflict_resolved():
    assert _resolves_to("dispatch-search-01", EXPECT["dispatch-search-01"])

def test_db_02_conflict_resolved():
    assert _resolves_to("dispatch-db-02", EXPECT["dispatch-db-02"])

def test_gw_03_conflict_resolved():
    assert _resolves_to("dispatch-gw-03", EXPECT["dispatch-gw-03"])

def test_api_03_record_added():
    assert _resolves_to("dispatch-api-03", EXPECT["dispatch-api-03"])

def test_worker_03_record_added():
    assert _resolves_to("dispatch-worker-03", EXPECT["dispatch-worker-03"])

def test_worker_05_record_added():
    assert _resolves_to("dispatch-worker-05", EXPECT["dispatch-worker-05"])

def test_ledger_01_ghost_repointed_not_deleted():
    assert _resolves_to("dispatch-ledger-01", EXPECT["dispatch-ledger-01"])

def test_dispatch_vip_all_members_live():
    recs = _a("dispatch")
    assert bool(recs) and all(str(r.get("ipv4addr")) in LIVE_V4 for r in recs)

def test_api_01_aaaa_repointed_live():
    recs = _aaaa("dispatch-api-01")
    assert bool(recs) and all(str(r.get("ipv6addr")) == V6_EXPECT["dispatch-api-01"] for r in recs)

def test_api_02_aaaa_repointed_live():
    recs = _aaaa("dispatch-api-02")
    assert bool(recs) and all(str(r.get("ipv6addr")) == V6_EXPECT["dispatch-api-02"] for r in recs)

def test_worker_01_aaaa_repointed_live():
    recs = _aaaa("dispatch-worker-01")
    assert bool(recs) and all(str(r.get("ipv6addr")) == V6_EXPECT["dispatch-worker-01"] for r in recs)

def test_ship_cname_not_dangling():
    recs = _cname("ship")
    live_names = _live_a_names()
    assert all(str(r.get("canonical")) in live_names for r in recs)

def test_track_cname_not_dangling():
    recs = _cname("track")
    live_names = _live_a_names()
    assert all(str(r.get("canonical")) in live_names for r in recs)

def test_legacy_01_record_removed():
    assert _a("dispatch-legacy-01") == []

def test_canary_01_record_removed():
    assert _a("dispatch-canary-01") == []

def test_retired_01_record_removed():
    assert _a("dispatch-retired-01") == []

def test_no_dispatch_record_resolves_dead():
    recs = _get(DNS + "/record:a")
    recs = recs if isinstance(recs, list) else []
    dispatch = [r for r in recs if str(r.get("name")).startswith("dispatch")]
    assert dispatch and all(str(r.get("ipv4addr")) in LIVE_V4 for r in dispatch)

def test_every_inservice_dispatch_host_resolves_live():
    assert all(_resolves_to(name, ip) for name, ip in ALL_DISPATCH_HOSTS.items())

def test_incident_closed():
    assert _incident_state(INC_SYS) in ("6", "7")
