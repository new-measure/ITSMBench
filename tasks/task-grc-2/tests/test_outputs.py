import json
import urllib.error
import urllib.request
from datetime import datetime, timezone

VANTA = "http://vanta.local.mock:8080/v1"
SN = "http://servicenow.local.mock:8080/api/now/table"

NOW = datetime(2026, 7, 18, 9, 0, 0, tzinfo=timezone.utc)
INC_SYS = "be578f6b3f30029c11f83ab3ba492cb7"

A_IDS = ["vendor-a1", "vendor-a2", "vendor-a3", "vendor-a4", "vendor-a5"]
C_IDS = ["vendor-c1", "vendor-c2", "vendor-c3", "vendor-c4"]
D_IDS = ["vendor-d1", "vendor-d2", "vendor-d3", "vendor-d4"]
B_FINDINGS = {"vendor-b1": "finding-b1", "vendor-b2": "finding-b2", "vendor-b3": "finding-b3",
              "vendor-b4": "finding-b4", "vendor-b5": "finding-b5"}

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode()
    return json.loads(raw) if raw and raw.strip()[:1] in "{[" else raw

def _vanta_list(path):
    sep = "&" if "?" in path else "?"
    d = _get(VANTA + path + sep + "pageSize=100")
    return ((d or {}).get("results") or {}).get("data") or []

def _vendor(vid):
    v = _get(VANTA + "/vendors/%s" % vid)
    return v if isinstance(v, dict) else {}

def _findings(vid):
    return _vanta_list("/vendors/%s/findings" % vid)

def _parse(dt):
    if not dt:
        return None
    try:
        return datetime.fromisoformat(str(dt).replace("Z", "+00:00"))
    except ValueError:
        return None

FLAGGABLE_DECISION = {"NOT_APPROVED", "CONDITIONALLY_APPROVED"}

def _flag_signal(vid):
    v = _vendor(vid)
    if str(v.get("status")) != "MANAGED":
        return True
    return str((v.get("latestDecision") or {}).get("status")) in FLAGGABLE_DECISION

def _has_open_remediate(vid):
    return any(str(f.get("riskStatus")) == "REMEDIATE"
               and str((f.get("remediation") or {}).get("state")) != "CLOSED"
               for f in _findings(vid))

def _flagged(vid):
    return _flag_signal(vid) or _has_open_remediate(vid)

def test_a1_failed_assessment_reflagged():
    assert _flagged("vendor-a1")

def test_a2_failed_assessment_reflagged():
    assert _flagged("vendor-a2")

def test_a3_failed_assessment_reflagged():
    assert _flagged("vendor-a3")

def test_a4_failed_assessment_reflagged():
    assert _flagged("vendor-a4")

def test_a5_failed_assessment_reflagged():
    assert _flagged("vendor-a5")

def _finding_actioned(vid):
    if _flag_signal(vid):
        return True
    fid = B_FINDINGS[vid]
    f = next((x for x in _findings(vid) if str(x.get("id")) == fid), None)
    if f is None:
        return False
    if str(f.get("riskStatus")) != "REMEDIATE":
        return True
    return str((f.get("remediation") or {}).get("state")) == "CLOSED"

def test_b1_open_finding_actioned():
    assert _finding_actioned("vendor-b1")

def test_b2_open_finding_actioned():
    assert _finding_actioned("vendor-b2")

def test_b3_open_finding_actioned():
    assert _finding_actioned("vendor-b3")

def test_b4_open_finding_actioned():
    assert _finding_actioned("vendor-b4")

def test_b5_open_finding_actioned():
    assert _finding_actioned("vendor-b5")

def test_c1_ungoverned_access_flagged():
    assert _flagged("vendor-c1")

def test_c2_ungoverned_access_flagged():
    assert _flagged("vendor-c2")

def test_c3_ungoverned_access_flagged():
    assert _flagged("vendor-c3")

def test_c4_ungoverned_access_flagged():
    assert _flagged("vendor-c4")

def _overdue_handled(vid):
    if _flagged(vid):
        return True
    due = _parse(_vendor(vid).get("nextSecurityReviewDueDate"))
    return bool(due and due > NOW)

def test_d1_overdue_reassessment_handled():
    assert _overdue_handled("vendor-d1")

def test_d2_overdue_reassessment_handled():
    assert _overdue_handled("vendor-d2")

def test_d3_overdue_reassessment_handled():
    assert _overdue_handled("vendor-d3")

def test_d4_overdue_reassessment_handled():
    assert _overdue_handled("vendor-d4")

def test_ticket_closed():
    r = _get(SN + "/incident/" + INC_SYS)
    rec = (r or {}).get("result") if isinstance(r, dict) else None
    assert rec is not None
    s = str(rec.get("state")).lower()
    assert s in ("6", "7") or "clos" in s or "resolv" in s
