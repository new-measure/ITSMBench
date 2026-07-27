import email.utils
import json
import urllib.error
import urllib.request

SP = "http://sharepoint.local.mock:8080/v1.0"
SN = "http://servicenow.local.mock:8080/api/now/table"
ANON = {"anonymous", "anyone"}
ELEVATED = {"write", "owner"}
INC_SYS = "166b8ffefcc97588f3d7f1bbfd87338c"

CAP_GAP_SITES = ["site-fin", "site-hr", "site-sales"]
PERM_GAP = [("site-fin", "perm-fin-ext"), ("site-hr", "perm-hr-ext1"),
            ("site-hr", "perm-hr-ext2"), ("site-sales", "perm-sales-ext")]
LINK_GAP = [("drive-fin", "item-fin-1"), ("drive-hr", "item-hr-1"),
            ("drive-legal", "item-legal-1"), ("drive-legal", "item-legal-2"),
            ("drive-sales", "item-sales-1"), ("drive-sales", "item-sales-rej")]
LIST_GAP = [("site-fin", "list-fin"), ("site-hr", "list-hr"), ("site-sales", "list-sales")]

def _get(url):
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
        return json.loads(raw) if raw and raw.strip()[:1] in "{[" else raw
    except urllib.error.HTTPError:
        return None

def _perms(site_id):
    d = _get(SP + "/sites/%s/permissions" % site_id)
    return (d or {}).get("value", []) if isinstance(d, dict) else []

def _perm(site_id, perm_id):
    return next((p for p in _perms(site_id) if str(p.get("id")) == perm_id), None)

def _item(drive_id, item_id):
    return _get(SP + "/drives/%s/items/%s" % (drive_id, item_id))

def _list(site_id, list_id):
    return _get(SP + "/sites/%s/lists/%s" % (site_id, list_id))

def _cap_safe(site_id):
    s = _get(SP + "/sites/%s" % site_id)
    return isinstance(s, dict) and str(s.get("sharingCapability")) != "externalUserAndGuestSharing"

def _perm_remediated(site_id, perm_id):
    p = _perm(site_id, perm_id)
    if p is None:
        return True
    return not ({str(r).lower() for r in p.get("roles", [])} & ELEVATED)

def _link_remediated(drive_id, item_id):
    it = _item(drive_id, item_id)
    if not isinstance(it, dict):
        return False
    lk = it.get("link")
    if not lk:
        return True
    if str(lk.get("scope", "")).lower() not in ANON:
        return True
    exp = lk.get("expirationDateTime")
    return bool(exp) and str(exp)[:10] < "2026-07-20"

def _list_safe(site_id, list_id):
    x = _list(site_id, list_id)
    return isinstance(x, dict) and str(x.get("defaultLinkScope", "")).lower() not in ANON

def test_cap_fin():
    assert _cap_safe(CAP_GAP_SITES[0])

def test_cap_hr():
    assert _cap_safe(CAP_GAP_SITES[1])

def test_cap_sales():
    assert _cap_safe(CAP_GAP_SITES[2])

def test_perm_fin_ext():
    assert _perm_remediated(*PERM_GAP[0])

def test_perm_hr_ext1():
    assert _perm_remediated(*PERM_GAP[1])

def test_perm_hr_ext2():
    assert _perm_remediated(*PERM_GAP[2])

def test_perm_sales_ext():
    assert _perm_remediated(*PERM_GAP[3])

def test_link_fin_1():
    assert _link_remediated(*LINK_GAP[0])

def test_link_hr_1_expired_exception():
    assert _link_remediated(*LINK_GAP[1])

def test_link_legal_1_residue():
    assert _link_remediated(*LINK_GAP[2])

def test_link_legal_2_residue():
    assert _link_remediated(*LINK_GAP[3])

def test_link_sales_1():
    assert _link_remediated(*LINK_GAP[4])

def test_link_sales_rejected_exception():
    assert _link_remediated(*LINK_GAP[5])

def test_list_fin():
    assert _list_safe(*LIST_GAP[0])

def test_list_hr():
    assert _list_safe(*LIST_GAP[1])

def test_list_sales():
    assert _list_safe(*LIST_GAP[2])

def test_ticket_closed():
    r = _get(SN + "/incident/" + INC_SYS)
    rec = (r or {}).get("result") if isinstance(r, dict) else None
    assert rec is not None
    s = str(rec.get("state")).lower()
    assert s in ("6", "7") or "clos" in s or "resolv" in s
