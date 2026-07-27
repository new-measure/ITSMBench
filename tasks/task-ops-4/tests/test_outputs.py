import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request

SN = "http://servicenow.local.mock:8080/api/now/table"

def _h(*p):
    return hashlib.md5("|".join(str(x) for x in p).encode()).hexdigest()

def sid(k):
    return _h("ops4", k)[:32]

SCORED_VIOLATIONS = ["v_missing_norec", "v_missing_rejected", "v_self_1", "v_self_2", "v_unauth_1",
                     "v_unauth_2", "v_sod_1", "v_sod_2", "v_sod_3", "v_sod_grp_1", "v_sod_grp_2",
                     "v_sod_grp_3", "v_over_1", "v_over_2"]
SCORED_COMPLIANT = ["c_clean_1", "c_clean_2", "c_clean_3", "c_clean_4", "c_clean_5", "c_clean_6",
                    "c_exc", "c_unusual_approver", "c_noncf", "c_grp_noncf"]

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

def rec(sys_id):
    r = _rows(_get("%s/sc_req_item?sysparm_query=%s" % (SN, urllib.parse.quote("sys_id=" + sys_id))))
    return r[0] if r else {}

def _truthy(v):
    return str(v).strip().lower() in ("true", "1", "yes")

def _not_fulfilled(r):
    state = str(r.get("state")).strip().lower()
    if state in ("4", "7", "8", "closed_incomplete", "closed incomplete", "cancelled", "canceled", "rejected"):
        return True
    if _truthy(r.get("on_hold")):
        return True
    hr = str(r.get("hold_reason") or "").strip().lower()
    if hr and hr != "none":
        return True
    return False

def _fulfilled(r):
    state = str(r.get("state")).strip().lower()
    return state in ("3", "closed_complete", "closed complete", "fulfilled") or _truthy(r.get("u_fulfilled"))

def test_violation_missing_approval_no_record_not_fulfilled():
    assert _not_fulfilled(rec(sid("v_missing_norec")))

def test_violation_missing_approval_rejected_record_not_fulfilled():
    assert _not_fulfilled(rec(sid("v_missing_rejected")))

def test_violation_self_approval_1_not_fulfilled():
    assert _not_fulfilled(rec(sid("v_self_1")))

def test_violation_self_approval_2_not_fulfilled():
    assert _not_fulfilled(rec(sid("v_self_2")))

def test_violation_unauthorized_approver_1_not_fulfilled():
    assert _not_fulfilled(rec(sid("v_unauth_1")))

def test_violation_unauthorized_approver_2_not_fulfilled():
    assert _not_fulfilled(rec(sid("v_unauth_2")))

def test_violation_sod_conflict_1_not_fulfilled():
    assert _not_fulfilled(rec(sid("v_sod_1")))

def test_violation_sod_conflict_2_not_fulfilled():
    assert _not_fulfilled(rec(sid("v_sod_2")))

def test_violation_sod_conflict_3_not_fulfilled():
    assert _not_fulfilled(rec(sid("v_sod_3")))

def test_violation_sod_group_conferred_1_not_fulfilled():
    assert _not_fulfilled(rec(sid("v_sod_grp_1")))

def test_violation_sod_group_conferred_2_not_fulfilled():
    assert _not_fulfilled(rec(sid("v_sod_grp_2")))

def test_violation_sod_group_conferred_3_not_fulfilled():
    assert _not_fulfilled(rec(sid("v_sod_grp_3")))

def test_violation_over_entitlement_1_not_fulfilled():
    assert _not_fulfilled(rec(sid("v_over_1")))

def test_violation_over_entitlement_2_not_fulfilled():
    assert _not_fulfilled(rec(sid("v_over_2")))

def test_compliant_clean_1_fulfilled():
    assert _fulfilled(rec(sid("c_clean_1")))

def test_compliant_clean_2_fulfilled():
    assert _fulfilled(rec(sid("c_clean_2")))

def test_compliant_clean_3_fulfilled():
    assert _fulfilled(rec(sid("c_clean_3")))

def test_compliant_clean_4_fulfilled():
    assert _fulfilled(rec(sid("c_clean_4")))

def test_compliant_clean_5_fulfilled():
    assert _fulfilled(rec(sid("c_clean_5")))

def test_compliant_clean_6_fulfilled():
    assert _fulfilled(rec(sid("c_clean_6")))

def test_compliant_exception_backed_fulfilled():
    assert _fulfilled(rec(sid("c_exc")))

def test_compliant_unusual_authorized_approver_fulfilled():
    assert _fulfilled(rec(sid("c_unusual_approver")))

def test_compliant_non_conflict_combo_fulfilled():
    assert _fulfilled(rec(sid("c_noncf")))

def test_compliant_group_conferred_non_conflict_fulfilled():
    assert _fulfilled(rec(sid("c_grp_noncf")))
