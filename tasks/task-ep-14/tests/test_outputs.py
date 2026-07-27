
import json
import urllib.request
import urllib.error

SN = "http://servicenow.local.mock:8080"
D42 = "http://device42.local.mock:8080"
SLACK = "http://slack.local.mock:8080"
PD = "http://pagerduty.local.mock:8080"
JSM = "http://jira-service-management.local.mock:8080"
SNIPE = "http://snipeit.local.mock:8080/api/v1"

BASELINE_SERVERS = {
    "ledger-worker-old", "ledger-api-01", "ledger-api-02", "payments-01",
    "payments-02", "billing-01", "search-01", "auth-01", "warehouse-01",
}
SHADOW_SERVER = "ledger-cache-02"

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode() or "{}")

def norm(s):
    return "".join(c for c in str(s or "").lower() if c.isalnum())

def sn_list(table):
    out, off = [], 0
    while True:
        page = _get(f"{SN}/api/now/table/{table}?sysparm_limit=100&sysparm_offset={off}").get("result", [])
        out.extend(page)
        if len(page) < 100:
            return out
        off += 100

def d42_list(res, key):
    out, off = [], 0
    while True:
        j = _get(f"{D42}/api/2.0/{res}/?limit=1000&offset={off}")
        page = j.get(key, [])
        out.extend(page)
        if len(page) < 1000 or off + len(page) >= j.get("total_count", len(out)):
            return out
        off += 1000

def pd_incidents():
    out, off = [], 0
    while True:
        j = _get(f"{PD}/incidents?limit=100&offset={off}")
        page = j.get("incidents", [])
        out.extend(page)
        if not j.get("more") or len(page) < 100:
            return out
        off += 100

def snipe_hardware():
    out, off = [], 0
    while True:
        j = _get(f"{SNIPE}/hardware?limit=500&offset={off}")
        page = j.get("rows", [])
        out.extend(page)
        if len(page) < 500 or off + len(page) >= j.get("total", len(out)):
            return out
        off += 500

def pd_services():
    return _get(f"{PD}/services?limit=100").get("services", [])

def pd_escalation_policies():
    return _get(f"{PD}/escalation_policies?limit=100").get("escalation_policies", [])

def _team0(refs):
    refs = refs or []
    return refs[0].get("id") if refs else None

def payments_incident():
    incs = [i for i in pd_incidents()
            if norm((i.get("service") or {}).get("summary")) == norm("Payments API")]
    return next((i for i in incs if "error" in norm(i.get("title")) or "ratelimiter" in norm(i.get("title"))),
                incs[0] if incs else None)

def change_by_desc(sub):
    return next(c for c in sn_list("change_request")
               if sub.lower() in str(c.get("short_description", "")).lower())

def ci_by_name(table, name):
    return next(c for c in sn_list(table) if norm(c.get("name")) == norm(name))

NON_INSTALLED = lambda v: norm(v) not in ("1", "installed", "operational")
CLOSED = lambda v: str(v) in ("3", "7")

def test_a_cmdb_ledger_api_version_updated():
    ci = ci_by_name("cmdb_ci_appl", "Ledger API")
    assert "2.4" in str(ci.get("version")), f"Ledger API CMDB version not reconciled: {ci.get('version')}"

def test_a_change_closed_successful():
    c = change_by_desc("Upgrade Ledger API to v2.4")
    assert CLOSED(c.get("state")) and norm(c.get("close_code")) == "successful", \
        f"Ledger upgrade change not closed successful: state={c.get('state')} close={c.get('close_code')}"

def test_b_stuck_approval_recorded():
    b = change_by_desc("Add failover replica to Ledger DB")
    appr = next(a for a in sn_list("sysapproval_approver") if a.get("sysapproval") == b["sys_id"])
    assert norm(appr.get("state")) == "approved", f"B approval not recorded: {appr.get('state')}"

