import json
import urllib.request
import urllib.error

ENTRA = "http://entra-id.local.mock:8080/v1.0"
M365 = "http://microsoft-365.local.mock:8080/v1.0"
INTUNE = "http://microsoft-intune.local.mock:8080/v1.0"
DEFENDER = "http://microsoft-defender.local.mock:8080/v1.0"
TEAMS = "http://microsoft-teams.local.mock:8080/v1.0"
SP = "http://sharepoint.local.mock:8080/v1.0"
SN = "http://servicenow.local.mock:8080"

NADIA = "u-nadia-osei"
PRIYA = "u-priya-rao"
PRIYA_GUEST = "u-priya-rao-guest"
DIEGO = "u-diego-marchetti"
SANA_GUEST = "u-sana-rahman-guest"
THEO = "u-theo-vance"
MARCUS = "u-marcus-webb"
DEPARTED = {NADIA, PRIYA, PRIYA_GUEST, DIEGO, SANA_GUEST, THEO, MARCUS}
DEPARTED_UPNS = {
    "nadia.osei@contoso.example", "priya.rao@contoso.example",
    "priya.rao_sentinelworks.example#EXT#@contoso.onmicrosoft.com",
    "diego.marchetti@contoso.example",
    "sana.rahman_northwind.example#EXT#@contoso.onmicrosoft.com",
    "theo.vance@contoso.example", "marcus.webb@contoso.example",
}
TICKET_SYS_ID = "866ac3e61176827d2f42103270b6af9c"

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
        for k in keys + ("value", "values", "result"):
            if k in obj and isinstance(obj[k], list):
                return obj[k]
    return []

def _disabled(base, uid):
    u = _get(base + "/users/" + uid)
    return u is not None and u.get("accountEnabled") is False

def _entra_group_ids(gid):
    return {str(m.get("id")) for m in _as_list(_get(ENTRA + "/groups/%s/members" % gid))}

def _role_member_ids(rid):
    return {str(m.get("id")) for m in _as_list(_get(M365 + "/directoryRoles/%s/members" % rid))}

def _app_owner_ids(aid):
    return {str(o.get("id")) for o in _as_list(_get(M365 + "/applications/%s/owners" % aid))}

def _user_enabled(uid):
    u = _get(M365 + "/users/" + uid) or _get(ENTRA + "/users/" + uid)
    return bool(u) and u.get("accountEnabled") is True

def _app_handed_over(aid):
    owners = _app_owner_ids(aid)
    return not (owners & DEPARTED) and any(o not in DEPARTED and _user_enabled(o) for o in owners)

def _device_offboarded(dev_id):
    d = _get(INTUNE + "/deviceManagement/managedDevices/" + dev_id)
    if d is None:
        return True
    return str(d.get("managementState")) in ("retirePending", "wipePending")

def _incident_assigned_to(inc_id):
    inc = _get(DEFENDER + "/security/incidents/" + inc_id)
    return str((inc or {}).get("assignedTo") or "")

def _team_member_ids(tid):
    return {str(m.get("userId")) for m in _as_list(_get(TEAMS + "/teams/%s/members" % tid))}

def _grant_targets_user(perm, uid):
    def _scan(node):
        return str((node or {}).get("user", {}).get("id")) == uid
    if _scan(perm.get("grantedToV2")) or _scan(perm.get("grantedTo")):
        return True
    for ident in _as_list(perm.get("grantedToIdentitiesV2")) + _as_list(perm.get("grantedToIdentities")):
        if _scan(ident):
            return True
    return False

def _site_has(uid, site):
    return any(_grant_targets_user(p, uid) for p in _as_list(_get(SP + "/sites/%s/permissions" % site)))

def test_nadia_disabled():
    assert _disabled(ENTRA, NADIA)

def test_nadia_removed_from_soc_analysts():
    assert NADIA not in _entra_group_ids("g-soc-analysts")

def test_nadia_removed_from_breakglass():
    assert NADIA not in _entra_group_ids("g-breakglass")

def test_nadia_removed_from_security_reader_role():
    assert NADIA not in _role_member_ids("role-secreader")

def test_nadia_device_offboarded():
    assert _device_offboarded("dev-nadia")

def test_nadia_removed_from_soc_team():
    assert NADIA not in _team_member_ids("team-soc")

def test_priya_member_disabled():
    assert _disabled(ENTRA, PRIYA)

def test_priya_removed_from_detection_eng():
    assert PRIYA not in _entra_group_ids("g-detection-eng")

def test_priya_guest_disabled():
    assert _disabled(ENTRA, PRIYA_GUEST)

def test_priya_guest_removed_from_external_vendors():
    assert PRIYA_GUEST not in _entra_group_ids("g-external-vendors")

def test_priya_guest_sharepoint_comms_removed():
    assert not _site_has(PRIYA_GUEST, "site-comms")

def test_diego_disabled():
    assert _disabled(ENTRA, DIEGO)

def test_diego_removed_from_detection_eng():
    assert DIEGO not in _entra_group_ids("g-detection-eng")

def test_diego_device_offboarded():
    assert _device_offboarded("dev-diego")

def test_diego_phone_offboarded():
    assert _device_offboarded("dev-diego-phone")

def test_diego_incident_reassigned():
    owner = _incident_assigned_to("inc-201")
    assert owner != "" and owner not in DEPARTED_UPNS

def test_diego_app_ownership_handed_over():
    assert _app_handed_over("app-hunt")

def test_sana_guest_disabled():
    assert _disabled(ENTRA, SANA_GUEST)

def test_sana_guest_removed_from_external_vendors():
    assert SANA_GUEST not in _entra_group_ids("g-external-vendors")

def test_sana_guest_sharepoint_legal_removed():
    assert not _site_has(SANA_GUEST, "site-legal")

def test_theo_disabled():
    assert _disabled(ENTRA, THEO)

def test_theo_removed_from_vuln_mgmt():
    assert THEO not in _entra_group_ids("g-vuln-mgmt")

def test_theo_removed_from_security_reader_role():
    assert THEO not in _role_member_ids("role-secreader")

def test_theo_sharepoint_finance_removed():
    assert not _site_has(THEO, "site-finance")

def test_theo_laptop_offboarded():
    assert _device_offboarded("dev-theo-lap")

def test_theo_phone_offboarded():
    assert _device_offboarded("dev-theo-phone")

def test_marcus_disabled():
    assert _disabled(ENTRA, MARCUS)

def test_marcus_removed_from_breakglass():
    assert MARCUS not in _entra_group_ids("g-breakglass")

def test_marcus_removed_from_security_admin_role():
    assert MARCUS not in _role_member_ids("role-secadmin")

def test_marcus_removed_from_soc_team():
    assert MARCUS not in _team_member_ids("team-soc")

def test_marcus_app_ownership_handed_over():
    assert _app_handed_over("app-ir")

def test_ticket_closed():
    r = _get(SN + "/api/now/table/incident/" + TICKET_SYS_ID)
    state = str(((r or {}).get("result") or {}).get("state") or "")
    assert state in ("6", "7")
