import json
import urllib.error
import urllib.parse
import urllib.request

OKTA = "http://okta.local.mock:8080/api/v1"
M365 = "http://microsoft-365.local.mock:8080/v1.0"
SN = "http://servicenow.local.mock:8080/api/now/table"

APP_PBI = "0oapowerbi000000001"
SKU_PBI = "pbipro00-0000-0000-0000-00000000pbi1"
INC_SYS = "2e31b68847d76a4d2e68c219abab4e2a"
DOMAIN = "halcyon.example"

def _login(key):
    return key.replace("-", ".") + "@" + DOMAIN

COHORT = ["ava-morgan", "ben-cole", "cara-diaz", "dev-shah", "ella-fox", "finn-reed",
          "gia-park", "hugo-lane", "iris-shaw", "jonah-kim", "kira-bell", "leo-vance"]
SUSPENDED = ["ella-fox", "finn-reed", "gia-park"]
MFA_WIPED = ["hugo-lane", "iris-shaw", "jonah-kim"]
DELICENSED = ["ben-cole", "kira-bell", "leo-vance"]

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode()
    return json.loads(raw) if raw and raw.strip()[:1] in "{[" else raw

def _okta_user(login):
    return _get(OKTA + "/users/" + urllib.parse.quote(login, safe=""))

def _effective_app_user_ids(app_id):
    rows = _get(OKTA + "/apps/" + app_id + "/users")
    rows = rows if isinstance(rows, list) else []
    return {str(r.get("id")) for r in rows if r.get("id")}

def _active_factors(login):
    rows = _get(OKTA + "/users/" + urllib.parse.quote(login, safe="") + "/factors")
    rows = rows if isinstance(rows, list) else []
    return [f for f in rows if str(f.get("status")) == "ACTIVE"]

_M365_CACHE = {}

def _m365_users():
    if not _M365_CACHE:
        resp = _get(M365 + "/users")
        vals = resp.get("value", []) if isinstance(resp, dict) else (resp if isinstance(resp, list) else [])
        for u in vals:
            _M365_CACHE[str(u.get("userPrincipalName", "")).lower()] = u
    return _M365_CACHE

def _has_bi_pro(login):
    u = _m365_users().get(login.lower())
    if not u:
        return False
    return any(str(l.get("skuId")) == SKU_PBI for l in (u.get("assignedLicenses") or []))

def _incident_state(sys_id):
    r = _get(SN + "/incident/" + sys_id)
    rec = (r or {}).get("result") if isinstance(r, dict) else None
    return str((rec or {}).get("state")) if rec else None

_EFF = _effective_app_user_ids(APP_PBI)

def _has_access(key):
    uid = str((_okta_user(_login(key)) or {}).get("id"))
    return uid in _EFF

def test_access_ava_morgan():
    assert _has_access("ava-morgan")

def test_access_ben_cole():
    assert _has_access("ben-cole")

def test_access_cara_diaz():
    assert _has_access("cara-diaz")

def test_access_dev_shah():
    assert _has_access("dev-shah")

def test_access_ella_fox():
    assert _has_access("ella-fox")

def test_access_finn_reed():
    assert _has_access("finn-reed")

def test_access_gia_park():
    assert _has_access("gia-park")

def test_access_hugo_lane():
    assert _has_access("hugo-lane")

def test_access_iris_shaw():
    assert _has_access("iris-shaw")

def test_access_jonah_kim():
    assert _has_access("jonah-kim")

def test_access_kira_bell():
    assert _has_access("kira-bell")

def test_access_leo_vance():
    assert _has_access("leo-vance")

def test_status_ella_fox_active():
    assert str((_okta_user(_login("ella-fox")) or {}).get("status")) == "ACTIVE"

def test_status_finn_reed_active():
    assert str((_okta_user(_login("finn-reed")) or {}).get("status")) == "ACTIVE"

def test_status_gia_park_active():
    assert str((_okta_user(_login("gia-park")) or {}).get("status")) == "ACTIVE"

def test_mfa_hugo_lane():
    assert len(_active_factors(_login("hugo-lane"))) >= 1

def test_mfa_iris_shaw():
    assert len(_active_factors(_login("iris-shaw"))) >= 1

def test_mfa_jonah_kim():
    assert len(_active_factors(_login("jonah-kim"))) >= 1

def test_license_ben_cole():
    assert _has_bi_pro(_login("ben-cole"))

def test_license_kira_bell():
    assert _has_bi_pro(_login("kira-bell"))

def test_license_leo_vance():
    assert _has_bi_pro(_login("leo-vance"))

def test_incident_closed():
    s = str(_incident_state(INC_SYS)).lower()
    assert s in ("6", "7") or "clos" in s or "resolv" in s
