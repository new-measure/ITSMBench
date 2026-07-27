#!/usr/bin/env python3
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

SF = "http://salesforce.local.mock:8080/services/data/v67.0"
HS = "http://hubspot.local.mock:8080"
PD = "http://pagerduty.local.mock:8080"
SN = "http://servicenow.local.mock:8080/api/now/table"
FD = "http://freshdesk.local.mock:8080/api/v2"
SL = "http://slack.local.mock:8080/api"

FAILURES = []
DISCOVERED = []

def call(method, url, body=None):
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {url} -> HTTP {e.code}: {e.read().decode()[:300]}")
    return json.loads(raw) if raw else None

def check(ok, what):
    tag = "OK " if ok else "READBACK-MISMATCH"
    print(f"[{tag}] {what}")
    if not ok:
        FAILURES.append(what)

def found(what):
    DISCOVERED.append(what)
    print(f"[FOUND] {what}")

def _norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())

def _email_local(email):
    return _norm(email).split("@")[0] if email else ""

def subject_matches(subject, name=None, email=None):
    full = _norm(subject["name"])
    dotted = full.replace(" ", ".")
    if name and _norm(name) == full:
        return True
    if email and _email_local(email) in (dotted, full.replace(" ", "")):
        return True
    return False

def match_subject(subjects, name=None, email=None):
    for s in subjects:
        if subject_matches(s, name, email):
            return s
    return None

def _numbered_subjects(desc):
    subjects = []
    for line in (desc or "").splitlines():
        m = re.match(r"\s*\d+\)\s*(.+)", line)
        if not m:
            continue
        name = m.group(1).split(" - ")[0].strip()
        subjects.append({"name": name, "role_change": "CHANGED ROLES" in m.group(1).upper()})
    return subjects

def _is_closed(t):
    return t.get("status") in (4, 5, "4", "5")

def read_ticket():
    tickets = call("GET", f"{FD}/tickets")
    open_with_list = [t for t in tickets
                      if not _is_closed(t) and len(_numbered_subjects(t.get("description_text"))) >= 2]
    if not open_with_list:
        raise RuntimeError("could not discover an OPEN offboarding/restructure ticket with a people list")
    ticket = open_with_list[0]
    found(f"freshdesk ticket #{ticket['id']}: {ticket['subject']}")

    precedent = next((t for t in tickets
                      if _is_closed(t) and "offboarding" in _norm(t.get("subject"))
                      and t.get("id") != ticket.get("id")), None)
    if precedent is not None:
        found(f"precedent (CLOSED) ticket #{precedent['id']}: {precedent['subject']} -- "
              f"records reassigning owned records and disabling/handing-over a leaver's automation")

    subjects = _numbered_subjects(ticket.get("description_text"))
    for s in subjects:
        found(f"subject: {s['name']}" + (" (ROLE CHANGE - identity stays)" if s["role_change"] else " (leaver)"))
    return subjects

def soql(q):
    return call("GET", f"{SF}/query?q={urllib.parse.quote(q)}")["records"]

def do_salesforce(subjects, leavers):
    users = soql("SELECT Id, Name, Email, IsActive, Title FROM User")
    leaver_users = [u for u in users if match_subject(leavers, u.get("Name"), u.get("Email"))]
    for u in leaver_users:
        found(f"salesforce identity {u['Id']} ({u['Name']} <{u['Email']}>)")
    pool = [u for u in users
            if u.get("IsActive") and not match_subject(subjects, u.get("Name"), u.get("Email"))]
    if not pool:
        raise RuntimeError("no active non-subject Salesforce user to reassign ownership to")

    def prefer(*terms):
        for term_set in terms:
            hit = next((u for u in pool if all(t in _norm(u.get("Title")) for t in term_set)), None)
            if hit:
                return hit
        return pool[0]

    sales_mgr = prefer(("sales", "manager"), ("manager",))
    support_mgr = prefer(("support", "manager"), ("manager",))
    leaver_ids = {u["Id"] for u in leaver_users}
    for sobject, target in (("Account", sales_mgr), ("Opportunity", sales_mgr), ("Case", support_mgr)):
        for rec in soql(f"SELECT Id, Name, OwnerId FROM {sobject}"):
            if rec.get("OwnerId") in leaver_ids:
                found(f"salesforce {sobject} {rec['Id']} owned by leaver -> reassign to {target['Name']}")
                call("PATCH", f"{SF}/sobjects/{sobject}/{rec['Id']}", {"OwnerId": target["Id"]})
                back = call("GET", f"{SF}/sobjects/{sobject}/{rec['Id']}")
                check(back.get("OwnerId") == target["Id"], f"salesforce {sobject} {rec['Id']} owner -> {target['Id']}")
    for u in leaver_users:
        call("PATCH", f"{SF}/sobjects/User/{u['Id']}", {"IsActive": False})
        back = call("GET", f"{SF}/sobjects/User/{u['Id']}")
        check(back.get("IsActive") is False, f"salesforce User {u['Id']} IsActive=false")

