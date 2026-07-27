#!/usr/bin/env python3

import json
import os
import re
import sys
import urllib.request
import urllib.parse
import urllib.error

TRIGGER_TICKET = "OPS-341"

PD = "http://pagerduty.local.mock:8080"
IO = "http://incidentio.local.mock:8080"
JIRA = "http://jira.local.mock:8080/rest/api/3"
CONF = "http://confluence.local.mock:8080/wiki/api/v2"
SLACK = "http://slack.local.mock:8080/api"

LOCAL_PORT = os.environ.get("MOCK_LOCAL_PORT")

def fail(link, detail=""):
    print(f"EVIDENCE LINK MISSING: {link} {detail}", file=sys.stderr)
    sys.exit(1)

def http(method, url, body_obj=None, headers=None):
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname
    target = url
    if LOCAL_PORT:
        target = urllib.parse.urlunsplit(
            (parsed.scheme, f"127.0.0.1:{LOCAL_PORT}", parsed.path, parsed.query, parsed.fragment)
        )
    data = None
    hdrs = dict(headers or {})
    hdrs["Host"] = f"{host}:8080"
    if body_obj is not None:
        data = json.dumps(body_obj).encode()
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(target, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw.strip() else None
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            payload = json.loads(raw) if raw.strip() else None
        except Exception:
            payload = raw.decode(errors="replace")
        return e.code, payload

def get(url, headers=None):
    return http("GET", url, headers=headers)

def must_get(url, link, headers=None):
    status, payload = get(url, headers)
    if status != 200:
        fail(link, f"GET {url} -> {status} {payload}")
    return payload

def pd_list(path, key, params=None):
    out, offset = [], 0
    while True:
        q = dict(params or {})
        q.update({"limit": 100, "offset": offset})
        qs = urllib.parse.urlencode(q, doseq=True)
        payload = must_get(f"{PD}{path}?{qs}", f"pagerduty list {path}")
        out.extend(payload[key])
        if not payload.get("more"):
            return out
        offset += len(payload[key])

def io_list_incidents():
    out, after = [], None
    while True:
        q = {"page_size": 250}
        if after:
            q["after"] = after
        payload = must_get(f"{IO}/v2/incidents?{urllib.parse.urlencode(q)}", "incidentio incidents list")
        out.extend(payload["incidents"])
        after = (payload.get("pagination_meta") or {}).get("after")
        if not after:
            return out

def slack_get(method, params=None):
    qs = urllib.parse.urlencode(params or {}, doseq=True)
    payload = must_get(f"{SLACK}/{method}?{qs}" if qs else f"{SLACK}/{method}", f"slack {method}")
    if not payload.get("ok", False):
        fail(f"slack {method}", json.dumps(payload))
    return payload

def slack_post(method, body_obj):
    status, payload = http("POST", f"{SLACK}/{method}", body_obj)
    if status != 200 or not (payload or {}).get("ok", False):
        fail(f"slack {method} write", f"{status} {payload}")
    return payload

def slack_users_all():
    out, cursor = [], None
    while True:
        params = {"limit": 200}
        if cursor:
            params["cursor"] = cursor
        payload = slack_get("users.list", params)
        out.extend(payload["members"])
        cursor = (payload.get("response_metadata") or {}).get("next_cursor") or None
        if not cursor:
            return out

def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

JIRA_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,9}-\d+)\b")

