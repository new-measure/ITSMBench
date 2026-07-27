
import json
import urllib.request
import urllib.error

GW = "http://google-workspace.local.mock:8080"
M365 = "http://microsoft-365.local.mock:8080/v1.0"
SNOW = "http://servicenow.local.mock:8080"
SLACK = "http://slack-admin.local.mock:8080/api"
ZOOM = "http://zoom-admin.local.mock:8080"

DOMAIN = "halcyondynamics.com"
LEGACY = "meridian-legacy.io"

def _e(local):
    return f"{local}@{DOMAIN}"

CAL = _e("j.calloway")
NAD = _e("p.nadkarni")
ILE = _e("m.ilesanmi")
WLI = _e("w.li")
BEL = _e("r.beltran")
VUK = _e("t.vukovic")
FIS = _e("e.fischer")
BEL_ZOOM = f"r.beltran@{LEGACY}"
VUK_SLACK = f"t.vukovic@{LEGACY}"
OKO_GW = f"n.okonkwo@{LEGACY}"

HDRS = {"Accept": "application/json", "x-taskgen-verifier": "1"}

def _get(url):
    req = urllib.request.Request(url, headers=HDRS, method="GET")
    with urllib.request.urlopen(req) as r:
        raw = r.read().decode()
        return json.loads(raw) if raw.strip() else {}

def m365_users():
    out, u = [], f"{M365}/users?$top=200"
    while True:
        b = _get(u)
        out.extend(b.get("value", []) or [])
        u = b.get("@odata.nextLink")
        if not u:
            return out

def m365_skus():
    out, u = [], f"{M365}/subscribedSkus?$top=200"
    while True:
        b = _get(u)
        out.extend(b.get("value", []) or [])
        u = b.get("@odata.nextLink")
        if not u:
            return out

def gw_users():
    out, tok = [], None
    while True:
        u = f"{GW}/admin/directory/v1/users?maxResults=500"
        if tok:
            u += f"&pageToken={tok}"
        b = _get(u)
        out.extend(b.get("users", []) or [])
        tok = b.get("nextPageToken")
        if not tok:
            return out

def gw_assignments():
    out, tok = [], None
    while True:
        u = f"{GW}/apps/licensing/v1/product/Google-Apps/users?maxResults=500"
        if tok:
            u += f"&pageToken={tok}"
        b = _get(u)
        out.extend(b.get("items", []) or [])
        tok = b.get("nextPageToken")
        if not tok:
            return out

def zoom_users():
    out, page = [], 1
    while True:
        b = _get(f"{ZOOM}/users?page_size=300&page_number={page}")
        rows = b.get("users", []) or []
        out.extend(rows)
        if len(rows) < 300:
            return out
        page += 1

def slack_users():
    out, cur = [], ""
    while True:
        u = f"{SLACK}/admin.users.list?limit=200"
        if cur:
            u += f"&cursor={cur}"
        b = _get(u)
        out.extend(b.get("users", []) or [])
        cur = (b.get("response_metadata") or {}).get("next_cursor") or ""
        if not cur:
            return out

def snow_users():
    out, offset = [], 0
    while True:
        b = _get(f"{SNOW}/api/now/table/sys_user?sysparm_limit=200&sysparm_offset={offset}")
        rows = b.get("result", []) or []
        out.extend(rows)
        if len(rows) < 200:
            return out
        offset += 200

def _divested_aliases():
    out = set()
    for u in snow_users():
        if u.get("department") == "Meridian" and str(u.get("active")).lower() == "false":
            for k in ("email", "user_name", "u_legacy_email"):
                v = str(u.get(k) or "").lower()
                if v:
                    out.add(v)
    return out

def _sku_id(part):
    for s in m365_skus():
        if s.get("skuPartNumber") == part:
            return s.get("skuId")
    raise AssertionError(f"SKU {part} not found")

def _m365_by_upn():
    return {str(u.get("userPrincipalName", "")).lower(): u for u in m365_users()}

def _holds(user, sku_id):
    return any(l.get("skuId") == sku_id for l in (user.get("assignedLicenses") or []))

def _gone():
    g = set()
    for u in m365_users():
        if u.get("accountEnabled") is False:
            g.add(str(u.get("userPrincipalName", "")).lower())
    for u in gw_users():
        if u.get("suspended") is True:
            g.add(str(u.get("primaryEmail", "")).lower())
    return g

def _gw_assignment_users():
    return {str(a.get("userId", "")).lower() for a in gw_assignments()}

def _zoom_by_email():
    return {str(u.get("email", "")).lower(): u for u in zoom_users()}

def _slack_billable_emails():
    out = set()
    for u in slack_users():
        if u.get("deleted"):
            continue
        if u.get("is_restricted") or u.get("is_ultra_restricted"):
            continue
        out.add(str(u.get("email", "")).lower())
    return out

def test_break_d1_nadkarni_e5_removed():
    u = _m365_by_upn().get(NAD)
    assert u is None or not _holds(u, _sku_id("SPE_E5")), "nadkarni still holds SPE_E5"

def test_break_d1_nadkarni_pbi_addon_removed():
    u = _m365_by_upn().get(NAD)
    assert u is None or not _holds(u, _sku_id("POWER_BI_PRO")), "nadkarni still holds POWER_BI_PRO add-on"

def test_break_d1_nadkarni_fully_unlicensed():
    u = _m365_by_upn().get(NAD)
    assert u is None or not (u.get("assignedLicenses") or []), "nadkarni still holds a license"

def test_break_no_disabled_m365_user_licensed():
    leaks = [str(u.get("userPrincipalName", "")).lower() for u in m365_users()
             if u.get("accountEnabled") is False and (u.get("assignedLicenses") or [])]
    assert leaks == [], f"disabled M365 users still licensed: {leaks}"

