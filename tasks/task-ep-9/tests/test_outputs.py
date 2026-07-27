
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

PD = "http://pagerduty.local.mock:8080"
IO = "http://incidentio.local.mock:8080"
JIRA = "http://jira.local.mock:8080/rest/api/3"
CONF = "http://confluence.local.mock:8080/wiki/api/v2"
SLACK = "http://slack.local.mock:8080/api"
LOCAL_PORT = os.environ.get("MOCK_LOCAL_PORT")

NOW = "2026-07-14T09:00:00Z"

B36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

def h(key):
    return hashlib.md5(("ep9:" + key).encode()).hexdigest()

def b36(hexstr, n):
    v = int(hexstr, 16)
    out = ""
    while len(out) < n:
        out += B36[v % 36]
        v //= 36
    return out

def pdid(key):
    return "P" + b36(h("pd:" + key), 6)

def ioid(key):
    return "01" + b36(h("io:" + key), 24)

def slid(key, prefix):
    return prefix + b36(h("sl:" + key), 8)

def confid(key):
    return str(30000 + int(h("cf:" + key), 16) % 60000)

def email_of(name):
    e = name.lower().replace(" ", ".") + "@solsticecommerce.com"
    return re.sub(r"[^a-z.@]", "", e)

def pd_user_id(name):
    return pdid("user:" + email_of(name))

def slack_id(name):
    return slid("user:" + email_of(name), "U")

TEAMS = ["Payments", "Platform", "Search", "Data Platform", "Mobile",
         "Identity", "Infra", "Support Eng", "Growth", "Core Services"]
SERVICES = [
    ("checkout-api", "Payments"), ("checkout-db", "Payments"), ("payments-reconciler", "Payments"),
    ("platform-gateway", "Platform"), ("platform-queue", "Platform"), ("platform-scheduler", "Platform"),
    ("platform-object-store", "Platform"), ("search-frontend", "Search"), ("search-indexer", "Search"),
    ("search-index-db", "Search"), ("search-suggest", "Search"), ("dp-airflow", "Data Platform"),
    ("dp-warehouse", "Data Platform"), ("dp-streaming", "Data Platform"), ("dp-catalog", "Data Platform"),
    ("mobile-api", "Mobile"), ("mobile-push", "Mobile"), ("mobile-push-legacy", "Mobile"),
    ("mobile-config", "Mobile"), ("identity-idp", "Identity"), ("identity-tokens", "Identity"),
    ("identity-scim", "Identity"), ("infra-dns", "Infra"), ("infra-vault", "Infra"),
    ("infra-ci", "Infra"), ("infra-cdn", "Infra"), ("support-desk-api", "Support Eng"),
    ("support-webhooks", "Support Eng"), ("growth-emails", "Growth"), ("growth-referrals", "Growth"),
    ("growth-experiments", "Growth"), ("core-billing-ledger", "Core Services"),
    ("core-feature-flags", "Core Services"), ("core-notifications", "Core Services"),
]
SCHEDULE_NAMES = [f"{t} Primary" for t in TEAMS] + [
    "Payments Secondary", "Platform Secondary", "Infra Secondary",
    "Checkout Legacy Rotation", "EU Launch War Room",
]

SVC = {name: pdid("service:" + name) for name, _ in SERVICES}
EP = {t: pdid(f"ep:{t} Escalation") for t in TEAMS}
EP_LEGACY = pdid("ep:Checkout (legacy)")
SCHED = {n: pdid("schedule:" + n) for n in SCHEDULE_NAMES}
TRIGGER_INCIDENT = pdid("incident:trigger")
OPEN_NOISE_INCIDENTS = {pdid("incident:open-1"), pdid("incident:open-2"), pdid("incident:open-3")}
MW_DEBRIS = pdid("mw:debris")
MW_LEGIT = pdid("mw:legit")
UG = {t: slid("ug:" + t, "S") for t in TEAMS}
STORM_IO_INCIDENT = ioid("incident:storm")
STORM_FOLLOWUPS = {ioid("fu:" + k) for k in ("a", "b", "d", "e", "g")}
PM_PAGE_ID = confid("page:postmortem-june-failover")

ANAYA_SLACK = slack_id("Anaya Deshpande")
MARCUS_SLACK = slack_id("Marcus Webb")
MARCUS_PD = pd_user_id("Marcus Webb")
JONAS_SLACK = slack_id("Jonas Berg")
PAYMENTS_LEAD_PD = pd_user_id("Priya Nair")

def get(url):
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname
    target = url
    if LOCAL_PORT:
        target = urllib.parse.urlunsplit(
            (parsed.scheme, f"127.0.0.1:{LOCAL_PORT}", parsed.path, parsed.query, parsed.fragment)
        )
    req = urllib.request.Request(target, headers={"Host": f"{host}:8080"})
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw.strip() else None
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw) if raw.strip() else None
        except Exception:
            return e.code, None

