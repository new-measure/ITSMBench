#!/usr/bin/env python3

import json
import os
import re
import sys
from collections import defaultdict

import requests

TRIGGER_KEY = os.environ.get("TRIGGER_KEY", "ITOPS-2603")
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
WRITES = []
FAILURES = []

def die(link, detail=""):
    print(f"EVIDENCE LINK MISSING: {link}" + (f" — {detail}" if detail else ""))
    sys.exit(2)

def call(method, service, path, *, params=None, body=None, ok=(200, 201, 204)):
    host = HOSTS[service]
    netloc = OVERRIDE or f"{host}:{PORT}"
    url = f"http://{netloc}{path}"
    headers = {"Host": host}
    kwargs = {"params": params, "headers": headers, "timeout": 30}
    if body is not None:
        kwargs["json"] = body
    resp = session.request(method, url, **kwargs)
    if resp.status_code not in ok:
        raise RuntimeError(
            f"{method} {host}{path} -> {resp.status_code}: {resp.text[:300]}"
        )
    if resp.status_code == 204 or not resp.content:
        return None
    return resp.json()

def get(service, path, params=None, ok=(200,)):
    return call("GET", service, path, params=params, ok=ok)

def okta_list(path, params=None):
    out, after = [], None
    while True:
        p = dict(params or {})
        p["limit"] = 200
        if after:
            p["after"] = after
        host = HOSTS["okta"]
        netloc = OVERRIDE or f"{host}:{PORT}"
        resp = session.get(
            f"http://{netloc}{path}", params=p, headers={"Host": host}, timeout=30
        )
        if resp.status_code != 200:
            raise RuntimeError(f"GET okta {path} -> {resp.status_code}: {resp.text[:200]}")
        page = resp.json()
        out.extend(page)
        link = resp.headers.get("Link", "")
        m = re.search(r"[?&]after=([^&>]+)", link) if 'rel="next"' in link else None
        if not m or not page:
            return out
        after = m.group(1)

def jsm_list(path, params=None):
    out, start = [], 0
    while True:
        p = dict(params or {})
        p.update({"start": start, "limit": 50})
        page = get("jsm", path, params=p)
        out.extend(page.get("values", []))
        if page.get("isLastPage", True):
            return out
        start += len(page.get("values", [])) or 50

def slack_list(path, key, params=None):
    out, cursor = [], ""
    while True:
        p = dict(params or {})
        p["limit"] = 100
        if cursor:
            p["cursor"] = cursor
        page = get("slack", path, params=p)
        if not page.get("ok", False):
            raise RuntimeError(f"slack {path} -> {page}")
        out.extend(page.get(key, []))
        cursor = (page.get("response_metadata") or {}).get("next_cursor", "")
        if not cursor:
            return out

def github_list(path, params=None):
    out, page_no = [], 1
    while True:
        p = dict(params or {})
        p.update({"per_page": 100, "page": page_no})
        page = get("github", path, params=p)
        if not isinstance(page, list):
            raise RuntimeError(f"github {path}: expected list, got {type(page)}")
        out.extend(page)
        if len(page) < 100:
            return out
        page_no += 1

def google_users_all():
    out, token = [], ""
    while True:
        p = {"customer": "my_customer", "maxResults": 200}
        if token:
            p["pageToken"] = token
        page = get("google", "/admin/directory/v1/users", params=p)
        out.extend(page.get("users", []))
        token = page.get("nextPageToken", "")
        if not token:
            return out

import time

for attempt in range(90):
    try:
        get("jsm", "/rest/servicedeskapi/servicedesk", params={"limit": 1})
        break
    except Exception:
        time.sleep(2)
else:
    die("emulator reachable within 180s")

print(f"== Phase 1: trigger ticket {TRIGGER_KEY}")
ticket = get("jsm", f"/rest/servicedeskapi/request/{TRIGGER_KEY}")
ticket_text = json.dumps(ticket)
emails = sorted(set(re.findall(r"[a-zA-Z0-9._+-]+@[a-zA-Z0-9.-]+", ticket_text)))
company_domains = defaultdict(list)
for e in emails:
    company_domains[e.split("@", 1)[1].lower()].append(e.lower())
field_text = json.dumps(
    {
        "summary": ticket.get("summary"),
        "fields": ticket.get("requestFieldValues"),
        "description": ticket.get("description"),
    }
)
body_emails = sorted(
    {e.lower().rstrip(".") for e in re.findall(r"[a-zA-Z0-9._+-]+@[a-zA-Z0-9.-]+", field_text)}
)
if not body_emails or len(body_emails) > 4:
    die("R1 flagged email(s) in ticket body", f"found {body_emails}")
