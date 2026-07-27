import json
import urllib.error
import urllib.request

INTUNE = "http://microsoft-intune.local.mock:8080/v1.0"
DEFENDER = "http://microsoft-defender.local.mock:8080/v1.0"
ENTRA = "http://entra-id.local.mock:8080/v1.0"
SN = "http://servicenow.local.mock:8080/api/now/table"

GRP_ENFORCED = "9dba9800-943e-48b9-affd-6b07cde586a1"
INC_SYS = "2e31b68847d76a4d2e68c219abab4e2a"

FIX = {
    "ANDERSON-LT": ("fb23fc24-8f0b-fafc-f0f4-700fb9154635", "bb0300aa-4540-9060-ae20-8e5f73faf459"),
    "BROOKS-LT":   ("46e5ba0b-4a0d-9c6f-0f11-695a6dd6b427", "bffcc882-5082-44b6-01ff-71d4a1917f63"),
    "CHEN-LT":     ("11a01b06-3d60-5dac-01c2-c0bd4124304d", "52abb501-6ffc-13b6-6469-bcdef71686cc"),
    "DIAZ-LT":     ("7e891cbf-f7f6-3db4-3df0-da5f6a5dd529", "38ab718e-a703-6a41-816a-43c040dc0513"),
    "EVANS-LT":    ("a9171b44-a9af-86ff-ccc5-76b51edf994d", "496c17b1-b67f-8cf6-03b6-0d338870ceab"),
    "FOSTER-LT":   ("b1a9a250-10f6-8b65-193a-db0761d4341f", "8e831643-5927-1d6d-35fb-b3c222fb6a98"),
    "GHOSH-LT":    ("c8fd2462-26ad-56ac-f466-2d13c09d9e85", "fcc967fa-7feb-b9c0-4252-e0696d0e8acd"),
    "HAAS-LT":     ("7bc87950-b74f-7780-2904-e8e8d6674166", "e6a91a66-f9de-7872-42fe-75c1e4e36049"),
}
GENUINE_ALERTS = {
    "ANDERSON-LT": "dabde53a715c518f28bd94f2",
    "BROOKS-LT":   "dac3033fcf0af136621bb810",
    "CHEN-LT":     "da8f4034d61ec81bd3b4de4b",
    "DIAZ-LT":     "daf7e192562c550331f6cefb",
    "EVANS-LT":    "da195ad4b82159181922249c",
    "FOSTER-LT":   "da214f7ab51a74bb92f09b06",
}

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode()
    return json.loads(raw) if raw else None

def _value(obj):
    if isinstance(obj, dict):
        return obj.get("value") or obj.get("result") or []
    return obj if isinstance(obj, list) else []

def _devices():
    return _value(_get(INTUNE + "/deviceManagement/managedDevices"))

def _device(device_id):
    return next((d for d in _devices() if str(d.get("id")) == device_id), None)

def _synced(device_id):
    d = _device(device_id) or {}
    results = d.get("deviceActionResults") or []
    return any(str(r.get("actionName")) == "syncDevice" for r in results)

def _group_member_ids():
    members = _value(_get(ENTRA + "/groups/" + GRP_ENFORCED + "/members"))
    return {str(m.get("id")) for m in members if isinstance(m, dict)}

def _alert_status(alert_id):
    alerts = _value(_get(DEFENDER + "/security/alerts_v2"))
    a = next((x for x in alerts if str(x.get("id")) == alert_id), None)
    return str(a.get("status")) if a else None

def _incident_state(sys_id):
    r = _get(SN + "/incident/" + sys_id)
    rec = (r or {}).get("result") if isinstance(r, dict) else None
    return str((rec or {}).get("state")) if rec else None

def test_member_anderson_added():
    assert FIX["ANDERSON-LT"][1] in _group_member_ids()

def test_member_brooks_added():
    assert FIX["BROOKS-LT"][1] in _group_member_ids()

def test_member_chen_added():
    assert FIX["CHEN-LT"][1] in _group_member_ids()

def test_member_diaz_added():
    assert FIX["DIAZ-LT"][1] in _group_member_ids()

def test_member_evans_added():
    assert FIX["EVANS-LT"][1] in _group_member_ids()

def test_member_foster_added():
    assert FIX["FOSTER-LT"][1] in _group_member_ids()

def test_member_ghosh_added():
    assert FIX["GHOSH-LT"][1] in _group_member_ids()

def test_member_haas_added():
    assert FIX["HAAS-LT"][1] in _group_member_ids()

def test_alert_anderson_resolved():
    assert _alert_status(GENUINE_ALERTS["ANDERSON-LT"]) == "resolved"

def test_alert_brooks_resolved():
    assert _alert_status(GENUINE_ALERTS["BROOKS-LT"]) == "resolved"

def test_alert_chen_resolved():
    assert _alert_status(GENUINE_ALERTS["CHEN-LT"]) == "resolved"

def test_alert_diaz_resolved():
    assert _alert_status(GENUINE_ALERTS["DIAZ-LT"]) == "resolved"

def test_alert_evans_resolved():
    assert _alert_status(GENUINE_ALERTS["EVANS-LT"]) == "resolved"

def test_alert_foster_resolved():
    assert _alert_status(GENUINE_ALERTS["FOSTER-LT"]) == "resolved"

def test_sync_anderson():
    assert _synced(FIX["ANDERSON-LT"][0])

def test_sync_brooks():
    assert _synced(FIX["BROOKS-LT"][0])

def test_sync_chen():
    assert _synced(FIX["CHEN-LT"][0])

def test_sync_diaz():
    assert _synced(FIX["DIAZ-LT"][0])

def test_sync_evans():
    assert _synced(FIX["EVANS-LT"][0])

def test_sync_foster():
    assert _synced(FIX["FOSTER-LT"][0])

def test_sync_ghosh():
    assert _synced(FIX["GHOSH-LT"][0])

def test_sync_haas():
    assert _synced(FIX["HAAS-LT"][0])

def test_incident_closed():
    assert _incident_state(INC_SYS) in ("6", "7")