def get_ok(url):
    status, payload = get(url)
    assert status == 200, f"GET {url} -> {status}"
    return payload

def pd_list(path, key, params=None):
    out, offset = [], 0
    while True:
        q = dict(params or {})
        q.update({"limit": 100, "offset": offset})
        payload = get_ok(f"{PD}{path}?{urllib.parse.urlencode(q, doseq=True)}")
        out.extend(payload[key])
        if not payload.get("more"):
            return out
        offset += len(payload[key])

def slack_get(method, params=None):
    qs = urllib.parse.urlencode(params or {}, doseq=True)
    payload = get_ok(f"{SLACK}/{method}?{qs}" if qs else f"{SLACK}/{method}")
    assert payload.get("ok") is True, f"slack {method} not ok: {payload}"
    return payload

def parse_ts(iso):
    return iso.replace("Z", "")

def test_b_checkout_api_routed_to_payments_policy():
    svc = get_ok(f"{PD}/services/{SVC['checkout-api']}")["service"]
    assert svc["escalation_policy"]["id"] == EP["Payments"], (
        f"checkout-api still pages {svc['escalation_policy']['id']}"
    )

def test_a_payments_policy_has_second_level():
    ep = get_ok(f"{PD}/escalation_policies/{EP['Payments']}")["escalation_policy"]
    assert len(ep.get("escalation_rules", [])) >= 2, "payments policy still has a single level"

def test_a_second_level_targets_secondary_rotation():
    ep = get_ok(f"{PD}/escalation_policies/{EP['Payments']}")["escalation_policy"]
    rules = ep.get("escalation_rules", [])
    beyond_l1 = [t for r in rules[1:] for t in r.get("targets", [])]
    accepted = {SCHED["Payments Secondary"], PAYMENTS_LEAD_PD}
    assert any(t["id"] in accepted for t in beyond_l1), (
        f"no level beyond 1 pages the payments secondary rotation (targets={beyond_l1})"
    )

def test_c_checkout_db_not_silenced():
    ongoing = pd_list("/maintenance_windows", "maintenance_windows", {"filter": "ongoing"})
    covering = [w for w in ongoing if any(r["id"] == SVC["checkout-db"] for r in w.get("services", []))]
    assert covering == [], f"checkout-db still under ongoing windows {[w['id'] for w in covering]}"

def test_f_reconciler_alerting_enabled():
    svc = get_ok(f"{PD}/services/{SVC['payments-reconciler']}")["service"]
    assert svc["status"] == "active", f"payments-reconciler status={svc['status']}"

def test_d_oncall_handle_pages_current_primary():
    users = slack_get("usergroups.users.list", {"usergroup": UG["Payments"]})["users"]
    assert ANAYA_SLACK in users, f"payments-oncall does not page the current primary ({users})"

def test_d_oncall_handle_stale_member_removed():
    users = slack_get("usergroups.users.list", {"usergroup": UG["Payments"]})["users"]
    assert MARCUS_SLACK not in users, "payments-oncall still pages the re-orged engineer"

def test_t1_trigger_incident_resolved():
    inc = get_ok(f"{PD}/incidents/{TRIGGER_INCIDENT}")["incident"]
    assert inc["status"] == "resolved", f"trigger incident status={inc['status']}"

def test_t2_trigger_ticket_done():
    issue = get_ok(f"{JIRA}/issue/OPS-341")
    cat = (((issue.get("fields") or {}).get("status") or {}).get("statusCategory") or {}).get("key")
    assert cat == "done", f"OPS-341 status category={cat}"

def test_g_payments_first_level_still_primary():
    ep = get_ok(f"{PD}/escalation_policies/{EP['Payments']}")["escalation_policy"]
    rules = ep.get("escalation_rules", [])
    assert rules, "payments policy has no rules"
    l1 = [t["id"] for t in rules[0].get("targets", [])]
    assert l1 == [SCHED["Payments Primary"]], f"payments level 1 changed: {l1}"

def test_g_legacy_schedule_untouched():
    sched = get_ok(f"{PD}/schedules/{SCHED['Checkout Legacy Rotation']}")["schedule"]
    users = [e["user"]["id"] for l in sched.get("schedule_layers", []) for e in l.get("users", [])]
    assert users == [MARCUS_PD], f"legacy rotation edited: {users}"

def test_g_no_overrides_anywhere():
    for name, sid in SCHED.items():
        payload = get_ok(f"{PD}/schedules/{sid}/overrides?since=2026-07-01T00:00:00Z&until=2026-12-31T00:00:00Z")
        assert payload["overrides"] == [], f"override created on {name}"