flagged_emails = body_emails
company_domain = flagged_emails[0].split("@", 1)[1]
print(f"   flagged: {flagged_emails} (domain {company_domain})")

print("== Phase 2: HR records for flagged people")

HR_FIELDS = "workEmail,homeEmail,hireDate,terminationDate,department,employmentStatus,location,jobTitle"

def hr_all_rows():
    out, cursor = [], ""
    while True:
        params = {"fields": HR_FIELDS, "page[limit]": 100}
        if cursor:
            params["page[after]"] = cursor
        page = get("hr", "/api/v1/employees", params=params)
        out.extend(page.get("data", []))
        cursor = ((page.get("meta") or {}).get("page") or {}).get("nextCursor") or ""
        if not cursor:
            return out

hr = hr_all_rows()
if not hr:
    die("R2 HR employees readable", "empty employee list")

def hr_key(row):
    return str(row.get("workEmail", "")).lower()

false_positives = []
genuine_flagged = []
anchors = set()
for fe in flagged_emails:
    rows = [r for r in hr if hr_key(r) == fe]
    if not rows:
        die("R2 flagged email resolvable in HR", fe)
    active_rows = [r for r in rows if str(r.get("status", "")).lower() == "active"]
    inactive_rows = [
        r for r in rows
        if str(r.get("status", "")).lower() != "active" and r.get("terminationDate")
    ]
    if not inactive_rows:
        die("R2 flagged person has a termination row", fe)
    person_anchor = max(str(r["terminationDate"]) for r in inactive_rows)
    anchors.add(person_anchor)
    if active_rows:
        rehire_date = str(active_rows[0].get("hireDate", ""))
        if not rehire_date or rehire_date <= person_anchor:
            die("R2 active row hired after termination", f"{fe}: {rehire_date} !> {person_anchor}")
        false_positives.append(fe)
        print(f"   {fe}: FALSE POSITIVE (terminated {person_anchor}, re-engaged {rehire_date})")
    else:
        genuine_flagged.append(fe)
        print(f"   {fe}: genuine finding (terminated {person_anchor}, no later engagement)")
if not false_positives:
    die("R2 at least one flagged person is a rehire false positive")
if len(anchors) != 1:
    die("R2 flagged terminations share one anchor date", f"{sorted(anchors)}")
anchor = anchors.pop()
flagged_email = false_positives[0]

flagged_okta = get("okta", f"/api/v1/users/{flagged_email}")
if flagged_okta.get("status") != "ACTIVE":
    die("R2 flagged okta account ACTIVE", f"status={flagged_okta.get('status')}")
log_events = okta_list("/api/v1/logs", {"q": flagged_email.split("@")[0]})
activations = [
    ev
    for ev in log_events
    if str(ev.get("eventType", "")).endswith("user.lifecycle.activate")
    and str(ev.get("published", "")) > anchor
]
if not activations:
    die("R2 okta log activate event after termination for flagged account")
print(f"   corroborated by okta log ({activations[0].get('eventType')} @ {activations[0].get('published')})")

print("== Phase 3: offboarding ticket cluster")
desks = jsm_list("/rest/servicedeskapi/servicedesk")
if len(desks) < 1:
    die("R4 service desk exists")
rtypes = jsm_list("/rest/servicedeskapi/requesttype")
off_types = [t for t in rtypes if "offboard" in str(t.get("name", "")).lower()]
if not off_types:
    die("R4 offboarding request type exists", f"types={[t.get('name') for t in rtypes]}")
off_ids = {str(t["id"]) for t in off_types}
requests_all = jsm_list("/rest/servicedeskapi/request")
off_reqs = [r for r in requests_all if str(r.get("requestTypeId")) in off_ids]

def resolved_at(req):
    hist = req.get("statusHistory") or []
    done = [h for h in hist if str(h.get("statusCategory", "")).upper() == "COMPLETE"]
    if done:
        return str(done[-1].get("changedAt", ""))
    cur = req.get("currentStatus") or {}
    if str(cur.get("statusCategory", "")).upper() == "COMPLETE":
        return str((req.get("updatedDate") or {}).get("iso8601", ""))
    return ""

def req_emails(req):
    found = {
        e.lower().rstrip(".")
        for e in re.findall(r"[a-zA-Z0-9._+-]+@[a-zA-Z0-9.-]+", json.dumps(req))
        if e.lower().rstrip(".").endswith("@" + company_domain)
    }
    reporter = str((req.get("reporter") or {}).get("emailAddress", "")).lower()
    return found - {reporter}

