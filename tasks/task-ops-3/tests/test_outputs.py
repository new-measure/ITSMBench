import datetime
import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request

SN = "http://servicenow.local.mock:8080/api/now/table"
FREEZE_START = "2026-07-25 20:00:00"
FREEZE_END = "2026-07-26 08:00:00"

def _h(*p):
    return hashlib.md5("|".join(str(x) for x in p).encode()).hexdigest()

def sid(k):
    return _h("ops3", k)[:32]

def chg(key):
    return sid("chg:" + key)

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
    r = _rows(_get("%s/change_request?sysparm_query=%s" % (SN, urllib.parse.quote("sys_id=" + sys_id))))
    return r[0] if r else {}

def _parse(dt):
    return datetime.datetime.strptime(str(dt), "%Y-%m-%d %H:%M:%S")

NEUTRAL_STATES = {"4", "canceled", "cancelled", "blocked", "rejected", "hold", "on_hold", "on hold"}

def neutralized(c):
    if str(c.get("on_hold", "")).strip().lower() in ("true", "1", "yes"):
        return True
    return str(c.get("state", "")).strip().lower() in NEUTRAL_STATES

def _overlap(a, b):
    try:
        return _parse(a["start_date"]) < _parse(b["end_date"]) and _parse(b["start_date"]) < _parse(a["end_date"])
    except (KeyError, ValueError):
        return False

def collision_resolved(a_key, b_key):
    a, b = rec(chg(a_key)), rec(chg(b_key))
    if neutralized(a) or neutralized(b):
        return True
    return not _overlap(a, b)

def in_freeze(c):
    try:
        return _parse(FREEZE_START) <= _parse(c["start_date"]) < _parse(FREEZE_END)
    except (KeyError, ValueError):
        return False

def test_collision_sc1_same_ci():
    assert collision_resolved("sc1a", "sc1b")

def test_collision_sc2_same_ci():
    assert collision_resolved("sc2a", "sc2b")

def test_collision_sc3_same_ci():
    assert collision_resolved("sc3a", "sc3b")

def test_collision_dc1_depends_on():
    assert collision_resolved("dc1a", "dc1b")

def test_collision_dc2_depends_on():
    assert collision_resolved("dc2a", "dc2b")

def test_collision_dc3_depends_on():
    assert collision_resolved("dc3a", "dc3b")

def test_collision_dc4_depends_on():
    assert collision_resolved("dc4a", "dc4b")

def test_collision_rc1_shared_dependent():
    assert collision_resolved("rc1a", "rc1b")

def test_collision_rc2_shared_dependent():
    assert collision_resolved("rc2a", "rc2b")

def test_collision_tc1_transitive():
    assert collision_resolved("tc1a", "tc1b")

def test_collision_tc2_transitive():
    assert collision_resolved("tc2a", "tc2b")

def test_unapproved_ua1_blocked():
    assert neutralized(rec(chg("ua1")))

def test_unapproved_ua2_blocked():
    assert neutralized(rec(chg("ua2")))

def test_unapproved_ua3_blocked():
    assert neutralized(rec(chg("ua3")))

def _freeze_remediated(key):
    c = rec(chg(key))
    return neutralized(c) or (not in_freeze(c))

def test_freeze_fz1_remediated():
    assert _freeze_remediated("fz1")

def test_freeze_fz2_remediated():
    assert _freeze_remediated("fz2")

def test_freeze_fz3_remediated():
    assert _freeze_remediated("fz3")

def test_highrisk_hr1_blocked():
    assert neutralized(rec(chg("hr1")))

def test_highrisk_hr2_blocked():
    assert neutralized(rec(chg("hr2")))

def test_highrisk_hr3_blocked():
    assert neutralized(rec(chg("hr3")))
