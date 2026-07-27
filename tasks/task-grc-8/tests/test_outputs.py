import json
import urllib.error
import urllib.request

GH = "http://github.local.mock:8080"
SN = "http://servicenow.local.mock:8080/api/now/table"
ORG = "acme-cloud"
INC_SYS = "512d99eb2eedcad49beac2ff75a0ceec"

BP_TARGETS = [("billing-api", "main"), ("payments-ledger", "release"), ("checkout-web", "mainline"),
              ("orders-ingest", "develop"), ("auth-service", "trunk")]
COLLAB_TARGETS = [("billing-api", "dparker"), ("auth-service", "rfoster"),
                  ("payments-ledger", "twong"), ("checkout-web", "lgomez")]
KEY_TARGETS = [("billing-api", 6001), ("checkout-web", 6002), ("payments-ledger", 6003),
               ("orders-ingest", 6004)]
OUTSIDE_TARGETS = ["contractor-al", "ext-audit", "freelance-kim", "pentest-guest"]

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
        return resp.status, (json.loads(raw) if raw and raw.strip()[:1] in "{[" else raw)
    except urllib.error.HTTPError as e:
        return e.code, None

def _protected(repo, branch):
    code, prot = _get("%s/repos/%s/%s/branches/%s/protection" % (GH, ORG, repo, branch))
    if code != 200 or not isinstance(prot, dict):
        return False
    rpr = prot.get("required_pull_request_reviews") or {}
    return int(rpr.get("required_approving_review_count") or 0) >= 1

def _collab_logins(repo):
    code, d = _get("%s/repos/%s/%s/collaborators" % (GH, ORG, repo))
    return {str(c.get("login")) for c in d} if isinstance(d, list) else set()

def _key_ids(repo):
    code, d = _get("%s/repos/%s/%s/keys" % (GH, ORG, repo))
    return {int(k.get("id")) for k in d if k.get("id") is not None} if isinstance(d, list) else set()

def _outside_logins():
    code, d = _get("%s/orgs/%s/outside_collaborators" % (GH, ORG))
    return {str(o.get("login")) for o in d} if isinstance(d, list) else set()

def test_bp_billing_api_protected():
    assert _protected("billing-api", "main")

def test_bp_payments_ledger_protected():
    assert _protected("payments-ledger", "release")

def test_bp_checkout_web_protected():
    assert _protected("checkout-web", "mainline")

def test_bp_orders_ingest_protected():
    assert _protected("orders-ingest", "develop")

def test_bp_auth_service_protected():
    assert _protected("auth-service", "trunk")

def test_collab_dparker_removed_billing_api():
    assert "dparker" not in _collab_logins("billing-api")

def test_collab_rfoster_removed_auth_service():
    assert "rfoster" not in _collab_logins("auth-service")

def test_collab_twong_removed_payments_ledger():
    assert "twong" not in _collab_logins("payments-ledger")

def test_collab_lgomez_removed_checkout_web():
    assert "lgomez" not in _collab_logins("checkout-web")

def test_key_removed_billing_api():
    assert 6001 not in _key_ids("billing-api")

def test_key_removed_checkout_web():
    assert 6002 not in _key_ids("checkout-web")

def test_key_removed_payments_ledger():
    assert 6003 not in _key_ids("payments-ledger")

def test_key_removed_orders_ingest():
    assert 6004 not in _key_ids("orders-ingest")

def test_outside_contractor_al_removed():
    assert "contractor-al" not in _outside_logins()

def test_outside_ext_audit_removed():
    assert "ext-audit" not in _outside_logins()

def test_outside_freelance_kim_removed():
    assert "freelance-kim" not in _outside_logins()

def test_outside_pentest_guest_removed():
    assert "pentest-guest" not in _outside_logins()

def test_ticket_closed():
    code, r = _get(SN + "/incident/" + INC_SYS)
    rec = (r or {}).get("result") if isinstance(r, dict) else None
    assert rec is not None
    s = str(rec.get("state")).lower()
    assert s in ("6", "7") or "clos" in s or "resolv" in s