def test_g_platform_policy_unchanged():
    ep = get_ok(f"{PD}/escalation_policies/{EP['Platform']}")["escalation_policy"]
    rules = ep.get("escalation_rules", [])
    assert len(rules) == 2, f"platform policy rule count changed: {len(rules)}"
    assert [t["id"] for t in rules[0]["targets"]] == [SCHED["Platform Primary"]]
    assert [t["id"] for t in rules[1]["targets"]] == [SCHED["Platform Secondary"]]

def test_g_platform_oncall_group_unchanged():
    users = slack_get("usergroups.users.list", {"usergroup": UG["Platform"]})["users"]
    assert users == [JONAS_SLACK], f"platform-oncall changed: {users}"

def test_g_other_team_usergroups_unchanged():
    groups = {g["id"]: g for g in slack_get("usergroups.list")["usergroups"]}
    assert set(groups) == set(UG.values()), "usergroup set changed"
    for team in TEAMS:
        if team == "Payments":
            continue
        members = groups[UG[team]].get("users", [])
        assert len(members) == 1, f"{team} on-call group membership changed: {members}"

def test_g_future_search_window_preserved():
    win = get_ok(f"{PD}/maintenance_windows/{MW_LEGIT}")["maintenance_window"]
    assert win["start_time"] == "2026-07-14T22:00:00Z", f"legit window start changed: {win['start_time']}"
    assert win["end_time"] == "2026-07-15T02:00:00Z", f"legit window end changed: {win['end_time']}"

def test_g_mobile_legacy_stays_disabled():
    svc = get_ok(f"{PD}/services/{SVC['mobile-push-legacy']}")["service"]
    assert svc["status"] == "disabled", f"mobile-push-legacy status={svc['status']}"

def test_g_service_policies_unchanged_except_trigger():
    services = pd_list("/services", "services")
    expected = {SVC[name]: EP[team] for name, team in SERVICES if name != "checkout-api"}
    actual = {s["id"]: s["escalation_policy"]["id"] for s in services if s["id"] != SVC["checkout-api"]}
    assert actual == expected, "a bystander service's escalation policy changed"

def test_g_service_set_unchanged():
    services = pd_list("/services", "services")
    assert {s["id"] for s in services} == set(SVC.values()), "services created or deleted"

def test_t1x_open_incident_set_exact():
    open_incidents = pd_list(
        "/incidents", "incidents",
        {"statuses[]": ["triggered", "acknowledged"], "date_range": "all"},
    )
    assert {i["id"] for i in open_incidents} == OPEN_NOISE_INCIDENTS, (
        f"open incident set wrong: {sorted(i['id'] for i in open_incidents)}"
    )

def test_g_schedule_set_and_layers_unchanged():
    schedules = pd_list("/schedules", "schedules")
    assert {s["id"] for s in schedules} == set(SCHED.values()), "schedules created or deleted"
    payments_primary = next(s for s in schedules if s["id"] == SCHED["Payments Primary"])
    first = payments_primary["schedule_layers"][0]["users"][0]["user"]["id"]
    assert first == pd_user_id("Anaya Deshpande"), "payments primary rotation edited"

def test_g_pd_users_intact():
    users = pd_list("/users", "users")
    assert len(users) == 56, f"pagerduty user count changed: {len(users)}"
    marcus = get_ok(f"{PD}/users/{MARCUS_PD}")["user"]
    teams = [t["id"] for t in marcus.get("teams", [])]
    assert teams == [pdid("team:Data Platform")], f"Marcus's team membership changed: {teams}"

def test_g_storm_followups_preserved():
    payload = get_ok(f"{IO}/v2/follow_ups?incident_id={STORM_IO_INCIDENT}")
    ids = {f["id"] for f in payload["follow_ups"]}
    assert STORM_FOLLOWUPS <= ids, f"postmortem follow-ups deleted: missing {STORM_FOLLOWUPS - ids}"

def test_g_storm_incident_record_closed_unchanged():
    inc = get_ok(f"{IO}/v2/incidents/{STORM_IO_INCIDENT}")["incident"]
    assert inc["incident_status"]["category"] == "closed", "postmortem incident reopened"

def test_g_postmortem_page_exists():
    status, page = get(f"{CONF}/pages/{PM_PAGE_ID}")
    assert status == 200 and page.get("status") == "current", "postmortem page deleted"

def test_g_noise_tickets_unchanged():
    for key, want in [("REL-216", "done"), ("REL-218", "done"),
                      ("OPS-338", "new"), ("OPS-340", "new"), ("OPS-342", "new")]:
        issue = get_ok(f"{JIRA}/issue/{key}")
        cat = (((issue.get("fields") or {}).get("status") or {}).get("statusCategory") or {}).get("key")
        assert cat == want, f"{key} status category changed to {cat}"