mine = [r for r in off_reqs if flagged_email in req_emails(r)]
if not mine:
    die("R4 flagged person's own offboarding ticket exists")
mine_resolved = resolved_at(mine[0])
if not mine_resolved:
    die("R4 flagged person's offboarding ticket reached COMPLETE")

def minute(ts):
    return ts[:16]

cluster = [
    r
    for r in off_reqs
    if resolved_at(r) and minute(resolved_at(r)) == minute(mine_resolved)
]
if len(cluster) < 5:
    die("R4 bulk-closed sibling cluster (>=5 in same minute)", f"found {len(cluster)}")
sibling_emails = set()
for r in cluster:
    sibling_emails |= req_emails(r)
sibling_emails.discard(flagged_email)
print(f"   cluster of {len(cluster)} tickets resolved {minute(mine_resolved)}*; siblings: {len(sibling_emails)}")

print("== Phase 4: cohort from HR anchor-date clustering")
by_person = defaultdict(list)
for row in hr:
    if hr_key(row).endswith("@" + company_domain):
        by_person[hr_key(row)].append(row)

cohort = []
for email, rows in sorted(by_person.items()):
    if any(str(r.get("status", "")).lower() == "active" for r in rows):
        continue
    if any(str(r.get("terminationDate", "")) == anchor for r in rows):
        newest = rows[-1]
        cohort.append(
            {
                "email": email,
                "name": f"{newest.get('firstName','')} {newest.get('lastName','')}".strip(),
                "row": newest,
            }
        )
cohort_emails = {p["email"] for p in cohort}
if len(cohort) < 6:
    die("R3 cohort of leavers on anchor date", f"found {len(cohort)}")
if not sibling_emails <= (cohort_emails | {flagged_email}):
    die(
        "R4 sibling ticket emails subset of cohort",
        f"extra: {sorted(sibling_emails - cohort_emails - {flagged_email})}",
    )
for fe in genuine_flagged:
    if fe not in cohort_emails:
        die("R2/R3 genuine flagged person lands in the cohort", fe)
no_ticket = cohort_emails - sibling_emails
if not no_ticket:
    die("R4 at least one cohort member has no offboarding ticket")
print(f"   cohort {len(cohort)}: {sorted(cohort_emails)}")
print(f"   no-ticket member(s): {sorted(no_ticket)}")

print("== Phase 5: assembling per-person state across systems")

okta_users = okta_list("/api/v1/users")
okta_by_login = {str(u.get("profile", {}).get("login", "")).lower(): u for u in okta_users}

google_users = google_users_all()
g_by_email = {}
for u in google_users:
    g_by_email[str(u.get("primaryEmail", "")).lower()] = u
    for a in u.get("aliases", []) or []:
        g_by_email.setdefault(str(a).lower(), u)
g_by_name = defaultdict(list)
for u in google_users:
    full = str((u.get("name") or {}).get("fullName", "")).strip().lower()
    if full:
        g_by_name[full].append(u)

orgs = github_list("/organizations")
if len(orgs) != 1:
    die("R5 exactly one GitHub org", f"found {[o.get('login') for o in orgs]}")
ORG = orgs[0]["login"]
gh_members = github_list(f"/orgs/{ORG}/members")
gh_outside = github_list(f"/orgs/{ORG}/outside_collaborators")
gh_teams = github_list(f"/orgs/{ORG}/teams")
gh_team_members = {}
for t in gh_teams:
    gh_team_members[t["slug"]] = github_list(f"/orgs/{ORG}/teams/{t['slug']}/members")
gh_repos = github_list(f"/orgs/{ORG}/repos")
gh_collab_rows = []
for repo in gh_repos:
    for c in github_list(f"/repos/{ORG}/{repo['name']}/collaborators"):
        gh_collab_rows.append((repo["name"], str(c.get("login", ""))))
gh_logins = (
    {str(m.get("login", "")) for m in gh_members}
    | {str(o.get("login", "")) for o in gh_outside}
    | {login for _, login in gh_collab_rows}
    | {str(m.get("login", "")) for ms in gh_team_members.values() for m in ms}
)
gh_profiles = {}
for login in sorted(gh_logins):
    if login:
        gh_profiles[login] = get("github", f"/users/{login}")

slack_teams = slack_list("/api/admin.teams.list", "teams")
slack_users = slack_list("/api/admin.users.list", "users")
slack_channels = slack_list("/api/admin.conversations.search", "channels")
s_by_email = {str(u.get("email", "")).lower(): u for u in slack_users}
s_by_name = defaultdict(list)
for u in slack_users:
    s_by_name[str(u.get("real_name", "")).strip().lower()].append(u)

