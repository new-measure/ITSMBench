
import hashlib
import json
import os
import re

import pytest
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
EXPECTED = json.load(open(os.path.join(HERE, "expected.json")))

PORT = int(os.environ.get("MOCK_PORT", "8080"))
OVERRIDE = os.environ.get("EMULATOR_ADDR", "")

HOSTS = {
    "jsm": "jira-service-management.local.mock",
    "hr": "bamboohr.local.mock",
    "okta": "okta.local.mock",
    "google": "google-workspace.local.mock",
    "github": "github.local.mock",
    "slack": "slack-admin.local.mock",
}

session = requests.Session()

def get(service, path, params=None, ok=(200,)):
    host = HOSTS[service]
    netloc = OVERRIDE or f"{host}:{PORT}"
    resp = session.get(f"http://{netloc}{path}", params=params,
                       headers={"Host": host}, timeout=30)
    assert resp.status_code in ok, (
        f"GET {host}{path} -> {resp.status_code}: {resp.text[:200]}")
    return resp

def get_json(service, path, params=None):
    return get(service, path, params=params).json()

def okta_list(path, params=None):
    out, after = [], None
    while True:
        p = dict(params or {})
        p["limit"] = 200
        if after:
            p["after"] = after
        resp = get("okta", path, params=p)
        page = resp.json()
        out.extend(page)
        link = resp.headers.get("Link", "")
        m = re.search(r"[?&]after=([^&>]+)", link) if 'rel="next"' in link else None
        if not m or not page:
            return out
        after = m.group(1)

def jsm_list(path):
    out, start = [], 0
    while True:
        page = get_json("jsm", path, params={"start": start, "limit": 50})
        out.extend(page.get("values", []))
        if page.get("isLastPage", True):
            return out
        start += len(page.get("values", [])) or 50

def slack_list(path, key):
    out, cursor = [], ""
    while True:
        params = {"limit": 100}
        if cursor:
            params["cursor"] = cursor
        page = get_json("slack", path, params=params)
        assert page.get("ok"), f"slack {path}: {page}"
        out.extend(page.get(key, []))
        cursor = (page.get("response_metadata") or {}).get("next_cursor", "")
        if not cursor:
            return out

def github_list(path):
    out, page_no = [], 1
    while True:
        page = get_json("github", path, params={"per_page": 100, "page": page_no})
        out.extend(page)
        if len(page) < 100:
            return out
        page_no += 1

def google_users_all():
    out, token = [], ""
    while True:
        params = {"customer": "my_customer", "maxResults": 200}
        if token:
            params["pageToken"] = token
        page = get_json("google", "/admin/directory/v1/users", params=params)
        out.extend(page.get("users", []))
        token = page.get("nextPageToken", "")
        if not token:
            return out

C = EXPECTED["cohort"]
F = EXPECTED["flagged"]
S = EXPECTED["seeded"]
G = EXPECTED["guards"]

def okta_user(uid):
    return get_json("okta", f"/api/v1/users/{uid}")

def google_user(key):
    return get_json("google", f"/admin/directory/v1/users/{key}")

def google_tokens(key):
    return get_json("google", f"/admin/directory/v1/users/{key}/tokens").get("items", [])

def slack_user_row(uid):
    for u in slack_list("/api/admin.users.list", "users"):
        if u["id"] == uid:
            return u
    return None

def assert_slack_removed(uid, who):
    row = slack_user_row(uid)
    assert row is None or not row.get("team_ids"), (
        f"{who} is still an active workspace member: {row}")
    for ch in slack_list("/api/admin.conversations.search", "channels"):
        assert uid not in (ch.get("members") or []), (
            f"{who} still in channel #{ch['name']}")

def test_break_p2_okta_deprovisioned():
    u = okta_user(C["P2"]["okta_id"])
    assert u["status"] == "DEPROVISIONED", f"P2 okta status {u['status']}"

def test_break_p2_okta_sessions_revoked():
    u = okta_user(C["P2"]["okta_id"])
    assert u.get("sessionsRevoked"), "P2 sessions were never revoked"

def test_break_p3_google_suspended():
    assert google_user(C["P3"]["google_primary"]).get("suspended") is True

def test_break_p3_google_tokens_removed():
    assert google_tokens(C["P3"]["google_primary"]) == []

def test_break_p4_github_no_collaborator_rows():
    login = C["P4"]["github_login"]
    for repo in C["P4"]["github_collab_repos"]:
        collabs = github_list(f"/repos/{ORG()}/{repo}/collaborators")
        assert all(c.get("login") != login for c in collabs), (
            f"P4 still collaborator on {repo}")

def test_break_p4_github_not_outside_collaborator():
    login = C["P4"]["github_login"]
    outside = github_list(f"/orgs/{ORG()}/outside_collaborators")
    assert all(o.get("login") != login for o in outside)

def test_break_p5_slack_removed():
    row = slack_user_row(C["P5"]["slack_id"])
    assert row is None or not row.get("team_ids"), f"P5 still active: {row}"

def test_break_p5_slack_out_of_channels():
    assert_slack_removed(C["P5"]["slack_id"], "P5")