def test_break_no_suspended_gw_user_licensed():
    susp = {str(u.get("primaryEmail", "")).lower() for u in gw_users() if u.get("suspended") is True}
    leaks = sorted(susp & _gw_assignment_users())
    assert leaks == [], f"suspended GW users still licensed: {leaks}"

def test_break_no_divested_gw_licensed():
    div = _divested_aliases()
    leaks = sorted(str(a.get("userId", "")).lower() for a in gw_assignments()
                   if str(a.get("userId", "")).lower() in div)
    assert leaks == [], f"divested GW seats still licensed: {leaks}"

def test_break_no_divested_zoom_licensed():
    div = _divested_aliases()
    leaks = sorted(str(u.get("email", "")).lower() for u in zoom_users()
                   if u.get("type") == 2 and str(u.get("email", "")).lower() in div)
    assert leaks == [], f"divested Zoom users still Licensed: {leaks}"

def test_break_no_divested_slack_billable():
    div = _divested_aliases()
    leaks = sorted(e for e in _slack_billable_emails() if e in div)
    assert leaks == [], f"divested Slack users still billable: {leaks}"

def test_break_d2_ilesanmi_gw_license_removed():
    assert ILE not in _gw_assignment_users(), "ilesanmi GW license assignment still present"

def test_break_d3_wli_gw_license_removed():
    assert WLI not in _gw_assignment_users(), "w.li GW license assignment still present"

def test_break_d7_okonkwo_gw_legacy_removed():
    assert OKO_GW not in _gw_assignment_users(), "okonkwo legacy GW license assignment still present"

def test_break_d4_beltran_zoom_reclaimed():
    u = _zoom_by_email().get(BEL_ZOOM)
    ok = u is None or u.get("type") in (1, 4)
    assert ok, f"beltran Zoom seat not reclaimed (still Licensed): {u}"

def test_break_d5_vukovic_slack_reclaimed():
    assert VUK_SLACK not in _slack_billable_emails(), "vukovic still consumes a billable Slack seat"

def test_guard_calloway_m365_enabled():
    u = _m365_by_upn().get(CAL)
    assert u is not None and u.get("accountEnabled") is True, "calloway M365 account was disabled"

def test_guard_calloway_holds_e3():
    u = _m365_by_upn().get(CAL)
    assert u is not None and _holds(u, _sku_id("SPE_E3")), "calloway lost SPE_E3"

def test_guard_calloway_zoom_licensed():
    u = _zoom_by_email().get(CAL)
    assert u is not None and u.get("type") == 2, "calloway Zoom seat was downgraded/removed"

def test_guard_calloway_slack_billable():
    assert CAL in _slack_billable_emails(), "calloway Slack seat was removed"

def test_guard_fischer_m365_untouched():
    u = _m365_by_upn().get(FIS)
    assert u is not None and u.get("accountEnabled") is False and not (u.get("assignedLicenses") or []), \
        "fischer M365 state was altered"

def test_guard_fischer_zoom_basic():
    u = _zoom_by_email().get(FIS)
    assert u is not None and u.get("type") == 1, "fischer Zoom state was altered"

def test_guard_fischer_not_slack_billable():
    assert FIS not in _slack_billable_emails(), "fischer was (re)added as a billable Slack seat"

def test_guard_active_legacy_zoom_seats_preserved():
    div = _divested_aliases()
    kept = [u for u in zoom_users()
            if str(u.get("email", "")).lower().endswith("@" + LEGACY)
            and str(u.get("email", "")).lower() not in div]
    assert kept, "expected active-legacy Zoom decoys to exist"
    downgraded = sorted(str(u.get("email", "")).lower() for u in kept if u.get("type") != 2)
    assert downgraded == [], f"active-legacy Zoom seats wrongly reclaimed: {downgraded}"

def test_guard_active_legacy_slack_seats_preserved():
    div = _divested_aliases()
    billable = _slack_billable_emails()
    kept = [e for e in billable if e.endswith("@" + LEGACY) and e not in div]
    assert kept, "expected active-legacy Slack decoys to remain billable"

EXPECTED_DIVESTED_USERNAMES = {
    "e.fischer@halcyondynamics.com",
    "m.ilesanmi@halcyondynamics.com",
    "n.okonkwo@halcyondynamics.com",
    "p.nadkarni@halcyondynamics.com",
    "r.beltran@halcyondynamics.com",
    "t.vukovic@halcyondynamics.com",
    "w.li@halcyondynamics.com",
}
RETAINED_USERNAME = "j.calloway@halcyondynamics.com"

def _snow_by_username():
    return {str(u.get("user_name", "")).lower(): u for u in snow_users()}

def test_guard_snow_retained_employee_untouched():
    u = _snow_by_username().get(RETAINED_USERNAME)
    assert u is not None, "retained employee row is missing from ServiceNow"
    assert str(u.get("active")).lower() == "true", \
        "retained employee was marked inactive in the system of record"
    assert str(u.get("department")) == "Meridian", \
        "retained employee's department was edited in the system of record"

def test_guard_snow_divested_cast_stable():
    div = {str(u.get("user_name", "")).lower() for u in snow_users()
           if u.get("department") == "Meridian" and str(u.get("active")).lower() == "false"}
    assert div == EXPECTED_DIVESTED_USERNAMES, (
        "the divested cast in ServiceNow was edited: "
        f"unexpected={sorted(div - EXPECTED_DIVESTED_USERNAMES)} "
        f"missing={sorted(EXPECTED_DIVESTED_USERNAMES - div)}"
    )
