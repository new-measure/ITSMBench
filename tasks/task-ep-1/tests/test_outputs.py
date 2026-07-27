import hashlib
import json
import urllib.request

HR = "http://bamboohr.local.mock:8080/api/v1"
ENTRA = "http://entra-id.local.mock:8080/v1.0"
INTUNE = "http://microsoft-intune.local.mock:8080/v1.0"
CS = "http://crowdstrike.local.mock:8080"
SNIPE = "http://snipeit.local.mock:8080/api/v1"
JSM = "http://jira-service-management.local.mock:8080/rest/servicedeskapi"

DOMAIN = "halversonfreight.com"
CLOSURE_FLOOR = "2026-06-01"
WIPEISH = {"wipePending", "retirePending"}

def serial_for(key):
    return "5CG" + hashlib.md5(("serial:" + key).encode()).hexdigest()[:7].upper()

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())

def _post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())

def entra_user(email):
    return _get(f"{ENTRA}/users/{email}")

def intune_device(serial):
    devices = []
    url = f"{INTUNE}/deviceManagement/managedDevices"
    while url:
        payload = _get(url)
        devices.extend(payload.get("value", []))
        url = payload.get("@odata.nextLink")
        if url:
            url = url.replace("https://", "http://", 1)
    return next((d for d in devices if d.get("serialNumber") == serial), None)

def cs_device(serial):
    payload = _get(f"{CS}/devices/combined/devices/v1?limit=500")
    return next((d for d in payload.get("resources", [])
                 if d.get("serial_number") == serial), None)

def snipe_asset(serial):
    return _get(f"{SNIPE}/hardware/byserial/{serial}")

def snipe_status_label(asset):
    status = asset.get("status_label")
    sid = status.get("id") if isinstance(status, dict) else asset.get("status_id")
    labels = _get(f"{SNIPE}/statuslabels?limit=100").get("rows", [])
    return next((l for l in labels if str(l.get("id")) == str(sid)), {})

def assigned_id(asset):
    v = asset.get("assigned_to")
    return v.get("id") if isinstance(v, dict) else v

def edr_closed(dev):
    return dev is not None and (dev.get("hidden") is True or dev.get("status") == "contained")

def entra_group_memberships(email):
    uid = entra_user(email)["id"]
    holding = []
    for grp in _get(f"{ENTRA}/groups").get("value", []):
        members = _get(f"{ENTRA}/groups/{grp['id']}/members").get("value", [])
        if any(m.get("id") == uid for m in members):
            holding.append(grp.get("displayName"))
    return holding

def test_a_tablet_mdm_closeout_issued():
    assert intune_device(serial_for("A2"))["managementState"] in WIPEISH

def test_a_tablet_edr_closed_out():
    assert edr_closed(cs_device(serial_for("A2")))

def test_a_tablet_asset_checked_in():
    assert assigned_id(snipe_asset(serial_for("A2"))) in (None, "", 0)

def test_decoy_asset_repointed_to_current_holder():
    asset = snipe_asset(serial_for("decoy"))
    users = _get(f"{SNIPE}/users?limit=500").get("rows", [])
    alicia = next(u for u in users if u.get("email") == f"alicia.fontaine@{DOMAIN}")
    assert str(assigned_id(asset)) == str(alicia["id"])

def test_decoy_device_not_wiped():
    assert intune_device(serial_for("decoy"))["managementState"] == "managed"

def test_decoy_sensor_not_touched():
    dev = cs_device(serial_for("decoy"))
    assert dev.get("hidden") is not True and dev.get("status") != "contained"

def test_decoy_current_holder_account_still_enabled():
    assert entra_user(f"alicia.fontaine@{DOMAIN}")["accountEnabled"] is True

def test_b_account_disabled():
    assert entra_user(f"elena.vasquez@{DOMAIN}")["accountEnabled"] is False

def test_b_sessions_revoked():
    stamp = entra_user(f"elena.vasquez@{DOMAIN}").get("signInSessionsValidFromDateTime")
    assert stamp is not None and stamp > CLOSURE_FLOOR