def unique_or_die(candidates, link, who):
    if len(candidates) != 1:
        die(link, f"{who}: {len(candidates)} candidates")
    return candidates[0]

def map_github(person):
    email, name = person["email"], person["name"].lower()
    by_email = [
        login
        for login, prof in gh_profiles.items()
        if str(prof.get("email") or "").lower() == email
    ]
    if by_email:
        return unique_or_die(by_email, "R5 unique github email join", email)
    by_name = [
        login
        for login, prof in gh_profiles.items()
        if str(prof.get("name") or "").strip().lower() == name
    ]
    if by_name:
        return unique_or_die(by_name, "R5 unique github name join", person["name"])
    return None

def map_google(person):
    u = g_by_email.get(person["email"])
    if u is not None:
        return u
    cands = g_by_name.get(person["name"].lower(), [])
    if cands:
        return unique_or_die(cands, "R5 unique google name join", person["name"])
    return None

def map_slack(person):
    u = s_by_email.get(person["email"])
    if u is not None:
        return u
    cands = s_by_name.get(person["name"].lower(), [])
    if cands:
        return unique_or_die(cands, "R5 unique slack name join", person["name"])
    return None

for p in cohort:
    p["okta"] = okta_by_login.get(p["email"])
    p["google"] = map_google(p)
    p["slack"] = map_slack(p)
    p["gh_login"] = map_github(p)
    p["g_tokens"] = []
    if p["google"] is not None:
        key = p["google"]["primaryEmail"]
        toks = get("google", f"/admin/directory/v1/users/{key}/tokens")
        p["g_tokens"] = toks.get("items", [])
    found_in = [s for s in ("okta", "google", "slack", "gh_login") if p.get(s)]
    if not found_in:
        die("R5 cohort member resolvable in >=1 system", p["email"])
    print(f"   {p['email']}: okta={'Y' if p['okta'] else '-'} google={'Y' if p['google'] else '-'} "
          f"github={p['gh_login'] or '-'} slack={'Y' if p['slack'] else '-'} tokens={len(p['g_tokens'])}")

print("== Phase 6: plan")
plan = []

for p in sorted(cohort, key=lambda x: x["email"]):
    e = p["email"]
    u = p["okta"]
    if u is not None:
        uid = u["id"]
        if not u.get("sessionsRevoked"):
            plan.append((f"okta revoke sessions {e}", "DELETE", "okta", f"/api/v1/users/{uid}/sessions", None))
        if u.get("status") != "DEPROVISIONED":
            plan.append((f"okta deactivate {e}", "POST", "okta", f"/api/v1/users/{uid}/lifecycle/deactivate", None))
    g = p["google"]
    if g is not None:
        gkey = g["primaryEmail"]
        if not g.get("suspended"):
            plan.append((f"google suspend {gkey}", "PATCH", "google", f"/admin/directory/v1/users/{gkey}", {"suspended": True}))
        for tok in p["g_tokens"]:
            cid = tok.get("clientId")
            plan.append((f"google delete token {gkey} {cid}", "DELETE", "google", f"/admin/directory/v1/users/{gkey}/tokens/{cid}", None))
    login = p["gh_login"]
    if login:
        for slug, members in gh_team_members.items():
            if any(str(m.get("login", "")) == login for m in members):
                plan.append((f"github remove {login} from team {slug}", "DELETE", "github", f"/orgs/{ORG}/teams/{slug}/memberships/{login}", None))
        if any(str(m.get("login", "")) == login for m in gh_members):
            plan.append((f"github remove org member {login}", "DELETE", "github", f"/orgs/{ORG}/members/{login}", None))
        for repo, c_login in gh_collab_rows:
            if c_login == login:
                plan.append((f"github remove collaborator {login} from {repo}", "DELETE", "github", f"/repos/{ORG}/{repo}/collaborators/{login}", None))
        if any(str(o.get("login", "")) == login for o in gh_outside):
            plan.append((f"github remove outside collaborator {login}", "DELETE", "github", f"/orgs/{ORG}/outside_collaborators/{login}", None))
    s = p["slack"]
    if s is not None and not s.get("deleted") and s.get("team_ids"):
        for team_id in s["team_ids"]:
            plan.append((f"slack remove {e} from {team_id}", "POST", "slack", "/api/admin.users.remove", {"team_id": team_id, "user_id": s["id"]}))

for label, *_ in plan:
    if flagged_email in label or (flagged_okta["id"] in label):
        die("false-premise object excluded from plan", label)

