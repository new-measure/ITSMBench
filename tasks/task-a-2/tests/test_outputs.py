
import json
import urllib.parse
import urllib.request

SN = "http://servicenow.local.mock:8080"
CS = "http://crowdstrike.local.mock:8080"
INTUNE = "http://microsoft-intune.local.mock:8080"
SNIPE = "http://snipeit.local.mock:8080/api/v1"

CALLER_EMAIL = "marcus.reilly@nimbuslattice.com"
SERIAL = "NLX7F4KQ2P9"
HOSTNAME = "NL-LT-4471"
CS_DEVICE_ID = "5f9c2e7a4b1d8c3e6f0a9b2c7d4e1f80"
SHA256 = "9d3f1c7a2b8e4f60d15a93c47e0b26f8a1c4d97e5302f8b6ae19c4d70f3b82a5"
SEEDED_IOC_ID = "b7c100000000000000000000000000000000000000000000000000000000aa11"
INCIDENT_NUMBER = "INC0010042"
RESPONDER = "IT Security Operations"
SEEDED_LAST_SYNC = "2026-01-05T09:12:00Z"
SEEDED_LAST_AUDIT = "2025-11-20"

TIMEOUT = 30

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = resp.read().decode("utf-8")
    try:
        return json.loads(raw) if raw else None
    except json.JSONDecodeError:
        return raw

def _fql(field, value):
    return urllib.parse.quote(f"{field}:'{value}'", safe="")

def cs_device():
    data = _get(f"{CS}/devices/combined/devices/v1?filter={_fql('serial_number', SERIAL)}")
    res = (data or {}).get("resources", []) if isinstance(data, dict) else []
    return res[0] if res else {}

def cs_malware_ioc_list():
    data = _get(f"{CS}/iocs/combined/indicator/v1?filter={_fql('value', SHA256)}")
    res = (data or {}).get("resources", []) if isinstance(data, dict) else []
    return [i for i in res if not i.get("deleted")]

def cs_malware_alert():
    data = _get(f"{CS}/alerts/combined/alerts/v1?filter={_fql('agent_id', CS_DEVICE_ID)}")
    res = (data or {}).get("resources", []) if isinstance(data, dict) else []
    for alert in res:
        if str(alert.get("sha256", "")).lower() == SHA256.lower():
            return alert
    return {}

def intune_device():
    flt = urllib.parse.urlencode({"$filter": f"serialNumber eq '{SERIAL}'"})
    data = _get(f"{INTUNE}/v1.0/deviceManagement/managedDevices?{flt}")
    val = (data or {}).get("value", []) if isinstance(data, dict) else []
    for dev in val:
        if str(dev.get("serialNumber")) == SERIAL:
            return dev
    data = _get(f"{INTUNE}/v1.0/deviceManagement/managedDevices?{urllib.parse.urlencode({'$top': 999})}")
    for dev in (data or {}).get("value", []) if isinstance(data, dict) else []:
        if str(dev.get("serialNumber")) == SERIAL or str(dev.get("userPrincipalName", "")).lower() == CALLER_EMAIL.lower():
            return dev
    return val[0] if val else {}

def intune_action_states(action_name):
    dev = intune_device()
    return [
        r.get("actionState")
        for r in (dev.get("deviceActionResults") or [])
        if r.get("actionName") == action_name
    ]

def sn_incident():
    q = urllib.parse.urlencode({"sysparm_query": f"number={INCIDENT_NUMBER}"})
    data = _get(f"{SN}/api/now/table/incident?{q}")
    res = (data or {}).get("result", []) if isinstance(data, dict) else []
    return res[0] if res else {}

def sn_target_problem():
    q = urllib.parse.urlencode({"sysparm_query": f"short_descriptionLIKE{HOSTNAME}^ORdescriptionLIKE{HOSTNAME}^ORroot_causeLIKE{HOSTNAME}"})
    data = _get(f"{SN}/api/now/table/problem?{q}")
    res = (data or {}).get("result", []) if isinstance(data, dict) else []
    return res[0] if res else {}

def snipe_asset():
    data = _get(f"{SNIPE}/hardware?{urllib.parse.urlencode({'search': SERIAL})}")
    rows = (data or {}).get("rows", []) if isinstance(data, dict) else []
    asset = next((r for r in rows if str(r.get("serial")) == SERIAL), None)
    if not asset:
        return {}
    return _get(f"{SNIPE}/hardware/{asset.get('id')}") or {}

def test_crowdstrike_containment_lifted():
    assert str(cs_device().get("status", "")).lower() == "normal"

def test_crowdstrike_malware_hash_blocked():
    iocs = cs_malware_ioc_list()
    assert len(iocs) == 1 and str(iocs[0].get("action", "")).lower() == "prevent"

def test_crowdstrike_detection_closed():
    assert str(cs_malware_alert().get("status", "")).lower() == "closed"

def test_crowdstrike_detection_assigned_to_responder():
    assert cs_malware_alert().get("assigned_to_name") == RESPONDER

def test_intune_defender_scan_ran():
    assert "done" in intune_action_states("windowsDefenderScan")

def test_intune_device_resynced():
    assert "done" in intune_action_states("syncDevice")

def test_intune_last_sync_advanced():
    assert intune_device().get("lastSyncDateTime") not in (None, "", SEEDED_LAST_SYNC)

def test_incident_reclassified_security():
    assert str(sn_incident().get("category", "")).lower() == "security"

def test_incident_state_closed():
    assert str(sn_incident().get("state", "")) == "7"

def test_incident_inactive():
    assert sn_incident().get("active") in (False, "false")

def test_incident_close_code_permanent():
    assert sn_incident().get("close_code") == "Solved (Permanently)"

def test_incident_close_notes_name_malware():
    assert "malware" in str(sn_incident().get("close_notes", "")).lower()

def test_problem_root_cause_names_malware():
    assert "malware" in str(sn_target_problem().get("root_cause", "")).lower()

def test_problem_root_cause_names_exact_hash():
    assert SHA256 in str(sn_target_problem().get("root_cause", ""))

def test_problem_product_area_endpoint_security():
    assert str(sn_target_problem().get("u_product_area", "")).lower() == "endpoint security"

def test_problem_short_description_names_malware():
    assert "malware" in str(sn_target_problem().get("short_description", "")).lower()

def test_asset_audited():
    assert snipe_asset().get("last_audit_date") not in (None, "", SEEDED_LAST_AUDIT)

def test_intune_device_not_wiped_or_retired():
    assert str(intune_device().get("managementState", "")).lower() == "managed"

def test_intune_device_still_compliant():
    assert str(intune_device().get("complianceState", "")).lower() == "compliant"

def test_malware_ioc_escalated_in_place():
    iocs = cs_malware_ioc_list()
    seeded = next((i for i in iocs if i.get("id") == SEEDED_IOC_ID), None)
    assert seeded is not None and str(seeded.get("action", "")).lower() == "prevent"
