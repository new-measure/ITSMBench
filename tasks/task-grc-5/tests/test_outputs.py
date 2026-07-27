import json
import urllib.error
import urllib.request

PURVIEW = "http://purview.local.mock:8080/v1.0"
SN = "http://servicenow.local.mock:8080/api/now/table"

ACTIVE_GAP = [
    ("case-aurora", "cust-aur-1"), ("case-aurora", "cust-aur-2"), ("case-aurora", "cust-aur-3"),
    ("case-aurora", "cust-aur-6"),
    ("case-nimbus", "cust-nim-1"), ("case-nimbus", "cust-nim-2"),
    ("case-nimbus", "cust-nim-3"),
    ("case-nimbus", "cust-nim-5"),
    ("case-titan", "cust-tit-3"),
    ("case-titan", "cust-tit-1"),
    ("case-titan", "cust-tit-2"),
]
CLOSED_GAP = [
    ("case-zephyr", "cust-zep-1"), ("case-zephyr", "cust-zep-2"), ("case-zephyr", "cust-zep-3"),
    ("case-orion", "cust-ori-1"), ("case-orion", "cust-ori-2"), ("case-orion", "cust-ori-3"),
    ("case-vesta", "cust-ves-1"), ("case-vesta", "cust-ves-2"), ("case-vesta", "cust-ves-3"),
]
RETENTION_GAP_TYPES = ["ret-type-departure", "ret-type-contract", "ret-type-producteol"]
INC_SYS = "415e2e7a663d900499532f8cb4fdd733"

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode()
    return json.loads(raw) if raw and raw.strip()[:1] in "{[" else raw

def _custodian(case_id, cust_id):
    return _get(PURVIEW + "/security/cases/ediscoveryCases/%s/custodians/%s" % (case_id, cust_id))

def _on_hold(case_id, cust_id):
    c = _custodian(case_id, cust_id)
    return isinstance(c, dict) and str(c.get("status")) == "active" and str(c.get("holdStatus")) == "applied"

def _hold_lifted(case_id, cust_id):
    c = _custodian(case_id, cust_id)
    if not isinstance(c, dict):
        return False
    return str(c.get("status")) == "released" or str(c.get("holdStatus")) == "notApplied"

def _events_for_type(et):
    d = _get(PURVIEW + "/security/triggers/retentionEvents")
    evs = (d or {}).get("value", []) if isinstance(d, dict) else []
    return [e for e in evs if str((e.get("retentionEventType") or {}).get("id")) == et]

def test_active_hold_01_aurora_notapplied():
    assert _on_hold(*ACTIVE_GAP[0])

def test_active_hold_02_aurora_notapplied():
    assert _on_hold(*ACTIVE_GAP[1])

def test_active_hold_03_aurora_notapplied():
    assert _on_hold(*ACTIVE_GAP[2])

def test_active_hold_04_aurora_partial():
    assert _on_hold(*ACTIVE_GAP[3])

def test_active_hold_05_nimbus_notapplied():
    assert _on_hold(*ACTIVE_GAP[4])

def test_active_hold_06_nimbus_notapplied():
    assert _on_hold(*ACTIVE_GAP[5])

def test_active_hold_07_nimbus_never_activated():
    assert _on_hold(*ACTIVE_GAP[6])

def test_active_hold_08_nimbus_applying():
    assert _on_hold(*ACTIVE_GAP[7])

def test_active_hold_09_titan_notapplied():
    assert _on_hold(*ACTIVE_GAP[8])

def test_active_hold_10_titan_partial():
    assert _on_hold(*ACTIVE_GAP[9])

def test_active_hold_11_titan_never_activated():
    assert _on_hold(*ACTIVE_GAP[10])

def test_closed_release_1():
    assert _hold_lifted(*CLOSED_GAP[0])

def test_closed_release_2():
    assert _hold_lifted(*CLOSED_GAP[1])

def test_closed_release_3():
    assert _hold_lifted(*CLOSED_GAP[2])

def test_closed_release_4():
    assert _hold_lifted(*CLOSED_GAP[3])

def test_closed_release_5():
    assert _hold_lifted(*CLOSED_GAP[4])

def test_closed_release_6():
    assert _hold_lifted(*CLOSED_GAP[5])

def test_closed_release_7():
    assert _hold_lifted(*CLOSED_GAP[6])

def test_closed_release_8():
    assert _hold_lifted(*CLOSED_GAP[7])

def test_closed_release_9():
    assert _hold_lifted(*CLOSED_GAP[8])

def test_retention_event_departure():
    assert len(_events_for_type(RETENTION_GAP_TYPES[0])) >= 1

def test_retention_event_contract():
    assert len(_events_for_type(RETENTION_GAP_TYPES[1])) >= 1

def test_retention_event_producteol():
    assert len(_events_for_type(RETENTION_GAP_TYPES[2])) >= 1

def test_ticket_closed():
    r = _get(SN + "/incident/" + INC_SYS)
    rec = (r or {}).get("result") if isinstance(r, dict) else None
    assert rec is not None
    s = str(rec.get("state")).lower()
    assert s in ("6", "7") or "clos" in s or "resolv" in s
