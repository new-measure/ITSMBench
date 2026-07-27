import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request

SN = "http://servicenow.local.mock:8080/api/now/table"

def _h(*p):
    return hashlib.md5("|".join(str(x) for x in p).encode()).hexdigest()

def sid(k):
    return _h("ops1", k)[:32]

PRB_PAY = sid("prb_pay")
CHG_ROOT = sid("chg_root")
CHILDREN = [sid("cld%02d" % i) for i in range(1, 17)]
CHILD_SET = set(CHILDREN)
MISROUTED = {sid("mr01"): sid("g_net"), sid("mr02"): sid("g_iam"), sid("mr03"): sid("g_msg"),
             sid("mr04"): sid("g_data"), sid("mr05"): sid("g_crm"), sid("mr06"): sid("g_msg"),
             sid("mr07"): sid("g_store"), sid("mr08"): sid("g_data")}
MP01 = sid("mp01")

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

def _group_aliases(group_sid):
    g = rec("sys_user_group", group_sid)
    return {group_sid, str(g.get("name"))} - {"", "None"}

def _rerouted(inc_sid, correct_group_sid):
    return str(rec("incident", inc_sid).get("assignment_group")) in _group_aliases(correct_group_sid)

_LINK_TARGETS = CHILD_SET | {PRB_PAY}

def _linked(inc):
    if str(inc.get("problem_id")) == PRB_PAY:
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

def test_child_01_consolidated():
    assert _consolidated(sid("cld01"))

def test_child_02_consolidated():
    assert _consolidated(sid("cld02"))

def test_child_03_consolidated():
    assert _consolidated(sid("cld03"))

def test_child_04_consolidated():
    assert _consolidated(sid("cld04"))

def test_child_05_consolidated_dependent_ci():
    assert _consolidated(sid("cld05"))

def test_child_06_consolidated_dependent_ci():
    assert _consolidated(sid("cld06"))

def test_child_07_consolidated_blank_ci():
    assert _consolidated(sid("cld07"))

def test_child_08_consolidated_blank_ci():
    assert _consolidated(sid("cld08"))

def test_child_09_consolidated_wrong_ci():
    assert _consolidated(sid("cld09"))

def test_child_10_consolidated_wrong_ci():
    assert _consolidated(sid("cld10"))

def test_child_11_consolidated():
    assert _consolidated(sid("cld11"))

def test_child_12_consolidated_dependent_ci():
    assert _consolidated(sid("cld12"))

def test_child_13_consolidated_two_hop_dependency():
    assert _consolidated(sid("cld13"))

def test_child_14_consolidated_blank_ci():
    assert _consolidated(sid("cld14"))

def test_child_15_consolidated_wrong_ci():
    assert _consolidated(sid("cld15"))

def test_child_16_consolidated_dependent_ci():
    assert _consolidated(sid("cld16"))

def test_problem_linked_to_root_cause_change():
    p = rec("problem", PRB_PAY)
    vals = {str(v) for v in p.values()}
    if CHG_ROOT in vals:
        return
    num = str(rec("change_request", CHG_ROOT).get("number"))
    assert num and num not in ("", "None") and any(num in str(v) for v in p.values())

def test_problem_state_advanced():
    p = rec("problem", PRB_PAY)
    assert str(p.get("state")) not in ("1", "", "None")

def test_reroute_mr01_vpn():
    assert _rerouted(sid("mr01"), MISROUTED[sid("mr01")])

def test_reroute_mr02_sso():
    assert _rerouted(sid("mr02"), MISROUTED[sid("mr02")])

def test_reroute_mr03_mail():
    assert _rerouted(sid("mr03"), MISROUTED[sid("mr03")])

def test_reroute_mr04_warehouse():
    assert _rerouted(sid("mr04"), MISROUTED[sid("mr04")])

def test_reroute_mr05_crm():
    assert _rerouted(sid("mr05"), MISROUTED[sid("mr05")])

def test_reroute_mr06_notif():
    assert _rerouted(sid("mr06"), MISROUTED[sid("mr06")])

def test_reroute_mr07_cdn():
    assert _rerouted(sid("mr07"), MISROUTED[sid("mr07")])

def test_reroute_mr08_datalake():
    assert _rerouted(sid("mr08"), MISROUTED[sid("mr08")])

def test_misprioritized_raised_to_p1():
    inc = rec("incident", MP01)
    assert str(inc.get("priority")) == "1" or (str(inc.get("impact")) == "1" and str(inc.get("urgency")) == "1")