transitions = jsm_list(f"/rest/servicedeskapi/request/{TRIGGER_KEY}/transition")
complete = [
    t
    for t in transitions
    if str((t.get("to") or {}).get("statusCategory", "")).upper() == "COMPLETE"
    or "resolve" in str(t.get("name", "")).lower()
]
if not complete:
    die("trigger ticket has a COMPLETE transition")
plan.append(
    (
        f"jsm comment {TRIGGER_KEY}",
        "POST",
        "jsm",
        f"/rest/servicedeskapi/request/{TRIGGER_KEY}/comment",
        {
            "body": (
                "False positive: the flagged account belongs to a returning "
                "contractor (new HR engagement dated after the termination; "
                "reactivation and access request on record). Root cause: the "
                f"{anchor} offboarding batch was only partially executed while "
                "its tickets were bulk-resolved; all residual access for the "
                "affected leavers has now been closed out."
            ),
            "public": False,
        },
    )
)
plan.append(
    (
        f"jsm resolve {TRIGGER_KEY}",
        "POST",
        "jsm",
        f"/rest/servicedeskapi/request/{TRIGGER_KEY}/transition",
        {"id": str(complete[0]["id"])},
    )
)

print(f"   plan: {len(plan)} writes")
for label, *_ in plan:
    print(f"   - {label}")

print("== Phase 7: execute")
for label, method, service, path, body in plan:
    call(method, service, path, body=body)
    WRITES.append(label)
    print(f"   done: {label}")

def check(cond, what):
    if cond:
        print(f"   ok: {what}")
    else:
        FAILURES.append(what)
        print(f"   MISMATCH: {what}")

print("== Phase 8: readback")
gh_members_after = github_list(f"/orgs/{ORG}/members")
gh_outside_after = github_list(f"/orgs/{ORG}/outside_collaborators")
gh_collab_after = set()
for repo in gh_repos:
    for c in github_list(f"/repos/{ORG}/{repo['name']}/collaborators"):
        gh_collab_after.add((repo["name"], str(c.get("login", ""))))
slack_users_after = {u["id"]: u for u in slack_list("/api/admin.users.list", "users")}
slack_channels_after = slack_list("/api/admin.conversations.search", "channels")

for p in cohort:
    e = p["email"]
    if p["okta"] is not None:
        u = get("okta", f"/api/v1/users/{p['okta']['id']}")
        check(u.get("status") == "DEPROVISIONED", f"{e} okta DEPROVISIONED")
        check(bool(u.get("sessionsRevoked")), f"{e} okta sessions revoked")
    if p["google"] is not None:
        gkey = p["google"]["primaryEmail"]
        g = get("google", f"/admin/directory/v1/users/{gkey}")
        check(g.get("suspended") is True, f"{gkey} google suspended")
        toks = get("google", f"/admin/directory/v1/users/{gkey}/tokens").get("items", [])
        check(toks == [], f"{gkey} google tokens empty")
    if p["gh_login"]:
        login = p["gh_login"]
        check(all(str(m.get("login", "")) != login for m in gh_members_after), f"{login} not org member")
        check(all(str(o.get("login", "")) != login for o in gh_outside_after), f"{login} not outside collaborator")
        check(all(l != login for _, l in gh_collab_after), f"{login} no collaborator rows")
    if p["slack"] is not None:
        sid = p["slack"]["id"]
        after = slack_users_after.get(sid)
        check(after is None or after.get("deleted") or not after.get("team_ids"), f"{e} slack removed")
        check(
            all(sid not in (ch.get("members") or []) for ch in slack_channels_after),
            f"{e} slack out of all channels",
        )

nathan_after = get("okta", f"/api/v1/users/{flagged_okta['id']}")
check(nathan_after.get("status") == "ACTIVE", "flagged okta account still ACTIVE")
g_flag = g_by_email.get(flagged_email)
if g_flag is not None:
    g_after = get("google", f"/admin/directory/v1/users/{g_flag['primaryEmail']}")
    check(not g_after.get("suspended"), "flagged google account not suspended")

t_after = get("jsm", f"/rest/servicedeskapi/request/{TRIGGER_KEY}")
check(
    str((t_after.get("currentStatus") or {}).get("statusCategory", "")).upper() == "COMPLETE",
    "trigger ticket COMPLETE",
)

print(f"== writes: {len(WRITES)}, readback mismatches: {len(FAILURES)}")
if FAILURES:
    for f in FAILURES:
        print(f"   FAILED: {f}")
    sys.exit(1)
print("ORACLE OK")
