import json
import urllib.request
import urllib.parse

SF = "http://salesforce.local.mock:8080/services/data/v67.0"
HS = "http://hubspot.local.mock:8080"
PD = "http://pagerduty.local.mock:8080"
SN = "http://servicenow.local.mock:8080/api/now/table"
FD = "http://freshdesk.local.mock:8080/api/v2"
SL = "http://slack.local.mock:8080/api"

SF_MARCUS = "005MARCUSFELD00001"
SF_NADIA = "005NADIAKHAN000001"
SF_TOMASINT = "005TOMASINTEG0001"
SF_DEPARTED = {SF_MARCUS, SF_NADIA, SF_TOMASINT}
ACCT_MARCUS_A = "001ACCTNORTHRIDG1"
OPP_MARCUS = "006OPPRENEWALFY26"
OPP_TOMAS = "006OPPINTEGROLLOUT"
CASE_NADIA = "500CASEESCAL00001"

HS_DEAL_MARCUS = "4000000001"
HS_OWNER_MARCUS = "hs-owner-marcus"

PD_PRIYA, PD_DIEGO, PD_AISHA, PD_OWEN = "PPRIYA1", "PDIEGO1", "PAISHA1", "POWEN01"
PD_ACTIVE = {"PRAVI01", "PLENA01", "PMAYA01"}
EP_PAYMENTS, EP_INFRA, EP_CORP, EP_SUPPORT = "PEPPAY1", "PEPINF1", "PEPCOR1", "PEPSUP1"
SCH_PAYMENTS = "PSCPAY1"
TEAM_PAYMENTS, TEAM_INFRA = "PTMPAY1", "PTMINF1"

SN_PRIYA = "sn0000000000000000000000priya001"
SN_NADIA = "sn0000000000000000000000nadia001"
SN_AISHA = "sn0000000000000000000000aisha001"
SN_DIEGO = "sn0000000000000000000000diego001"
SN_SVC_PAY = "sn000000000000000000svcpayprobe1"
SN_JOB_CMDB = "snjob0000000000000000nightlycmdb01"
SN_JOB_LEDGER = "snjob0000000000paymentsledgerrec1"
SN_OAUTH_PRIYA = "snoauth00000paymentsexportapi001"

FD_AGENT_NADIA = 5001
FD_AGENT_OWEN = 5002

SL_MARCUS, SL_PRIYA, SL_NADIA, SL_AISHA, SL_TOMAS = "UMARCUS01", "UPRIYA001", "UNADIA001", "UAISHA001", "UGUESTTOM1"

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode()
    return json.loads(raw) if raw else None

def _get_or_none(url):
    try:
        return _get(url)
    except Exception:
        return None

def _sf_obj(sobject, rid):
    return _get_or_none(f"{SF}/sobjects/{sobject}/{rid}")

def _sf_user_active(uid):
    u = _sf_obj("User", uid)
    return bool(u and u.get("IsActive") is True)

def _owner_reassigned(sobject, rid):
    rec = _sf_obj(sobject, rid)
    if not rec:
        return False
    owner = rec.get("OwnerId")
    if owner in SF_DEPARTED or not owner:
        return False
    return _sf_user_active(owner)

def _ep_targets(ep_id):
    doc = _get_or_none(f"{PD}/escalation_policies/{ep_id}") or {}
    ep = doc.get("escalation_policy", {})
    ids = []
    for rule in ep.get("escalation_rules", []):
        for t in rule.get("targets", []):
            ids.append(str(t.get("id")))
    return ids

def _schedule_layer_user_ids(sch_id):
    doc = _get_or_none(f"{PD}/schedules/{sch_id}") or {}
    sch = doc.get("schedule", {})
    ids = []
    for layer in sch.get("schedule_layers", []):
        for entry in layer.get("users", []):
            ids.append(str((entry.get("user") or {}).get("id")))
    return ids

def _team_member_ids(team_id):
    doc = _get_or_none(f"{PD}/teams/{team_id}/members") or {}
    return [str((m.get("user") or {}).get("id")) for m in doc.get("members", [])]

def _override_user_ids(sch_id):
    q = urllib.parse.urlencode({"since": "2026-01-01T00:00:00Z", "until": "2027-01-01T00:00:00Z"})
    doc = _get_or_none(f"{PD}/schedules/{sch_id}/overrides?{q}") or {}
    return [str((o.get("user") or {}).get("id")) for o in doc.get("overrides", [])]

SN_LEAVER_USERNAMES = {"priya.raman", "nadia.khan", "aisha.bello"}
_HANDOVER_FIELDS = ("owned_by", "managed_by", "run_as", "assigned_to", "u_owner", "u_owned_by")

def _sn_table(table):
    doc = _get_or_none(f"{SN}/{table}") or {}
    return doc.get("result", []) if isinstance(doc, dict) else []

def _sn_inactive(sys_id):
    rec = next((r for r in _sn_table("sys_user") if str(r.get("sys_id")) == sys_id), None)
    if not rec:
        return False
    return rec.get("active") in (False, "false", "0", 0)

def _is_inactive_row(rec):
    return rec.get("active") in (False, "false", "0", 0)

