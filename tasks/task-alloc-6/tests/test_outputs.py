import hashlib
import json
import urllib.request
import urllib.parse
import urllib.error

SNIPE = "http://snipeit.local.mock:8080/api/v1"
SNOW = "http://servicenow.local.mock:8080/api/now/table"
RES_TABLE = "u_hw_provisioning_request"

MODEL_M = "MacBook Pro 14 M3"
DEST_NAME = "Deployment Staging - HQ"
TRIGGER = "RSV0001188"

RECLAIM_KEYS = ["rc1", "rc2", "rc5", "rc6", "rr1", "rr2"]
FULFILLED_STATES = {"fulfilled", "allocated", "delivered", "complete", "completed",
                    "closed complete", "closed_complete", "closed", "resolved", "done",
                    "issued", "provisioned"}

def hex_(salt, key, n=8):
    return hashlib.md5(f"{salt}:{key}".encode()).hexdigest()[:n]

def tag_for(key):
    return "NBS-" + hex_("tag", key, 6).upper()

def norm(v):
    return str(v or "").strip().lower()

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode())

def snipe_hardware():
    out, offset = [], 0
    while True:
        body = _get(f"{SNIPE}/hardware?{urllib.parse.urlencode({'limit': 500, 'offset': offset})}")
        rows = body.get("rows", [])
        out.extend(rows)
        offset += len(rows)
        if not rows or offset >= body.get("total", len(out)):
            break
    return out

def snow_request(number):
    body = _get(f"{SNOW}/{RES_TABLE}?{urllib.parse.urlencode({'number': number, 'sysparm_limit': 50})}")
    for r in body.get("result", []):
        if norm(r.get("number")) == norm(number):
            return r
    return None

_HW = snipe_hardware()
_LOCS = _get(f"{SNIPE}/locations?limit=500").get("rows", [])
_DEST = [l for l in _LOCS if norm(l.get("name")) == norm(DEST_NAME)]
DEST_ID = _DEST[0]["id"] if len(_DEST) == 1 else None
_HW_BY_TAG = {norm(h.get("asset_tag")): h for h in _HW}

def assigned_loc_id(h):
    a = h.get("assigned_to") or {}
    if isinstance(a, dict) and norm(a.get("type")) == "location":
        return a.get("id")
    return None

def assigned_loc_name(h):
    a = h.get("assigned_to") or {}
    if isinstance(a, dict) and norm(a.get("type")) == "location":
        return norm(a.get("name"))
    return None

def model_name(h):
    return norm((h.get("model") or {}).get("name"))

def at_bench_any():
    return [h for h in _HW if DEST_ID is not None and str(assigned_loc_id(h)) == str(DEST_ID)]

def at_bench_model_m():
    return [h for h in at_bench_any() if model_name(h) == norm(MODEL_M)]

def _issued(key):
    return norm(tag_for(key)) in {norm(h.get("asset_tag")) for h in at_bench_model_m()}

def test_c_rc1_issued():
    assert _issued("rc1")

def test_c_rc2_issued():
    assert _issued("rc2")

def test_c_rc5_issued():
    assert _issued("rc5")

def test_c_rc6_issued():
    assert _issued("rc6")

def test_c_rr1_issued():
    assert _issued("rr1")

def test_c_rr2_issued():
    assert _issued("rr2")

def test_c_alloc_exact_set():
    got = {norm(h.get("asset_tag")) for h in at_bench_model_m()}
    want = {norm(tag_for(k)) for k in RECLAIM_KEYS}
    assert got == want, f"bench model-M set {sorted(got)} != {sorted(want)}"

def test_c_flagship_fulfilled():
    r = snow_request(TRIGGER)
    assert r is not None, "flagship request not found"
    assert norm(r.get("state")) in FULFILLED_STATES, f"flagship state '{r.get('state')}' not fulfilled"

def _not_at_bench(key):
    return norm(tag_for(key)) not in {norm(h.get("asset_tag")) for h in at_bench_any()}

def test_g_pd_not_at_bench():
    assert _not_at_bench("pd")

def test_g_rep1_not_at_bench():
    assert _not_at_bench("rep1")

def test_g_rep1_still_pending_repair():
    sl = _HW_BY_TAG[norm(tag_for("rep1"))].get("status_label") or {}
    assert norm(sl.get("status_meta")) == "undeployable" or "repair" in norm(sl.get("name"))

def test_g_pc1_not_at_bench():
    assert _not_at_bench("pc1")

def test_g_pc2_not_at_bench():
    assert _not_at_bench("pc2")

def test_g_pc3_not_at_bench():
    assert _not_at_bench("pc3")

def _pc_request_state(key):
    body = _HW_BY_TAG.get(norm(tag_for(key)))
    assert body is not None, f"{key} body missing"
    num = body.get("_snipeit_reservation")
    assert num, f"{key} lost its request backlink"
    r = snow_request(num)
    assert r is not None, f"{key} request {num} missing"
    return norm(r.get("state"))

def test_g_pc1_request_still_confirmed():
    assert _pc_request_state("pc1") == "confirmed"

def test_g_pc2_request_still_confirmed():
    assert _pc_request_state("pc2") == "confirmed"

def test_g_pc3_request_still_confirmed():
    assert _pc_request_state("pc3") == "confirmed"

def test_g_nd1_still_at_east():
    assert assigned_loc_name(_HW_BY_TAG[norm(tag_for("nd1"))]) == norm("Field Office East")

def test_g_nd2_still_at_north():
    assert assigned_loc_name(_HW_BY_TAG[norm(tag_for("nd2"))]) == norm("Field Office North")

def test_g_idmp_still_at_south():
    assert assigned_loc_name(_HW_BY_TAG[norm(tag_for("idmp"))]) == norm("Field Office South")

def test_g_bench_only_model_m():
    non_m = [h for h in at_bench_any() if model_name(h) != norm(MODEL_M)]
    assert not non_m, f"non-target-model bodies at bench: {[h.get('asset_tag') for h in non_m]}"