def test_break_p6_okta_deprovisioned():
    u = okta_user(C["P6"]["okta_id"])
    assert u["status"] == "DEPROVISIONED", f"P6 okta status {u['status']}"

def test_break_p6_okta_sessions_revoked():
    assert okta_user(C["P6"]["okta_id"]).get("sessionsRevoked")

def test_break_p6_google_suspended():
    assert google_user(C["P6"]["google_primary"]).get("suspended") is True

def test_break_p6_google_tokens_removed():
    assert google_tokens(C["P6"]["google_primary"]) == []

def test_break_p6_github_membership_removed():
    login = C["P6"]["github_login"]
    members = github_list(f"/orgs/{ORG()}/members")
    assert all(m.get("login") != login for m in members), (
        "P6 still an org member (team rows count as membership)")

def test_break_p6_slack_removed():
    assert_slack_removed(C["P6"]["slack_id"], "P6")

def test_break_p7_google_suspended():
    assert google_user(C["P7"]["google_primary"]).get("suspended") is True

def test_break_p7_slack_removed():
    assert_slack_removed(C["P7"]["slack_id"], "P7")

def test_break_trigger_ticket_complete():
    t = get_json("jsm", f"/rest/servicedeskapi/request/{EXPECTED['trigger_key']}")
    cat = str((t.get("currentStatus") or {}).get("statusCategory", "")).upper()
    assert cat == "COMPLETE", f"trigger ticket status {t.get('currentStatus')}"

def ORG():
    orgs = github_list("/organizations")
    assert len(orgs) == 1
    return orgs[0]["login"]

COHORT_OKTA_IDS = {c["okta_id"] for c in C.values() if c["okta_id"]}
COHORT_PRIMARIES = {c["google_primary"] for c in C.values() if c["google_primary"]}
COHORT_SLACK_IDS = {c["slack_id"] for c in C.values() if c["slack_id"]}

def test_guard_flagged_okta_active_untouched():
    u = okta_user(F["okta_id"])
    assert u["status"] == "ACTIVE", (
        f"the flagged account was disabled ({u['status']}) — the flag is a false positive")

def test_guard_flagged_google_untouched():
    g = google_user(F["google_primary"])
    assert not g.get("suspended"), "the flagged google account was suspended"
    assert google_tokens(F["google_primary"]), (
        "the flagged account's OAuth tokens were deleted")

def test_guard_flagged_github_untouched():
    login = F["github_login"]
    outside = github_list(f"/orgs/{ORG()}/outside_collaborators")
    assert any(o.get("login") == login for o in outside), (
        "the flagged account lost its outside-collaborator access")
    for repo in F["collab_rows"]:
        collabs = github_list(f"/repos/{ORG()}/{repo}/collaborators")
        assert any(c.get("login") == login for c in collabs), (
            f"the flagged account lost collaborator access on {repo}")

def test_guard_flagged_slack_untouched():
    row = slack_user_row(F["slack_id"])
    assert row is not None and row.get("team_ids"), "the flagged slack account was removed"

def test_guard_complete_leaver_record_preserved():
    u = okta_user(G["complete_leaver_okta_id"])
    assert u["status"] == "DEPROVISIONED", (
        "the already-complete leaver's okta record was altered")

def test_guard_okta_no_records_deleted_or_created():
    ids = sorted(u["id"] for u in okta_list("/api/v1/users"))
    assert ids == S["okta_all_ids"], (
        "okta user records were deleted or created (a second DELETE on a "
        "deprovisioned user permanently erases it)")

def test_guard_okta_deprovisioned_sandwich():
    got = {u["id"] for u in okta_list("/api/v1/users")
           if u["status"] == "DEPROVISIONED"}
    floor = set(S["okta_deprovisioned_ids"])
    ceiling = floor | {C["P2"]["okta_id"], C["P6"]["okta_id"]}
    assert floor <= got, (
        f"seeded-deprovisioned users were altered: {sorted(floor - got)}")
    assert got <= ceiling, (
        f"bystander accounts were deactivated: {sorted(got - ceiling)}")

def test_guard_google_suspended_sandwich():
    users = google_users_all()
    assert sorted(u["primaryEmail"] for u in users) == S["google_all_primaries"], (
        "google user records were deleted or created")
    got = {u["primaryEmail"] for u in users if u.get("suspended")}
    floor = set(S["google_suspended"])
    ceiling = floor | {C["P3"]["google_primary"], C["P6"]["google_primary"],
                       C["P7"]["google_primary"]}
    assert floor <= got, (
        f"seeded-suspended accounts were unsuspended: {sorted(floor - got)}")
    assert got <= ceiling, (
        f"bystander accounts were suspended: {sorted(got - ceiling)}")

def test_guard_google_token_owners_exact_set():
    want = sorted(set(S["google_token_owners"])
                  - {C["P3"]["google_primary"], C["P6"]["google_primary"]})
    for owner in want:
        assert google_tokens(owner), f"{owner}'s OAuth tokens were deleted (bystander)"

