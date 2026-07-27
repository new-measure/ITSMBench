
import json
import urllib.error
import urllib.parse
import urllib.request

ENTRA = "http://entra-id.local.mock:8080/v1.0"
SP = "http://sharepoint.local.mock:8080/v1.0"
OD = "http://onedrive.local.mock:8080/v1.0"
SN = "http://servicenow.local.mock:8080/api/now/table"
DOMAIN = "meridiancap.example"

FIN_SITE = "Corporate Finance"
TITAN_SITE = "Deal Room - Project Titan"
BOARD = "Board Materials"
MODEL = "Project Titan - Financial Model.xlsx"
DD = "Project Titan - Due Diligence"

C_AG = "kofi.mensah@" + DOMAIN
C_MKT1 = "lena.fischer@" + DOMAIN
C_IT1 = "tunde.okafor@" + DOMAIN
C_CD = "sven.larsson@" + DOMAIN
C_MKT2 = "rohan.singh@" + DOMAIN
IT2 = "jia.tan@" + DOMAIN

EXT_VENDOR = "vendor@brightledger.example"
EXT_ZENITH = "former@zenithpartners.example"
EXT_KLEIN = "p.klein@northbridge.example"
EXT_CONTRACTOR = "contractor@brightledger.example"
EXT_ZENITH2 = "dd.temp@zenithpartners.example"

OVER_GROUP_MODEL = "Finance Extended"
OVER_GROUP_DD = "Corporate Development"

def _get(url, allow_404=True):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        if allow_404 and e.code == 404:
            return None
        raise
    return json.loads(raw) if raw else None

def _as_list(obj, *keys):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in keys + ("value", "values", "result", "results", "items", "members", "users"):
            if k in obj and isinstance(obj[k], list):
                return obj[k]
    return []

def _all_groups():
    return _as_list(_get(ENTRA + "/groups?$top=200"))

def _group_id_set():
    return {str(g.get("id")) for g in _all_groups()}

def _group_id_by_name(name):
    for g in _all_groups():
        if str(g.get("displayName")) == name:
            return str(g.get("id"))
    return None

def _expand_group(group_id, group_ids, seen=None):
    seen = seen or set()
    if group_id in seen:
        return set()
    seen.add(group_id)
    out = set()
    for m in _as_list(_get(ENTRA + "/groups/%s/members?$top=200" % group_id)):
        mid = str(m.get("id"))
        if mid in group_ids:
            out |= _expand_group(mid, group_ids, seen)
        else:
            out.add(mid)
    return out

def _user_id_by_email(email):
    for u in _as_list(_get(ENTRA + "/users?$top=400")):
        if str(u.get("mail", "")).lower() == email.lower() or \
           str(u.get("userPrincipalName", "")).lower() == email.lower():
            return str(u.get("id"))
    return None

def _site_id(display):
    for s in _as_list(_get(SP + "/sites?search=")) or _as_list(_get(SP + "/sites")):
        if str(s.get("displayName")) == display or str(s.get("name")) == display:
            return str(s.get("id"))
    return None

def _site_perms(display):
    sid = _site_id(display)
    if not sid:
        return []
    return _as_list(_get(SP + "/sites/%s/permissions" % sid))

def _drive_id():
    drives = _as_list(_get(OD + "/drives"))
    return str(drives[0]["id"]) if drives else None

def _item_id_by_name(name):
    did = _drive_id()
    if not did:
        return None
    queue = list(_as_list(_get(OD + "/drives/%s/root/children" % did)))
    seen = set()
    while queue:
        it = queue.pop(0)
        iid = str(it.get("id"))
        if iid in seen:
            continue
        seen.add(iid)
        if str(it.get("name")) == name:
            return iid
        if it.get("folder"):
            queue.extend(_as_list(_get(OD + "/drives/%s/items/%s/children" % (did, iid))))
    return None

def _item_perms(name):
    did = _drive_id()
    iid = _item_id_by_name(name)
    if not (did and iid):
        return []
    return _as_list(_get(OD + "/drives/%s/items/%s/permissions" % (did, iid)))