def _handed_to_active_owner(rec, users):
    by_key = {}
    for u in users:
        if u.get("active") in (True, "true", "1", 1) and str(u.get("user_name")) not in SN_LEAVER_USERNAMES:
            for k in (u.get("sys_id"), u.get("user_name"), u.get("email")):
                if k:
                    by_key[str(k).strip().lower()] = u
    for field in _HANDOVER_FIELDS:
        value = rec.get(field)
        if not value:
            continue
        key = str(value).strip().lower()
        if key == "admin" or key in by_key:
            return True
    return False

def _automation_neutralized(rec, users):
    return rec is None or _is_inactive_row(rec) or _handed_to_active_owner(rec, users)

def _sn_has_admin_role(user_sys_id):
    return any(str(r.get("user")) == user_sys_id and str(r.get("role")) == "admin"
               for r in _sn_table("sys_user_has_role"))

def _fd_agent_ids():
    doc = _get_or_none(f"{FD}/agents") or []
    rows = doc if isinstance(doc, list) else doc.get("result", [])
    return {int(a.get("id")) for a in rows if a.get("id") is not None}

def _slack_deleted(uid):
    doc = _get_or_none(f"{SL}/users.info?user={uid}") or {}
    user = doc.get("user") or {}
    return user.get("deleted") is True

def test_marcus_sf_user_inactive():
    assert _sf_user_active(SF_MARCUS) is False

def test_marcus_account_reassigned():
    assert _owner_reassigned("Account", ACCT_MARCUS_A)

def test_marcus_opp_reassigned():
    assert _owner_reassigned("Opportunity", OPP_MARCUS)

def test_nadia_sf_user_inactive():
    assert _sf_user_active(SF_NADIA) is False

def test_nadia_case_reassigned():
    assert _owner_reassigned("Case", CASE_NADIA)

def test_tomas_integration_user_inactive():
    assert _sf_user_active(SF_TOMASINT) is False

def test_tomas_opp_reassigned():
    assert _owner_reassigned("Opportunity", OPP_TOMAS)

def test_marcus_hubspot_deal_reassigned():
    deal = _get_or_none(f"{HS}/crm/v3/objects/0-3/{HS_DEAL_MARCUS}") or {}
    owner = (deal.get("properties") or {}).get("hubspot_owner_id")
    assert owner not in (HS_OWNER_MARCUS, None, "")

def test_priya_payments_ep_reassigned():
    targets = _ep_targets(EP_PAYMENTS)
    assert PD_PRIYA not in targets and any(t in PD_ACTIVE for t in targets)

def test_priya_payments_schedule_replaced():
    users = _schedule_layer_user_ids(SCH_PAYMENTS)
    assert PD_PRIYA not in users and len(users) > 0

def test_priya_removed_from_payments_team():
    assert PD_PRIYA not in _team_member_ids(TEAM_PAYMENTS)

def test_priya_override_removed():
    assert PD_PRIYA not in _override_user_ids(SCH_PAYMENTS)

def test_diego_removed_from_infra_ep():
    targets = _ep_targets(EP_INFRA)
    assert PD_DIEGO not in targets and any(t in PD_ACTIVE for t in targets)

def test_diego_removed_from_infra_team():
    assert PD_DIEGO not in _team_member_ids(TEAM_INFRA)

def test_aisha_removed_from_corp_ep():
    targets = _ep_targets(EP_CORP)
    assert PD_AISHA not in targets and any(t in PD_ACTIVE for t in targets)

def test_owen_removed_from_support_ep():
    targets = _ep_targets(EP_SUPPORT)
    assert PD_OWEN not in targets and any(t in PD_ACTIVE for t in targets)

def test_priya_sn_user_inactive():
    assert _sn_inactive(SN_PRIYA)

def test_nadia_sn_user_inactive():
    assert _sn_inactive(SN_NADIA)

def test_aisha_sn_user_inactive():
    assert _sn_inactive(SN_AISHA)

def test_aisha_sn_admin_role_removed():
    assert not _sn_has_admin_role(SN_AISHA)

def test_leaver_automation_neutralized():
    users = _sn_table("sys_user")
    jobs = _sn_table("sysauto_script")
    oauth = _sn_table("oauth_entity")
    svc = next((r for r in users if str(r.get("sys_id")) == SN_SVC_PAY), None)
    job_cmdb = next((j for j in jobs if str(j.get("sys_id")) == SN_JOB_CMDB), None)
    job_ledger = next((j for j in jobs if str(j.get("sys_id")) == SN_JOB_LEDGER), None)
    api_cred = next((o for o in oauth if str(o.get("sys_id")) == SN_OAUTH_PRIYA), None)
    assert (_automation_neutralized(svc, users)
            and _automation_neutralized(job_cmdb, users)
            and _automation_neutralized(job_ledger, users)
            and _automation_neutralized(api_cred, users))

def test_diego_sn_admin_role_removed():
    assert not _sn_has_admin_role(SN_DIEGO)

def test_nadia_freshdesk_agent_deleted():
    assert FD_AGENT_NADIA not in _fd_agent_ids()

def test_owen_freshdesk_agent_deleted():
    assert FD_AGENT_OWEN not in _fd_agent_ids()

def test_marcus_slack_deactivated():
    assert _slack_deleted(SL_MARCUS)

def test_priya_slack_deactivated():
    assert _slack_deleted(SL_PRIYA)

def test_nadia_slack_deactivated():
    assert _slack_deleted(SL_NADIA)

def test_aisha_slack_deactivated():
    assert _slack_deleted(SL_AISHA)

def test_tomas_slack_guest_deactivated():
    assert _slack_deleted(SL_TOMAS)
