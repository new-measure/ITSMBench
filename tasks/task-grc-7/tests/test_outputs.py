import json
import urllib.error
import urllib.parse
import urllib.request

SN = "http://servicenow.local.mock:8080/api/now/table"

ACTIVE = {"open", "in_progress", "in progress", "assigned", "reopened"}
INACTIVE = {"resolved", "closed"}

def _req(method, url, body=None):
    data, headers = None, {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode()
    return json.loads(raw) if raw and raw.strip()[:1] in "{[" else raw

def _items(cve, host):
    q = urllib.parse.quote("u_cve=%s^u_asset=%s" % (cve, host))
    r = _req("GET", SN + "/u_vuln_item?sysparm_query=" + q + "&sysparm_limit=1000")
    return (r or {}).get("result", []) if isinstance(r, dict) else []

def _active(cve, host):
    return [t for t in _items(cve, host) if str(t.get("u_state")) in ACTIVE]

def test_fc_web_prod_01_reopened():
    assert len([t for t in _items("CVE-2026-0101", "web-prod-01") if str(t.get("u_state")) in ACTIVE]) >= 1

def test_fc_api_prod_01_reopened():
    assert len([t for t in _items("CVE-2026-0102", "api-prod-01") if str(t.get("u_state")) in ACTIVE]) >= 1

def test_fc_db_prod_01_reopened():
    assert len([t for t in _items("CVE-2026-0103", "db-prod-01") if str(t.get("u_state")) in ACTIVE]) >= 1

def test_fc_auth_prod_01_reopened():
    assert len([t for t in _items("CVE-2026-0104", "auth-prod-01") if str(t.get("u_state")) in ACTIVE]) >= 1

def test_fc_gw_prod_01_reopened():
    assert len([t for t in _items("CVE-2026-0105", "gw-prod-01") if str(t.get("u_state")) in ACTIVE]) >= 1

def test_fc_bastion_01_reopened():
    assert len([t for t in _items("CVE-2026-0110", "bastion-01") if str(t.get("u_state")) in ACTIVE]) >= 1

def test_reconcile_worker_prod_01_ticket_raised():
    assert len(_active("CVE-2026-0201", "worker-prod-01")) >= 1

def test_reconcile_cache_prod_01_ticket_raised():
    assert len(_active("CVE-2026-0202", "cache-prod-01")) >= 1

def test_reconcile_k8s_node_01_ticket_raised():
    assert len(_active("CVE-2026-0203", "k8s-node-01")) >= 1

def test_reconcile_log_prod_01_ticket_raised():
    assert len(_active("CVE-2026-0204", "log-prod-01")) >= 1

def _escalated(cve, host):
    for t in _items(cve, host):
        assigned = bool(str(t.get("u_assignment_group") or "")) or bool(str(t.get("u_assigned_to") or ""))
        advanced = str(t.get("u_state")) in {"in_progress", "in progress", "assigned", "escalated", "reopened"}
        if assigned and advanced:
            return True
    return False

def test_sla_db_prod_02_escalated():
    assert _escalated("CVE-2026-0301", "db-prod-02")

def test_sla_log_prod_01_escalated():
    assert _escalated("CVE-2026-0302", "log-prod-01")

def test_sla_mail_prod_01_escalated():
    assert _escalated("CVE-2026-0303", "mail-prod-01")

def _accepted(cve, host):
    return any(str(t.get("u_state")) in {"risk_accepted", "accepted"} for t in _items(cve, host))

def test_ra_bastion_01_accepted():
    assert _accepted("CVE-2026-0401", "bastion-01")

def test_ra_k8s_node_02_accepted():
    assert _accepted("CVE-2026-0402", "k8s-node-02")

def test_ra_web_prod_02_accepted():
    assert _accepted("CVE-2026-0403", "web-prod-02")

def test_ra_gw_prod_01_accepted():
    assert _accepted("CVE-2026-0407", "gw-prod-01")

def test_dup_api_prod_01_single_active():
    assert len(_active("CVE-2026-0501", "api-prod-01")) == 1

def test_dup_db_prod_01_single_active():
    assert len(_active("CVE-2026-0502", "db-prod-01")) == 1

def test_incident_closed():
    r = _req("GET", SN + "/incident?sysparm_query=" + urllib.parse.quote("number=INC0030001"))
    rec = (r or {}).get("result", []) if isinstance(r, dict) else []
    assert rec
    s = str(rec[0].get("state")).lower()
    assert s in ("6", "7") or "clos" in s or "resolv" in s