def _effective_audience(perms):
    gids = _group_id_set()
    aud = set()
    for pm in perms:
        link = pm.get("link")
        if link:
            sc = str(link.get("scope"))
            if sc in ("anonymous", "anyone"):
                aud.add("*ANON*")
            elif sc in ("organization", "users"):
                aud |= _expand_all_org_users()
            continue
        g = pm.get("grantedToV2", {}) or {}
        if "group" in g:
            aud |= _expand_group(str(g["group"].get("id")), gids)
        elif "user" in g:
            aud.add(str(g["user"].get("id")))
    return aud

_ORG_CACHE = {}

def _expand_all_org_users():
    if "v" not in _ORG_CACHE:
        _ORG_CACHE["v"] = {str(u.get("id")) for u in _as_list(_get(ENTRA + "/users?$top=400"))
                           if str(u.get("userType", "Member")) != "Guest"}
    return _ORG_CACHE["v"]

def _in_audience(perms, email):
    uid = _user_id_by_email(email)
    aud = _effective_audience(perms)
    if "*ANON*" in aud:
        return True
    return uid is not None and uid in aud

def _has_link_scope(perms, scopes):
    return any(str((p.get("link") or {}).get("scope")) in scopes for p in perms)

def _external_directly_granted(perms, email):
    for p in perms:
        u = (p.get("grantedToV2", {}) or {}).get("user", {}) or {}
        if str(u.get("email", "")).lower() == email.lower():
            return True
    return False

def _group_granted(perms, group_name):
    gid = _group_id_by_name(group_name)
    for p in perms:
        g = (p.get("grantedToV2", {}) or {}).get("group", {}) or {}
        if str(g.get("id")) == gid or str(g.get("displayName")) == group_name:
            return True
    return False

def test_finance_nested_group_analytics_guild_cut():
    assert not _in_audience(_site_perms(FIN_SITE), C_AG)

def test_finance_broad_marketing_group_cut():
    assert not _in_audience(_site_perms(FIN_SITE), C_MKT1)

def test_finance_direct_internal_overshare_cut():
    assert not _in_audience(_site_perms(FIN_SITE), C_IT1)

def test_finance_stale_external_vendor_cut():
    assert not _in_audience(_site_perms(FIN_SITE), EXT_VENDOR)

def test_titan_broad_corpdev_group_cut():
    assert not _in_audience(_site_perms(TITAN_SITE), C_CD)

def test_titan_direct_internal_overshare_cut():
    assert not _in_audience(_site_perms(TITAN_SITE), C_MKT2)

def test_titan_stale_external_zenith_cut():
    assert not _in_audience(_site_perms(TITAN_SITE), EXT_ZENITH)

def test_board_no_anonymous_link():
    assert not _has_link_scope(_item_perms(BOARD), {"anonymous", "anyone"})

def test_board_no_organization_link():
    assert not _has_link_scope(_item_perms(BOARD), {"organization", "users"})

def test_board_stale_external_klein_cut():
    assert not _external_directly_granted(_item_perms(BOARD), EXT_KLEIN)

def test_board_direct_internal_overshare_cut():
    assert not _external_directly_granted(_item_perms(BOARD), IT2)

def test_model_no_anonymous_link():
    assert not _has_link_scope(_item_perms(MODEL), {"anonymous", "anyone"})

def test_model_broad_group_finance_extended_cut():
    assert not _group_granted(_item_perms(MODEL), OVER_GROUP_MODEL)

def test_model_stale_external_contractor_cut():
    assert not _external_directly_granted(_item_perms(MODEL), EXT_CONTRACTOR)

def test_dd_no_organization_link():
    assert not _has_link_scope(_item_perms(DD), {"organization", "users"})

def test_dd_no_anonymous_link():
    assert not _has_link_scope(_item_perms(DD), {"anonymous", "anyone"})

def test_dd_stale_external_zenith2_cut():
    assert not _external_directly_granted(_item_perms(DD), EXT_ZENITH2)

def test_dd_broad_group_corpdev_cut():
    assert not _group_granted(_item_perms(DD), OVER_GROUP_DD)

def test_governance_ticket_closed():
    rows = _as_list(_get(SN + "/incident?sysparm_query=" + urllib.parse.quote("number=INC0071500")))
    assert rows
    s = str(rows[0].get("state")).lower()
    assert s in ("6", "7") or "clos" in s or "resolv" in s
