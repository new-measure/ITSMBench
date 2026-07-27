import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request

SN = "http://servicenow.local.mock:8080/api/now/table"

def _h(*p):
    return hashlib.md5("|".join(str(x) for x in p).encode()).hexdigest()

def sid(k):
    return _h("ops2", k)[:32]

PRB_CHK = sid("prb_chk")
CHG_ROOT = sid("chg_root")
FOOTPRINT_KEYS = ["fc_co1", "fc_co2", "fc_co3",
                  "fc_wcu1", "fc_wcu2", "fc_mca1", "fc_mca2", "fc_pcs1", "fc_pcs2",
                  "fc_pta1", "fc_pta2", "fc_brs1", "fc_iap1", "fc_pfl1",
                  "fc_ssk1", "fc_wsdk1", "fc_kmall1"]
FOOTPRINT = [sid(k) for k in FOOTPRINT_KEYS]
FP_SET = set(FOOTPRINT)

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

_LINK_TARGETS = FP_SET | {PRB_CHK}

def _linked(inc):
    if str(inc.get("problem_id")) == PRB_CHK:
        return True
    self_id = str(inc.get("sys_id"))
    for f in ("parent_incident", "duplicate_of", "parent", "rfc", "u_parent_incident"):
        v = str(inc.get(f))
        if v in _LINK_TARGETS and v != self_id:
            return True
    return False

def _closed_dup(inc):
    if str(inc.get("state")) not in ("6", "7"):
        return False
    if "dup" in str(inc.get("close_code")).lower():
        return True
    return bool(str(inc.get("duplicate_of")) not in ("", "None"))

def _consolidated(child_sid):
    inc = rec("incident", child_sid)
    return _linked(inc) and _closed_dup(inc)

def test_footprint_co_1_affected_ci():
    assert _consolidated(sid("fc_co1"))

def test_footprint_co_2_affected_ci():
    assert _consolidated(sid("fc_co2"))

def test_footprint_co_3_affected_ci():
    assert _consolidated(sid("fc_co3"))

def test_footprint_wcu_1_one_hop_down():
    assert _consolidated(sid("fc_wcu1"))

def test_footprint_wcu_2_one_hop_down():
    assert _consolidated(sid("fc_wcu2"))

def test_footprint_mca_1_one_hop_down():
    assert _consolidated(sid("fc_mca1"))

def test_footprint_mca_2_one_hop_down():
    assert _consolidated(sid("fc_mca2"))

def test_footprint_pcs_1_one_hop_down():
    assert _consolidated(sid("fc_pcs1"))

def test_footprint_pcs_2_one_hop_down():
    assert _consolidated(sid("fc_pcs2"))

def test_footprint_pta_1_two_hop_down():
    assert _consolidated(sid("fc_pta1"))

def test_footprint_pta_2_two_hop_down():
    assert _consolidated(sid("fc_pta2"))

def test_footprint_brs_1_two_hop_down():
    assert _consolidated(sid("fc_brs1"))

def test_footprint_iap_1_two_hop_down():
    assert _consolidated(sid("fc_iap1"))

def test_footprint_pfl_1_two_hop_down():
    assert _consolidated(sid("fc_pfl1"))

def test_footprint_ssk_1_three_hop_down():
    assert _consolidated(sid("fc_ssk1"))

def test_footprint_wsdk_1_three_hop_down():
    assert _consolidated(sid("fc_wsdk1"))

def test_footprint_kmall_1_four_hop_down():
    assert _consolidated(sid("fc_kmall1"))

def test_problem_linked_to_upstream_root_cause_change():
    p = rec("problem", PRB_CHK)
    vals = {str(v) for v in p.values()}
    if CHG_ROOT in vals:
        return
    num = str(rec("change_request", CHG_ROOT).get("number"))
    assert num and num not in ("", "None") and any(num in str(v) for v in p.values())

def test_problem_state_advanced():
    p = rec("problem", PRB_CHK)
    assert str(p.get("state")) not in ("1", "", "None")

def test_problem_marked_known_error():
    p = rec("problem", PRB_CHK)
    assert str(p.get("known_error")).lower() in ("true", "1") or str(p.get("state")) == "3"
