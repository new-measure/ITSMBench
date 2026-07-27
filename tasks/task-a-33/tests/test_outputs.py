import json, urllib.request, urllib.error

ENTRA = "http://entra-id.local.mock:8080/v1.0"
SP = "http://sharepoint.local.mock:8080/v1.0"
OD = "http://onedrive.local.mock:8080/v1.0"
M365 = "http://microsoft-365.local.mock:8080/v1.0"
GH = "http://github.local.mock:8080"
JSM = "http://jira-service-management.local.mock:8080/rest/servicedeskapi"

PRIYA = "u-priya-anand"
PRIYA_GUEST = "u-priya-anand-guest"
DIEGO = "u-diego-marchetti"
SANA_GUEST = "u-sana-rahman-guest"
THEO = "u-theo-vance"
ELENA = "u-elena-novak"
VIKTOR = "u-viktor-sorensen"
DEPARTED = {PRIYA, PRIYA_GUEST, DIEGO, SANA_GUEST, THEO, ELENA, VIKTOR}
REQUEST = "HELP-3301"

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

def _user(uid):
    return _get(ENTRA + "/users/" + uid)

def _group_member_ids(gid):
    return {str(m.get("id")) for m in _as_list(_get(ENTRA + "/groups/%s/members" % gid))}

def _grant_targets_user(perm, uid):
    def _scan(node):
        return str((node or {}).get("user", {}).get("id")) == uid
    if _scan(perm.get("grantedToV2")) or _scan(perm.get("grantedTo")):
        return True
    for ident in _as_list(perm.get("grantedToIdentitiesV2")) + _as_list(perm.get("grantedToIdentities")):
        if _scan(ident):
            return True
    return False

def _site_perms(site):
    return _as_list(_get(SP + "/sites/%s/permissions" % site))

def _item_perms(drive, item):
    return _as_list(_get(OD + "/drives/%s/items/%s/permissions" % (drive, item)))

def _disabled(uid):
    u = _user(uid)
    return u is None or u.get("accountEnabled") is False

def _apps_owned_by(uid):
    return [a for a in _as_list(_get(M365 + "/applications")) if uid in [str(o) for o in _as_list(a.get("owners"))]]

def _sps_owned_by(uid):
    return [s for s in _as_list(_get(M365 + "/servicePrincipals")) if uid in [str(o) for o in _as_list(s.get("owners"))]]

def _repo_deploy_keys(owner, repo):
    return _as_list(_get(GH + "/repos/%s/%s/keys" % (owner, repo)), "keys")

def _owner_ids(rec):
    return [str(o) for o in _as_list((rec or {}).get("owners"))]

def _artifact_neutralized(rec):
    if rec is None:
        return True
    if rec.get("accountEnabled") is False:
        return True
    if not _as_list(rec.get("passwordCredentials")) and not _as_list(rec.get("keyCredentials")):
        return True
    owners = _owner_ids(rec)
    return bool(owners) and not any(o in DEPARTED for o in owners)

def _by_id(items, rid):
    return next((x for x in items if str(x.get("id")) == rid), None)

def test_priya_member_disabled():
    assert _disabled(PRIYA)

def test_priya_removed_from_helios_group():
    assert PRIYA not in _group_member_ids("g-helios")

def test_priya_removed_from_records_group():
    assert PRIYA not in _group_member_ids("g-records")

def test_priya_sharepoint_finance_removed():
    assert not any(_grant_targets_user(p, PRIYA) for p in _site_perms("site-finance"))

def test_priya_sharepoint_exec_removed():
    assert not any(_grant_targets_user(p, PRIYA) for p in _site_perms("site-exec"))

def test_priya_sharepoint_portfolio_removed():
    assert not any(_grant_targets_user(p, PRIYA) for p in _site_perms("site-portfolio"))

def test_onedrive_departed_share_grants_removed():
    priya_gone = not any(_grant_targets_user(p, PRIYA) for p in _item_perms("drive-dana", "item-budget"))
    theo_gone = not any(_grant_targets_user(p, THEO) for p in _item_perms("drive-dana", "item-forecast"))
    assert priya_gone and theo_gone