def do_hubspot(subjects, leavers):
    deals = call("GET", f"{HS}/crm/v3/objects/0-3")["results"]

    def owner_subject(owner_id):
        tokens = set(re.split(r"[^a-z0-9]+", _norm(owner_id)))
        for s in subjects:
            name_tokens = set(_norm(s["name"]).split())
            if tokens & name_tokens:
                return s
        return None

    target = next((str((d.get("properties") or {}).get("hubspot_owner_id"))
                   for d in deals
                   if (d.get("properties") or {}).get("hubspot_owner_id")
                   and owner_subject((d["properties"]).get("hubspot_owner_id")) is None), None)
    for d in deals:
        owner = (d.get("properties") or {}).get("hubspot_owner_id") or ""
        s = owner_subject(owner)
        if s and not s["role_change"]:
            if target is None:
                raise RuntimeError("no active HubSpot owner discovered to reassign deals to")
            found(f"hubspot deal {d['id']} owned by leaver owner '{owner}' -> reassign to '{target}'")
            call("PATCH", f"{HS}/crm/v3/objects/0-3/{d['id']}", {"properties": {"hubspot_owner_id": target}})
            back = call("GET", f"{HS}/crm/v3/objects/0-3/{d['id']}")
            check((back.get("properties") or {}).get("hubspot_owner_id") == target,
                  f"hubspot deal {d['id']} owner -> {target}")