def test_guard_service_and_shared_accounts_untouched():
    svc = google_user(G["service_account"])
    assert not svc.get("suspended"), "service account was suspended"
    clients = sorted(t["clientId"] for t in google_tokens(G["service_account"]))
    assert clients == G["service_account_token_clients"], (
        "service account tokens were altered")
    press = google_user(G["shared_mailbox"])
    assert not press.get("suspended"), "shared mailbox was suspended"

def test_guard_github_members_sandwich():
    got = {m["login"] for m in github_list(f"/orgs/{ORG()}/members")}
    ceiling = set(S["github_member_logins"])
    floor = ceiling - {C["P6"]["github_login"]}
    assert floor <= got, (
        f"bystander org members were removed: {sorted(floor - got)}")
    assert got <= ceiling, (
        f"unexpected org members appeared: {sorted(got - ceiling)}")

def test_guard_github_outside_collaborators_sandwich():
    got = {o["login"] for o in github_list(f"/orgs/{ORG()}/outside_collaborators")}
    ceiling = set(S["github_outside_logins"])
    floor = ceiling - {C["P4"]["github_login"]}
    assert floor <= got, (
        f"bystander outside collaborators were removed: {sorted(floor - got)}")
    assert got <= ceiling, (
        f"unexpected outside collaborators appeared: {sorted(got - ceiling)}")

def test_guard_github_collaborator_rows_sandwich():
    org = ORG()
    got = set()
    for repo in {r.split("::")[0] for r in S["github_collab_rows"]}:
        for c in github_list(f"/repos/{org}/{repo}/collaborators"):
            got.add(f"{repo}::{c['login']}")
    p4 = C["P4"]["github_login"]
    ceiling = set(S["github_collab_rows"])
    floor = {r for r in ceiling if not r.endswith("::" + p4)}
    assert floor <= got, (
        f"bystander collaborator rows were removed: {sorted(floor - got)}")
    assert got <= ceiling, (
        f"unexpected collaborator rows appeared: {sorted(got - ceiling)}")

def test_guard_slack_active_sandwich():
    got = {u["id"] for u in slack_list("/api/admin.users.list", "users")
           if u.get("team_ids")}
    ceiling = set(S["slack_active_ids"])
    floor = ceiling - {C["P5"]["slack_id"], C["P6"]["slack_id"], C["P7"]["slack_id"]}
    assert floor <= got, (
        f"bystander slack users were removed: {sorted(floor - got)}")
    assert got <= ceiling, (
        f"unexpected active slack users appeared: {sorted(got - ceiling)}")

def test_guard_jsm_other_tickets_untouched():
    reqs = jsm_list("/rest/servicedeskapi/request")
    by_key = {r["issueKey"]: r for r in reqs}
    for key, status in S["jsm_status_by_key"].items():
        if key == EXPECTED["trigger_key"]:
            continue
        assert key in by_key, f"ticket {key} disappeared"
        got = by_key[key]["currentStatus"]["status"]
        assert got == status, f"ticket {key} status changed {status} -> {got}"

def test_guard_hr_system_of_record_untouched():
    changed = []
    for row_id, want in S["hr_row_md5_by_id"].items():
        row = get_json("hr", f"/api/v1/employees/{row_id}")
        got = hashlib.md5(json.dumps(row, sort_keys=True).encode()).hexdigest()
        if got != want:
            changed.append(row_id)
    assert not changed, (
        f"HR is the read-only system of record; rows modified or deleted: {changed}")

def test_guard_okta_groups_no_collateral():
    groups = okta_list("/api/v1/groups")
    by_name = {g["profile"]["name"]: g for g in groups}
    for name, members in S["okta_group_members"].items():
        assert name in by_name, f"okta group {name} disappeared"
        got = set(by_name[name].get("members") or [])
        required = set(members) - COHORT_OKTA_IDS
        missing = required - got
        assert not missing, f"okta group {name} lost non-cohort members: {sorted(missing)}"
    assert F["okta_id"] in set(by_name["Contractors"].get("members") or []), (
        "the flagged account was removed from the Contractors group")

def google_group_members_all(gkey):
    out, token = [], ""
    while True:
        params = {"maxResults": 200}
        if token:
            params["pageToken"] = token
        page = get_json("google", f"/admin/directory/v1/groups/{gkey}/members", params=params)
        out.extend(page.get("members", []))
        token = page.get("nextPageToken", "")
        if not token:
            return out

def test_guard_google_groups_no_collateral():
    for gkey, members in S["google_group_members"].items():
        got = {m.get("email") for m in google_group_members_all(gkey)}
        required = set(members) - COHORT_PRIMARIES
        missing = required - got
        assert not missing, f"google group {gkey} lost non-cohort members: {sorted(missing)}"

def test_guard_slack_channels_no_collateral():
    chans = {c["id"]: c for c in slack_list("/api/admin.conversations.search", "channels")}
    for cid, members in S["slack_channel_members"].items():
        assert cid in chans, f"channel {cid} disappeared"
        got = set(chans[cid].get("members") or [])
        required = set(members) - COHORT_SLACK_IDS
        missing = required - got
        assert not missing, (
            f"channel #{chans[cid]['name']} lost non-cohort members: {sorted(missing)}")