def test_c_change_marked_unsuccessful():
    c = change_by_desc("Enable adaptive rate limiter on Payments API")
    assert norm(c.get("close_code")) in ("unsuccessful", "failed"), \
        f"failed change not marked unsuccessful: {c.get('close_code')}"

def test_c_pd_incident_handled():
    inc = payments_incident()
    assert inc is not None, "no PagerDuty incident on the Payments service"
    st = norm(inc.get("status"))
    if st in ("resolved", "acknowledged"):
        return
    eps = pd_escalation_policies()
    pay_ep_ids, pay_users = set(), set()
    for e in eps:
        is_pay = norm((_team_summary(e)) or "") == "payments" or "payments" in norm(e.get("summary"))
        if is_pay:
            pay_ep_ids.add(str(e.get("id")))
            for r in e.get("escalation_rules") or []:
                for t in r.get("targets") or []:
                    pay_users.add(str(t.get("id")))
    ep_id = str((inc.get("escalation_policy") or {}).get("id"))
    assignees = {str((a.get("assignee") or {}).get("id")) for a in (inc.get("assignments") or [])}
    assert ep_id in pay_ep_ids or (assignees & pay_users), \
        f"live Payments incident left unattended/mis-routed: status={inc.get('status')}"

def _team_summary(ep):
    teams = ep.get("teams") or []
    return teams[0].get("summary") if teams else None

def test_c_pd_service_routing_fixed():
    svcs = pd_services()
    pay = next(s for s in svcs if norm(s.get("name")) == norm("Payments API"))
    eps = {e.get("id"): e for e in pd_escalation_policies()}
    own = _team0(pay.get("teams"))
    ep = eps.get((pay.get("escalation_policy") or {}).get("id")) or {}
    ep_team = _team0(ep.get("teams"))
    assert own and ep_team and own == ep_team, \
        f"Payments service still routes to the wrong team (routes_to={ep_team}, owner={own})"

def test_d_cmdb_warehouse_version_updated():
    ci = ci_by_name("cmdb_ci_database", "Warehouse DB")
    assert "15" in str(ci.get("version")), f"Warehouse DB CMDB version not reconciled: {ci.get('version')}"

def test_e_shadow_ci_registered():
    servers = sn_list("cmdb_ci_server")
    match = [s for s in servers if norm(SHADOW_SERVER) in norm(s.get("name"))
             or norm(SHADOW_SERVER) in norm(s.get("fqdn"))]
    assert match, "shadow CI ledger-cache-02 was never registered in the CMDB"
    assert any(norm(s.get("u_environment")) == "production" for s in match), \
        "shadow CI registered but not marked production"

def test_g_cmdb_server_retired():
    s = ci_by_name("cmdb_ci_server", "ledger-worker-old")
    assert NON_INSTALLED(s.get("install_status")), \
        f"decommissioned server still Installed in CMDB: {s.get('install_status')}"

def test_g_snipe_asset_archived():
    a = next(h for h in snipe_hardware() if norm(h.get("serial")) == norm("SN-WORK-OLD"))
    label = a.get("status_label") or {}
    token = norm(label.get("status_type") or label.get("status_meta") or label.get("name"))
    assert "archiv" in token or str(label.get("id")) == "4", \
        f"decommissioned asset not archived in Snipe-IT: {label}"

def test_guard_false_premise_change_untouched():
    f = change_by_desc("Ledger API DB failover drill")
    assert norm(f.get("close_code")) not in ("unsuccessful", "failed"), \
        "the blamed (healthy) failover-drill change was wrongly marked as failed/culprit"

def test_guard_worked_example_change_untouched():
    ok = change_by_desc("Upgrade Billing API to v3.2")
    assert CLOSED(ok.get("state")) and norm(ok.get("close_code")) == "successful", \
        "the already-correct Billing change was altered away from closed-successful"