def do_pagerduty(subjects):
    users = call("GET", f"{PD}/users")["users"]
    subject_users = {u["id"]: u for u in users if match_subject(subjects, u.get("name"), u.get("email"))}
    active = [u for u in users if u["id"] not in subject_users]
    for u in subject_users.values():
        found(f"pagerduty user {u['id']} ({u['name']})")
    if not active:
        raise RuntimeError("no active PagerDuty responder available for backfill")

    def backfill(team_refs):
        team_ids = {t.get("id") for t in (team_refs or [])}
        for u in active:
            if team_ids & {t.get("id") for t in (u.get("teams") or [])}:
                return u
        return active[0]

    for ep in call("GET", f"{PD}/escalation_policies")["escalation_policies"]:
        changed, new_rules = False, []
        for rule in ep.get("escalation_rules", []):
            targets = [t for t in rule.get("targets", []) if t.get("id") not in subject_users]
            if len(targets) != len(rule.get("targets", [])):
                changed = True
                if not targets:
                    repl = backfill(ep.get("teams"))
                    found(f"pagerduty EP {ep['id']} rule would EMPTY -> backfill {repl['name']}")
                    targets = [{"id": repl["id"], "type": "user_reference"}]
            new_rules.append({"id": rule.get("id"),
                              "escalation_delay_in_minutes": rule.get("escalation_delay_in_minutes", 30),
                              "targets": targets})
        if changed:
            found(f"pagerduty escalation policy {ep['id']} ({ep['name']}) references a subject")
            call("PUT", f"{PD}/escalation_policies/{ep['id']}",
                 {"escalation_policy": {"escalation_rules": new_rules}})
            back = call("GET", f"{PD}/escalation_policies/{ep['id']}")["escalation_policy"]
            ids = [t.get("id") for r in back.get("escalation_rules", []) for t in r.get("targets", [])]
            check(ids and not (set(ids) & set(subject_users)),
                  f"pagerduty EP {ep['id']} has no subject targets and non-empty rules")

    for sch_stub in call("GET", f"{PD}/schedules")["schedules"]:
        sch = call("GET", f"{PD}/schedules/{sch_stub['id']}")["schedule"]
        changed, new_layers = False, []
        for layer in sch.get("schedule_layers", []):
            entries = [e for e in layer.get("users", []) if (e.get("user") or {}).get("id") not in subject_users]
            if len(entries) != len(layer.get("users", [])):
                changed = True
                if not entries:
                    removed = [e for e in layer.get("users", []) if (e.get("user") or {}).get("id") in subject_users]
                    repl = backfill((subject_users.get(removed[0]["user"]["id"]) or {}).get("teams")) if removed else active[0]
                    found(f"pagerduty schedule {sch['id']} layer would EMPTY -> backfill {repl['name']}")
                    entries = [{"user": {"id": repl["id"], "type": "user_reference"}}]
            new_layers.append({"id": layer.get("id"), "name": layer.get("name"),
                               "start": layer.get("start"),
                               "rotation_virtual_start": layer.get("rotation_virtual_start"),
                               "rotation_turn_length_seconds": layer.get("rotation_turn_length_seconds"),
                               "users": entries})
        if changed:
            found(f"pagerduty schedule {sch['id']} ({sch['name']}) references a subject")
            call("PUT", f"{PD}/schedules/{sch['id']}", {"schedule": {"schedule_layers": new_layers}})
            back = call("GET", f"{PD}/schedules/{sch['id']}")["schedule"]
            ids = [(e.get("user") or {}).get("id") for l in back.get("schedule_layers", []) for e in l.get("users", [])]
            check(ids and not (set(ids) & set(subject_users)),
                  f"pagerduty schedule {sch['id']} has no subject layer users and non-empty layers")

        q = urllib.parse.urlencode({"since": "2020-01-01T00:00:00Z", "until": "2030-01-01T00:00:00Z"})
        for ovr in call("GET", f"{PD}/schedules/{sch['id']}/overrides?{q}")["overrides"]:
            if (ovr.get("user") or {}).get("id") in subject_users:
                found(f"pagerduty override {ovr['id']} on schedule {sch['id']} for a subject")
                call("DELETE", f"{PD}/schedules/{sch['id']}/overrides/{ovr['id']}")
                back = call("GET", f"{PD}/schedules/{sch['id']}/overrides?{q}")["overrides"]
                check(all(o.get("id") != ovr["id"] for o in back),
                      f"pagerduty override {ovr['id']} removed")

    for uid, u in subject_users.items():
        for team in list(u.get("teams") or []):
            found(f"pagerduty user {uid} is a member of team {team.get('id')} ({team.get('summary')})")
            call("DELETE", f"{PD}/teams/{team['id']}/users/{uid}")
            back = call("GET", f"{PD}/teams/{team['id']}/members")["members"]
            check(all((m.get("user") or {}).get("id") != uid for m in back),
                  f"pagerduty user {uid} removed from team {team['id']}")

def sn_rows(table):
    return call("GET", f"{SN}/{table}").get("result", [])