def main():
    writes = []

    ticket = must_get(f"{JIRA}/issue/{TRIGGER_TICKET}", "trigger ticket")
    tfields = ticket.get("fields", {})
    ticket_text = " ".join(
        str(x) for x in [tfields.get("summary", ""), tfields.get("description", "")]
    )
    if not ticket_text.strip():
        fail("trigger ticket text", "empty summary+description")

    services = pd_list("/services", "services")
    low = ticket_text.lower()
    named = [s for s in services if s["name"].lower() in low]
    if len(named) != 1:
        fail("unique service in ticket", f"matched {[s['name'] for s in named]}")
    svc = named[0]
    if len(svc.get("teams") or []) != 1:
        fail("trigger service single team", svc["name"])
    team_ref = svc["teams"][0]
    legacy_ep_ref = svc.get("escalation_policy") or fail("trigger service escalation policy", svc["name"])

    open_incidents = pd_list(
        "/incidents", "incidents",
        {"service_ids[]": svc["id"], "statuses[]": ["triggered", "acknowledged"], "date_range": "all"},
    )
    if len(open_incidents) != 1:
        fail("exactly one open incident on trigger service", f"found {len(open_incidents)}")
    trig_inc = open_incidents[0]

    log_entries = must_get(
        f"{PD}/incidents/{trig_inc['id']}/log_entries?limit=100",
        "trigger incident log entries",
    )["log_entries"]
    assigns = [e for e in log_entries if e.get("type") == "assign_log_entry"]
    if not assigns:
        fail("assign log entry on trigger incident")
    assignees = [a["id"] for e in assigns for a in (e.get("assignees") or [])]
    if not assignees:
        fail("assignee on assign log entry")
    assigned_user = must_get(f"{PD}/users/{assignees[0]}", "assigned user")["user"]

    legacy_ep = must_get(f"{PD}/escalation_policies/{legacy_ep_ref['id']}", "legacy policy")["escalation_policy"]
    legacy_sched_ids = [
        t["id"] for r in legacy_ep.get("escalation_rules", []) for t in r.get("targets", [])
        if t.get("type") == "schedule_reference"
    ]
    staffed = False
    legacy_scheds = []
    for sid in legacy_sched_ids:
        sched = must_get(f"{PD}/schedules/{sid}", "legacy schedule")["schedule"]
        legacy_scheds.append(sched)
        layers = sched.get("schedule_layers") or []
        if layers and (layers[0].get("users") or []):
            staffed = True
    if not staffed:
        fail("legacy rotation staffed (premise refutation)")
    if any(t["id"] == team_ref["id"] for t in assigned_user.get("teams", [])):
        fail("misroute evidence", "assigned user IS on the service team")

    team_services = pd_list("/services", "services", {"team_ids[]": team_ref["id"]})
    if svc["id"] not in [s["id"] for s in team_services]:
        fail("trigger service in team listing")
    sibling_eps = {
        s["escalation_policy"]["id"] for s in team_services
        if s["id"] != svc["id"] and s.get("escalation_policy")
    }
    if len(sibling_eps) != 1:
        fail("sibling services share one team policy", f"policies={sibling_eps}")
    team_ep_id = sibling_eps.pop()
    if team_ep_id == legacy_ep["id"]:
        fail("team policy differs from legacy policy")
    team_ep = must_get(f"{PD}/escalation_policies/{team_ep_id}", "team policy")["escalation_policy"]
    if team_ref["id"] not in [t["id"] for t in team_ep.get("teams", [])]:
        fail("team policy belongs to team")

    all_schedules = pd_list("/schedules", "schedules")
    all_eps = pd_list("/escalation_policies", "escalation_policies")
    targeted_schedule_ids = {
        t["id"] for ep in all_eps for r in ep.get("escalation_rules", [])
        for t in r.get("targets", []) if t.get("type") == "schedule_reference"
    }
    team_member_ids = {
        u["id"] for u in pd_list("/users", "users", {"team_ids[]": team_ref["id"]})
    }
    if not team_member_ids:
        fail("team has members")

    def layer_user_ids(schedule):
        return [
            e["user"]["id"] for layer in (schedule.get("schedule_layers") or [])
            for e in (layer.get("users") or []) if e.get("user")
        ]

    secondary_candidates = [
        s for s in all_schedules
        if s["id"] not in targeted_schedule_ids
        and layer_user_ids(s)
        and set(layer_user_ids(s)) <= team_member_ids
    ]
    if len(secondary_candidates) != 1:
        fail("unique unused team secondary schedule", f"candidates={[s['name'] for s in secondary_candidates]}")
    secondary_sched = secondary_candidates[0]

    worked_example_ep = None
    for ep in all_eps:
        if ep["id"] in (team_ep["id"], legacy_ep["id"]):
            continue
        rules = ep.get("escalation_rules", [])
        if len(rules) >= 2 and any(t.get("type") == "schedule_reference" for t in rules[1].get("targets", [])):
            worked_example_ep = ep
            break
    if worked_example_ep is None:
        fail("worked-example policy with a level-2 schedule target")

    team_service_ids = {s["id"] for s in team_services}
    disabled_team_services = [s for s in team_services if s.get("status") == "disabled"]
    ongoing_windows = pd_list("/maintenance_windows", "maintenance_windows", {"filter": "ongoing"})
    debris_windows = [
        w for w in ongoing_windows
        if any(ref["id"] in team_service_ids for ref in (w.get("services") or []))
    ]

    resolved_team_incidents = pd_list(
        "/incidents", "incidents",
        {"service_ids[]": sorted(team_service_ids), "statuses[]": "resolved", "date_range": "all"},
    )
    if not resolved_team_incidents:
        fail("historical resolved incidents on team services")
    storm_start = min(i["created_at"] for i in resolved_team_incidents)

    def day_number(iso):
        y, m, d = int(iso[0:4]), int(iso[5:7]), int(iso[8:10])
        import datetime
        return datetime.date(y, m, d).toordinal()

    storm_day = day_number(storm_start)
    io_incidents = io_list_incidents()
    linked = [
        i for i in io_incidents
        if abs(day_number(i["created_at"]) - storm_day) <= 2
    ]
    if len(linked) != 1:
        fail("unique incident.io incident at the storm date", f"found {len(linked)}")
    io_inc = linked[0]

    page_id = None
    for entry in io_inc.get("custom_field_entries", []):
        for value in entry.get("values", []):
            link = value.get("value_link", "")
            m = re.search(r"/pages/(\d+)", str(link))
            if m:
                page_id = m.group(1)
    if not page_id:
        fail("postmortem page link on incident.io incident")

    follow_ups = must_get(
        f"{IO}/v2/follow_ups?incident_id={io_inc['id']}", "incident.io follow-ups"
    )["follow_ups"]
    if len(follow_ups) < 4:
        fail("follow-ups on the postmortem incident", f"found {len(follow_ups)}")

    page = must_get(f"{CONF}/pages/{page_id}", "postmortem page")
    page_html = ((page.get("body") or {}).get("storage") or {}).get("value", "")
    rows = re.findall(r"<tr>(.*?)</tr>", page_html, flags=re.S)
    action_rows = []
    for row in rows:
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td>(.*?)</td>", row, flags=re.S)]
        if len(cells) >= 4:
            action_rows.append(cells)
    if len(action_rows) < 5:
        fail("postmortem action table rows", f"parsed {len(action_rows)}")

    page_keys = {c for cells in action_rows for c in [cells[3]] if JIRA_KEY_RE.fullmatch(c)}
    fu_keys = {
        m.group(1) for f in follow_ups for m in [JIRA_KEY_RE.search(str(f.get("description", "")))] if m
    }
    if not (fu_keys & page_keys):
        fail("follow-up ticket keys overlap page table keys")
    tracked_keys = sorted(page_keys | fu_keys)

    close_times, comments_by_key = {}, {}
    for key in tracked_keys:
        issue = must_get(f"{JIRA}/issue/{key}?expand=changelog", f"tracked ticket {key}")
        histories = (issue.get("changelog") or {}).get("histories", [])
        closes = [
            h["created"] for h in histories
            if any(it.get("field") == "status" and "done" in str(it.get("toString", "")).lower() for it in h.get("items", []))
        ]
        if closes:
            close_times[key] = max(closes)
        comment_block = ((issue.get("fields") or {}).get("comment") or {})
        comments_by_key[key] = len(comment_block.get("comments") or [])
    minute = lambda ts: str(ts)[:16]
    from collections import Counter
    cluster_minutes = Counter(minute(t) for t in close_times.values())
    bulk_minute, bulk_count = (cluster_minutes.most_common(1) or [(None, 0)])[0]
    if bulk_count < 3:
        fail("bulk-close cluster among tracked tickets", f"max shared minute count={bulk_count}")
    bulk_keys = {k for k, t in close_times.items() if minute(t) == bulk_minute}
    if any(comments_by_key[k] > 0 for k in bulk_keys):
        fail("bulk-closed tickets have no resolution comments")

    oncalls = pd_list("/oncalls", "oncalls", {"escalation_policy_ids[]": team_ep["id"]})
    level1 = [o for o in oncalls if o.get("escalation_level") == 1 and o.get("user")]
    if not level1:
        fail("current level-1 on-call for team policy")
    primary_user = must_get(f"{PD}/users/{level1[0]['user']['id']}", "primary on-call user")["user"]

    teams = pd_list("/teams", "teams")
    team = next((t for t in teams if t["id"] == team_ref["id"]), None) or fail("team record")
    groups = slack_get("usergroups.list")["usergroups"]

    def group_for(team_name):
        want = f"{slug(team_name)}-oncall"
        matches = [g for g in groups if g.get("handle") == want]
        return matches[0] if len(matches) == 1 else None

    team_group = group_for(team["name"]) or fail("slack usergroup for team", team["name"])

    wx_team_ref = (worked_example_ep.get("teams") or [None])[0]
    if wx_team_ref is None:
        fail("worked-example policy team")
    wx_team = next((t for t in teams if t["id"] == wx_team_ref["id"]), None) or fail("worked-example team record")
    wx_group = group_for(wx_team["name"]) or fail("worked-example slack usergroup")
    wx_oncalls = pd_list("/oncalls", "oncalls", {"escalation_policy_ids[]": worked_example_ep["id"]})
    wx_primary = next((o for o in wx_oncalls if o.get("escalation_level") == 1 and o.get("user")), None)
    if wx_primary is None:
        fail("worked-example level-1 on-call")
    wx_user = must_get(f"{PD}/users/{wx_primary['user']['id']}", "worked-example primary user")["user"]
    slack_users = slack_users_all()
    by_email = {str(u.get("profile", {}).get("email", "")).lower(): u for u in slack_users}
    wx_slack = by_email.get(str(wx_user.get("email", "")).lower()) or fail("worked-example slack user by email")
    if list(wx_group.get("users") or []) != [wx_slack["id"]]:
        fail("worked-example usergroup mirrors its primary on-call", f"{wx_group.get('users')} vs {wx_slack['id']}")

    primary_slack = by_email.get(str(primary_user.get("email", "")).lower()) or fail("primary on-call slack user by email")

    me = must_get(f"{PD}/users/me", "current pagerduty user")["user"]
    FROM = {"From": me["email"]}

    plan = []
    if legacy_ep["id"] != team_ep["id"]:
        plan.append(("repoint-service", svc["id"], team_ep["id"]))
    if len(team_ep.get("escalation_rules", [])) < 2:
        plan.append(("add-level2", team_ep["id"], secondary_sched["id"]))
    for s in disabled_team_services:
        plan.append(("enable-service", s["id"], None))
    for w in debris_windows:
        plan.append(("end-window", w["id"], None))
    current_group_users = list(team_group.get("users") or [])
    if current_group_users != [primary_slack["id"]]:
        plan.append(("sync-usergroup", team_group["id"], primary_slack["id"]))
    plan.append(("resolve-incident", trig_inc["id"], None))
    plan.append(("close-ticket", TRIGGER_TICKET, None))

    print("PLANNED WRITES:")
    for step in plan:
        print("  ", step)

    def pd_put(path, body_obj, link):
        status, payload = http("PUT", f"{PD}{path}", body_obj, headers=FROM)
        if status != 200:
            fail(f"write {link}", f"{status} {payload}")
        return payload

    for op, a, b in plan:
        if op == "repoint-service":
            pd_put(f"/services/{a}", {"service": {"escalation_policy": {"id": b, "type": "escalation_policy_reference"}}}, op)
            after = must_get(f"{PD}/services/{a}", "readback service ep")["service"]
            if after["escalation_policy"]["id"] != b:
                fail("readback: service repointed")
            writes.append((op, a, b))
        elif op == "add-level2":
            ep_now = must_get(f"{PD}/escalation_policies/{a}", "policy before edit")["escalation_policy"]
            rules = [
                {
                    "escalation_delay_in_minutes": r.get("escalation_delay_in_minutes", 30),
                    "targets": [{"id": t["id"], "type": t["type"]} for t in r.get("targets", [])],
                }
                for r in ep_now.get("escalation_rules", [])
            ]
            rules.append({"escalation_delay_in_minutes": 15, "targets": [{"id": b, "type": "schedule_reference"}]})
            pd_put(f"/escalation_policies/{a}", {"escalation_policy": {"escalation_rules": rules}}, op)
            after = must_get(f"{PD}/escalation_policies/{a}", "readback policy")["escalation_policy"]
            got = after.get("escalation_rules", [])
            if len(got) < 2 or not any(
                t["id"] == b for t in got[-1].get("targets", [])
            ):
                fail("readback: level-2 rule added")
            writes.append((op, a, b))
        elif op == "enable-service":
            pd_put(f"/services/{a}", {"service": {"status": "active"}}, op)
            after = must_get(f"{PD}/services/{a}", "readback service status")["service"]
            if after.get("status") != "active":
                fail("readback: service enabled")
            writes.append((op, a, None))
        elif op == "end-window":
            status, payload = http("DELETE", f"{PD}/maintenance_windows/{a}", headers=FROM)
            if status != 204:
                fail("write end-window", f"{status} {payload}")
            still_ongoing = pd_list("/maintenance_windows", "maintenance_windows", {"filter": "ongoing"})
            if any(w["id"] == a for w in still_ongoing):
                fail("readback: window ended")
            writes.append((op, a, None))
        elif op == "sync-usergroup":
            slack_post("usergroups.users.update", {"usergroup": a, "users": [b]})
            after = slack_get("usergroups.users.list", {"usergroup": a})["users"]
            if list(after) != [b]:
                fail("readback: usergroup synced", f"{after}")
            writes.append((op, a, b))
        elif op == "resolve-incident":
            pd_put(f"/incidents/{a}", {"incident": {"status": "resolved"}}, op)
            after = must_get(f"{PD}/incidents/{a}", "readback incident")["incident"]
            if after.get("status") != "resolved":
                fail("readback: trigger incident resolved")
            writes.append((op, a, None))
        elif op == "close-ticket":
            transitions = must_get(f"{JIRA}/issue/{a}/transitions", "ticket transitions")["transitions"]
            done = next(
                (t for t in transitions if str(((t.get("to") or {}).get("statusCategory") or {}).get("key")) == "done"),
                None,
            )
            if done is None:
                fail("done-category transition available")
            status, payload = http("POST", f"{JIRA}/issue/{a}/transitions", {"transition": {"id": done["id"]}})
            if status != 204:
                fail("write ticket transition", f"{status} {payload}")
            http(
                "POST",
                f"{JIRA}/issue/{a}/comment",
                {"body": "Paging chain repaired; suppression debris cleared; on-call handle re-synced. Root cause: tracker consolidation auto-closed the outstanding postmortem remediation tickets and the follow-up sync recorded them complete without the work being done."},
            )
            after = must_get(f"{JIRA}/issue/{a}", "readback ticket")
            cat = str((((after.get("fields") or {}).get("status") or {}).get("statusCategory") or {}).get("key"))
            if cat != "done":
                fail("readback: ticket done", cat)
            writes.append((op, a, None))

    print("EXECUTED WRITES:")
    for w in writes:
        print("  ", w)
    print("ORACLE COMPLETE: 0 readback mismatches")

if __name__ == "__main__":
    main()