def test_guard_worked_example_ci_untouched():
    ci = ci_by_name("cmdb_ci_appl", "Billing API")
    assert str(ci.get("version")) == "3.2", f"Billing API CMDB wrongly changed: {ci.get('version')}"

def test_guard_hold_approval_not_approved():
    h = change_by_desc("Rotate Notifications API signing keys")
    appr = next(a for a in sn_list("sysapproval_approver") if a.get("sysapproval") == h["sys_id"])
    assert norm(appr.get("state")) != "approved", \
        "the on-hold approval (no Slack sign-off) was wrongly approved"

def test_guard_only_c_marked_unsuccessful():
    bad = {norm(c.get("short_description")) for c in sn_list("change_request")
           if norm(c.get("close_code")) in ("unsuccessful", "failed")}
    assert bad == {norm("Enable adaptive rate limiter on Payments API")}, \
        f"exactly one change should be unsuccessful; got {bad}"

def test_guard_cmdb_server_set_exact():
    names = {norm(s.get("name")) for s in sn_list("cmdb_ci_server")}
    allowed = {norm(n) for n in BASELINE_SERVERS | {SHADOW_SERVER}}
    assert names == allowed, f"cmdb_ci_server set drifted: unexpected={names - allowed}, missing={allowed - names}"

def test_guard_device42_reality_untouched():
    svcs = {norm(s.get("displayname")): str(s.get("version")) for s in d42_list("services", "services")}
    assert svcs.get("ledgerapi") == "2.4", "Device42 reality (ledger-api) must not be edited"
    assert svcs.get("warehousedb") == "15", "Device42 reality (warehouse-db) must not be edited"
    devs = {norm(d.get("name")) for d in d42_list("devices", "devices")}
    assert norm("ledger-cache-02") in devs and norm("ledger-worker-old") in devs, \
        "Device42 devices must not be deleted"

def test_guard_staging_drift_not_reconciled():
    ci = ci_by_name("cmdb_ci_appl", "Ledger API (staging)")
    assert str(ci.get("version")) == "2.2", \
        f"staging drift was wrongly 'fixed' (out of scope): {ci.get('version')}"

def test_guard_noise_prod_ci_untouched():
    ci = ci_by_name("cmdb_ci_appl", "Search API")
    assert str(ci.get("version")) == "9.1", f"a consistent noise CI was altered: {ci.get('version')}"

def test_guard_snipe_archived_set_exact():
    archived = set()
    for h in snipe_hardware():
        label = h.get("status_label") or {}
        token = norm(label.get("status_type") or label.get("status_meta") or label.get("name"))
        if "archiv" in token or str(label.get("id")) == "4":
            archived.add(norm(h.get("serial")))
    assert archived == {norm("SN-WORK-OLD"), norm("SN-RET-01")}, \
        f"exactly the decommissioned + baseline assets should be archived; got {archived}"

def test_guard_pagerduty_incident_count_stable():
    incs = pd_incidents()
    assert len(incs) == 4, f"PagerDuty incident count changed (spurious create/delete): {len(incs)}"

def test_guard_pd_routing_others_untouched():
    svcs = pd_services()
    eps = {e.get("id"): e for e in pd_escalation_policies()}
    for s in svcs:
        if norm(s.get("name")) == norm("Payments API"):
            continue
        own = _team0(s.get("teams"))
        ep = eps.get((s.get("escalation_policy") or {}).get("id")) or {}
        assert own and _team0(ep.get("teams")) == own, \
            f"non-Payments service {s.get('name')} routing was altered (over-action)"

def test_guard_jsm_evidence_untouched():
    reqs = _get(f"{JSM}/rest/servicedeskapi/request?limit=50").get("values", [])
    assert any(r.get("issueKey") == "DP-1042" for r in reqs), "JSM DP-1042 evidence must remain intact"

def test_guard_trigger_incident_present():
    inc = next(i for i in sn_list("incident") if i.get("number") == "INC0007001")
    assert inc, "trigger incident must not be deleted"