def do_servicenow(subjects, leavers, role_changers):
    users = sn_rows("sys_user")
    leaver_users = [u for u in users if match_subject(leavers, u.get("name"), u.get("email"))]
    rc_users = [u for u in users if match_subject(role_changers, u.get("name"), u.get("email"))]
    for u in leaver_users:
        found(f"servicenow user {u['sys_id']} ({u.get('user_name')})")
        call("PATCH", f"{SN}/sys_user/{u['sys_id']}", {"active": False})
        back = call("GET", f"{SN}/sys_user/{u['sys_id']}")["result"]
        check(back.get("active") in (False, "false"), f"servicenow user {u.get('user_name')} active=false")

    leaver_ids = {u["sys_id"] for u in leaver_users}
    rc_ids = {u["sys_id"] for u in rc_users}
    for row in sn_rows("sys_user_has_role"):
        uid, role = str(row.get("user")), str(row.get("role"))
        if uid in leaver_ids or (uid in rc_ids and role == "admin"):
            found(f"servicenow role grant {row['sys_id']} ({role}) held by subject {uid}")
            call("DELETE", f"{SN}/sys_user_has_role/{row['sys_id']}")
    remaining = {(str(r.get("user")), str(r.get("role"))) for r in sn_rows("sys_user_has_role")}
    check(not any(u in leaver_ids for u, _ in remaining), "servicenow: no role grants left on leavers")
    check(not any(u in rc_ids and role == "admin" for u, role in remaining),
          "servicenow: role-changer's admin grant removed")

    leaver_usernames = {str(u.get("user_name")) for u in leaver_users}
    leaver_identities = leaver_ids | leaver_usernames
    lineage_fields = ("owned_by", "run_as", "managed_by", "u_owner", "u_owned_by", "assigned_to")

    def created_or_run_by_leaver(row):
        if str(row.get("sys_created_by")) in leaver_usernames:
            return True
        return any(str(row.get(f)) in leaver_identities for f in lineage_fields if row.get(f))

    catalogue = [str(r.get("name")) for r in sn_rows("sys_db_object")]
    meta = {"sys_db_object", "sys_dictionary", "sys_choice", "sys_documentation",
            "sys_ui_section", "sys_ui_element", "sys_security_acl"}
    if "sysauto_script" not in catalogue:
        raise RuntimeError("table catalogue (sys_db_object) does not expose the seeded scheduled-job "
                           "table -- an agent cannot discover it; provider catalogue fix missing")
    handled = leaver_ids
    for table in catalogue:
        if table in meta:
            continue
        try:
            rows = sn_rows(table)
        except RuntimeError:
            continue
        for row in rows:
            if not created_or_run_by_leaver(row):
                continue
            if str(row.get("sys_id")) in handled or "active" not in row:
                continue
            if row.get("active") in (True, "true", "1", 1):
                found(f"servicenow {table} row {row['sys_id']} ({row.get('name') or row.get('user_name')}) "
                      f"created/owned/run by a leaver (created_by={row.get('sys_created_by')}, "
                      f"owned_by={row.get('owned_by')}, run_as={row.get('run_as')}) and still ACTIVE -> disable")
                call("PATCH", f"{SN}/{table}/{row['sys_id']}", {"active": False})
                back = call("GET", f"{SN}/{table}/{row['sys_id']}")["result"]
                check(back.get("active") in (False, "false"),
                      f"servicenow {table}/{row['sys_id']} active=false (dangling authority)")

def do_freshdesk(leavers):
    for agent in call("GET", f"{FD}/agents"):
        contact = agent.get("contact") or {}
        if match_subject(leavers, contact.get("name"), contact.get("email")):
            found(f"freshdesk agent {agent['id']} ({contact.get('name')})")
            call("DELETE", f"{FD}/agents/{agent['id']}")
    remaining = call("GET", f"{FD}/agents")
    check(not any(match_subject(leavers, (a.get("contact") or {}).get("name"),
                                (a.get("contact") or {}).get("email")) for a in remaining),
          "freshdesk: no leaver agent accounts remain")

def do_slack(leavers):
    members = call("GET", f"{SL}/users.list")["members"]
    for m in members:
        profile = m.get("profile") or {}
        if m.get("deleted"):
            continue
        if match_subject(leavers, m.get("real_name") or profile.get("real_name"), profile.get("email")):
            found(f"slack user {m['id']} ({m.get('real_name')})" + (" [guest]" if m.get("is_restricted") else ""))
            call("POST", f"{SL}/admin.users.remove", {"team_id": "T000001", "user_id": m["id"]})
            back = call("GET", f"{SL}/users.info?user={m['id']}")["user"]
            check(back.get("deleted") is True, f"slack user {m['id']} deleted=true")

def main():
    subjects = read_ticket()
    leavers = [s for s in subjects if not s["role_change"]]
    role_changers = [s for s in subjects if s["role_change"]]
    do_salesforce(subjects, leavers)
    do_hubspot(subjects, leavers)
    do_pagerduty(subjects)
    do_servicenow(subjects, leavers, role_changers)
    do_freshdesk(leavers)
    do_slack(leavers)
    print(f"\noracle discovered {len(DISCOVERED)} targets cold (no seed IDs used)")
    if FAILURES:
        print(f"ORACLE FAILED: {len(FAILURES)} readback mismatch(es):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("ORACLE COMPLETE: zero readback mismatches")

if __name__ == "__main__":
    main()
