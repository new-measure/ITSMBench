import json
import urllib.request
import urllib.error

JC = "http://jumpcloud.local.mock:8080/api"
JC2 = "http://jumpcloud.local.mock:8080/api/v2"
OKTA = "http://okta.local.mock:8080/api/v1"
S1 = "http://sentinelone.local.mock:8080/web/api/v2.1"
D42 = "http://device42.local.mock:8080/api/2.0"
SN = "http://servicenow.local.mock:8080/api/now/table"

JC_UID = {"marcus": "jcu-marcus", "elena": "jcu-elena", "raj": "jcu-raj",
          "priya": "jcu-priya", "dana": "jcu-dana", "hannah": "jcu-hannah"}
OKTA_UID = {"priya": "oktu-priya", "tomas": "oktu-tomas", "owen": "oktu-owen"}

MARCUS_NAME = "Marcus Webb"
ELENA_NAME = "Elena Fischer"
OWEN_NAME = "Owen Frost"
DEPARTED_NAMES = {"Dana Osei", "Elena Fischer", "Hannah Vogt", "Marcus Webb",
                  "Owen Frost", "Priya Nair", "Raj Malhotra", "Tomas Novak"}

RAJ_DEVICE = "5001"
HANNAH_DEVICES = ("5010", "5011")
INCIDENT = "sn-inc-offboarding-001"

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    return json.loads(raw) if raw else None

def _as_list(obj, *keys):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in keys + ("data", "resources", "value", "results", "result"):
            if k in obj and isinstance(obj[k], list):
                return obj[k]
    return []

def _jc_active(uid):
    u = _get(JC + "/systemusers/" + uid)
    if u is None:
        return False
    return str(u.get("state")) == "ACTIVATED"

def _jc_group_member_ids(gid):
    return {str((c.get("to") or {}).get("id")) for c in _as_list(_get(JC2 + "/usergroups/%s/members" % gid))}

def test_marcus_jc_disabled():
    assert not _jc_active(JC_UID["marcus"])

def test_elena_jc_disabled():
    assert not _jc_active(JC_UID["elena"])

def test_raj_jc_disabled():
    assert not _jc_active(JC_UID["raj"])

def test_priya_jc_disabled():
    assert not _jc_active(JC_UID["priya"])

def test_dana_jc_disabled():
    assert not _jc_active(JC_UID["dana"])

def test_hannah_jc_disabled():
    assert not _jc_active(JC_UID["hannah"])

def test_marcus_removed_from_secops():
    assert JC_UID["marcus"] not in _jc_group_member_ids("jcg-secops")

def test_marcus_removed_from_allstaff():
    assert JC_UID["marcus"] not in _jc_group_member_ids("jcg-allstaff")

def test_elena_removed_from_endpoint():
    assert JC_UID["elena"] not in _jc_group_member_ids("jcg-endpoint")

def test_elena_removed_from_allstaff():
    assert JC_UID["elena"] not in _jc_group_member_ids("jcg-allstaff")

def test_raj_removed_from_infra():
    assert JC_UID["raj"] not in _jc_group_member_ids("jcg-infra")

def test_raj_removed_from_allstaff():
    assert JC_UID["raj"] not in _jc_group_member_ids("jcg-allstaff")

def test_priya_removed_from_soc():
    assert JC_UID["priya"] not in _jc_group_member_ids("jcg-soc")

def test_dana_removed_from_cloud():
    assert JC_UID["dana"] not in _jc_group_member_ids("jcg-cloud")

def test_dana_removed_from_badge():
    assert JC_UID["dana"] not in _jc_group_member_ids("jcg-badge")

def test_dana_removed_from_allstaff():
    assert JC_UID["dana"] not in _jc_group_member_ids("jcg-allstaff")

def test_hannah_removed_from_infra():
    assert JC_UID["hannah"] not in _jc_group_member_ids("jcg-infra")

def test_hannah_removed_from_allstaff():
    assert JC_UID["hannah"] not in _jc_group_member_ids("jcg-allstaff")

def _okta_active(uid):
    u = _get(OKTA + "/users/" + uid)
    if u is None:
        return False
    return str(u.get("status")) not in ("DEPROVISIONED", "SUSPENDED")

def _okta_group_member_ids(gid):
    return {str(u.get("id")) for u in _as_list(_get(OKTA + "/groups/%s/users" % gid))}

def _okta_app_user_ids(app):
    return {str(u.get("id")) for u in _as_list(_get(OKTA + "/apps/%s/users" % app))}

def test_priya_okta_disabled():
    assert not _okta_active(OKTA_UID["priya"])

def test_tomas_okta_disabled():
    assert not _okta_active(OKTA_UID["tomas"])

def test_owen_okta_disabled():
    assert not _okta_active(OKTA_UID["owen"])

def test_priya_removed_from_okta_group():
    assert OKTA_UID["priya"] not in _okta_group_member_ids("oktg-soc-ext")

def test_tomas_removed_from_okta_group():
    assert OKTA_UID["tomas"] not in _okta_group_member_ids("oktg-consultants")

def test_owen_removed_from_okta_group():
    assert OKTA_UID["owen"] not in _okta_group_member_ids("oktg-consultants")

def test_priya_removed_from_vpn_app():
    assert OKTA_UID["priya"] not in _okta_app_user_ids("okta-app-vpn")

def test_tomas_removed_from_vpn_app():
    assert OKTA_UID["tomas"] not in _okta_app_user_ids("okta-app-vpn")

def test_owen_removed_from_vpn_app():
    assert OKTA_UID["owen"] not in _okta_app_user_ids("okta-app-vpn")

def _s1_exclusion_authors():
    return {str(e.get("userName")) for e in _as_list(_get(S1 + "/exclusions"))}

def test_marcus_sentinelone_exclusion_removed():
    assert MARCUS_NAME not in _s1_exclusion_authors()

def test_elena_sentinelone_exclusion_removed():
    assert ELENA_NAME not in _s1_exclusion_authors()

def test_owen_sentinelone_exclusion_removed():
    assert OWEN_NAME not in _s1_exclusion_authors()

def _device_owner(dev_id):
    dev = _get(D42 + "/devices/%s/" % dev_id)
    return dev, str((dev or {}).get("owner") or "").strip()

def test_raj_device_retains_active_owner():
    dev, owner = _device_owner(RAJ_DEVICE)
    assert dev is not None and owner != "" and owner not in DEPARTED_NAMES

def test_hannah_device_5010_retains_active_owner():
    dev, owner = _device_owner(HANNAH_DEVICES[0])
    assert dev is not None and owner != "" and owner not in DEPARTED_NAMES

def test_hannah_device_5011_retains_active_owner():
    dev, owner = _device_owner(HANNAH_DEVICES[1])
    assert dev is not None and owner != "" and owner not in DEPARTED_NAMES

def test_incident_closed():
    r = _get(SN + "/incident/" + INCIDENT)
    state = str(((r or {}).get("result") or {}).get("state"))
    assert state in ("6", "7")