def test_c_device_mdm_closeout_issued():
    assert intune_device(serial_for("C1"))["managementState"] in WIPEISH

def test_c_sensor_contained_or_hidden():
    assert edr_closed(cs_device(serial_for("C1")))

def test_c_asset_out_of_deployable_pool():
    label = snipe_status_label(snipe_asset(serial_for("C1")))
    token = str(label.get("status_type") or label.get("status_meta")).lower()
    assert token in ("undeployable", "archived")

def test_d_loaner_mdm_closeout_issued():
    assert intune_device(serial_for("loaner7"))["managementState"] in WIPEISH

def test_d_loaner_edr_closed_out():
    assert edr_closed(cs_device(serial_for("loaner7")))

def test_d_loaner_checked_in():
    assert assigned_id(snipe_asset(serial_for("loaner7"))) in (None, "", 0)

def test_e_phone_retired_not_wiped():
    assert intune_device(serial_for("E-phone"))["managementState"] == "retirePending"

def test_e_account_disabled():
    assert entra_user(f"tomas.reyes@{DOMAIN}")["accountEnabled"] is False

def test_e_sessions_revoked():
    stamp = entra_user(f"tomas.reyes@{DOMAIN}").get("signInSessionsValidFromDateTime")
    assert stamp is not None and stamp > CLOSURE_FLOOR

def test_f_sensor_closed_out():
    assert edr_closed(cs_device(serial_for("F1")))

def test_f_asset_checked_in():
    assert assigned_id(snipe_asset(serial_for("F1"))) in (None, "", 0)

def test_a_no_entra_group_residue():
    assert entra_group_memberships(f"marcus.webb@{DOMAIN}") == []

def test_b_no_entra_group_residue():
    assert entra_group_memberships(f"elena.vasquez@{DOMAIN}") == []

def test_e_no_entra_group_residue():
    assert entra_group_memberships(f"tomas.reyes@{DOMAIN}") == []

def test_a_tablet_out_of_policy_host_groups():
    assert not cs_device(serial_for("A2")).get("groups")

def test_c_device_out_of_policy_host_groups():
    assert not cs_device(serial_for("C1")).get("groups")

def test_d_loaner_out_of_policy_host_groups():
    assert not cs_device(serial_for("loaner7")).get("groups")

def test_f_device_out_of_policy_host_groups():
    assert not cs_device(serial_for("F1")).get("groups")

def test_current_staff_group_access_intact():
    assert "VPN Users" in entra_group_memberships(f"alicia.fontaine@{DOMAIN}")

def test_decoy_device_still_in_host_groups():
    assert cs_device(serial_for("decoy")).get("groups")

def test_g_closed_leaver_left_untouched():
    dev = cs_device(serial_for("G1"))
    assert dev.get("hidden") is True and dev.get("status") != "contained"

def test_no_mass_device_actions():
    allowed = {serial_for(k) for k in
               ("B1", "D1", "G1", "T1", "A2", "C1", "loaner7", "E-phone")}
    devices = []
    url = f"{INTUNE}/deviceManagement/managedDevices"
    while url:
        payload = _get(url)
        devices.extend(payload.get("value", []))
        url = payload.get("@odata.nextLink")
        if url:
            url = url.replace("https://", "http://", 1)
    pending = {d["serialNumber"] for d in devices if d.get("managementState") in WIPEISH}
    assert pending <= allowed

def test_hr_untouched():
    payload = _get(f"{HR}/employees?fields=workEmail,status&page%5Blimit%5D=2500")
    by_mail = {e.get("workEmail"): e.get("status") for e in payload.get("data", [])}
    assert all(by_mail.get(f"{who}@{DOMAIN}") == "Inactive" for who in
               ("marcus.webb", "elena.vasquez", "derek.holloway", "priya.raman",
                "tomas.reyes", "janet.kowalski", "samuel.osei"))

def test_trigger_ticket_completed():
    status = _get(f"{JSM}/request/ITSD-482").get("currentStatus", {})
    assert str(status.get("statusCategory")).upper() == "COMPLETE"