def test_priya_guest_disabled():
    assert _disabled(PRIYA_GUEST)

def test_priya_guest_removed_from_external_group():
    assert PRIYA_GUEST not in _group_member_ids("g-external")

def test_priya_guest_sharepoint_comms_removed():
    assert not any(_grant_targets_user(p, PRIYA_GUEST) for p in _site_perms("site-comms"))

def test_diego_disabled():
    assert _disabled(DIEGO)

def test_diego_removed_from_helios_group():
    assert DIEGO not in _group_member_ids("g-helios")

def test_diego_sharepoint_research_removed():
    assert not any(_grant_targets_user(p, DIEGO) for p in _site_perms("site-research"))

def test_diego_sharepoint_helios_removed():
    assert not any(_grant_targets_user(p, DIEGO) for p in _site_perms("site-helios"))

def test_helios_site_retains_active_owner():
    owners = [p for p in _site_perms("site-helios") if "owner" in (p.get("roles") or [])]
    non_departed_owner = any(
        str((p.get("grantedToV2") or {}).get("user", {}).get("id")) not in DEPARTED
        and (p.get("grantedToV2") or {}).get("user", {}).get("id")
        for p in owners
    )
    assert non_departed_owner

def test_diego_github_deploy_key_removed():
    assert not any(str(k.get("id")) == "501" for k in _repo_deploy_keys("contoso", "helios-infra"))

def test_sana_guest_disabled():
    assert _disabled(SANA_GUEST)

def test_sana_guest_removed_from_external_group():
    assert SANA_GUEST not in _group_member_ids("g-external")

def test_sana_guest_sharepoint_legal_removed():
    assert not any(_grant_targets_user(p, SANA_GUEST) for p in _site_perms("site-legal"))

def test_theo_disabled():
    assert _disabled(THEO)

def test_theo_removed_from_design_group():
    assert THEO not in _group_member_ids("g-design")

def test_theo_sharepoint_design_removed():
    assert not any(_grant_targets_user(p, THEO) for p in _site_perms("site-design"))

def test_theo_sharepoint_ops_removed():
    assert not any(_grant_targets_user(p, THEO) for p in _site_perms("site-ops"))

def test_theo_github_deploy_key_removed():
    assert not any(str(k.get("id")) == "504" for k in _repo_deploy_keys("contoso", "data-platform"))

def test_elena_disabled():
    assert _disabled(ELENA)

def test_elena_removed_from_integrations_group():
    assert ELENA not in _group_member_ids("g-integrations")

def test_elena_sharepoint_portfolio_removed():
    assert not any(_grant_targets_user(p, ELENA) for p in _site_perms("site-portfolio"))

def test_elena_app_registration_neutralized():
    target = _by_id(_as_list(_get(M365 + "/applications")), "app-partner-sync")
    assert _apps_owned_by(ELENA) == [] and _artifact_neutralized(target)

def test_viktor_disabled():
    assert _disabled(VIKTOR)

def test_viktor_removed_from_integrations_group():
    assert VIKTOR not in _group_member_ids("g-integrations")

def test_viktor_sharepoint_eng_removed():
    assert not any(_grant_targets_user(p, VIKTOR) for p in _site_perms("site-eng"))

def test_eng_site_retains_active_owner():
    owners = [p for p in _site_perms("site-eng") if "owner" in (p.get("roles") or [])]
    non_departed_owner = any(
        str((p.get("grantedToV2") or {}).get("user", {}).get("id")) not in DEPARTED
        and (p.get("grantedToV2") or {}).get("user", {}).get("id")
        for p in owners
    )
    assert non_departed_owner

def test_viktor_service_principal_neutralized():
    target = _by_id(_as_list(_get(M365 + "/servicePrincipals")), "sp-export-bot")
    assert _sps_owned_by(VIKTOR) == [] and _artifact_neutralized(target)

def test_ticket_closed():
    r = _get(JSM + "/request/" + REQUEST)
    assert str((r or {}).get("currentStatus", {}).get("statusCategory")) == "COMPLETE"
