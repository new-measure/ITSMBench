#!/usr/bin/env python3
import json
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

PRIMARY_NAME = "Priya Nair"
WINDOW_START = "2025-06-06T00:00:00Z"
WINDOW_END = "2025-06-11T00:00:00Z"

PD = "pagerduty.local.mock"
OKTA = "okta.local.mock"
BAMBOO = "bamboohr.local.mock"
IO = "incidentio.local.mock"

def _http(method, host, path, query=None, body=None):
    url = "http://%s:8080%s" % (host, path)
    if query:
        url += "?" + urlencode(query, doseq=True)
    data = json.dumps(body).encode() if body is not None else None
    req = Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except HTTPError as e:
        raw = e.read()
        try:
            parsed = json.loads(raw) if raw else None
        except Exception:
            parsed = raw.decode("utf-8", "replace")
        return e.code, parsed

def die(msg):
    print("ORACLE-FAIL: " + msg)
    sys.exit(2)

def pd_all(path, key, query=None):
    out, offset = [], 0
    while True:
        q = dict(query or {})
        q.update({"limit": 100, "offset": offset})
        st, data = _http("GET", PD, path, q)
        if st != 200:
            die("PagerDuty GET %s -> %s %s" % (path, st, data))
        out.extend(data.get(key, []))
        if not data.get("more"):
            break
        offset += data.get("limit", 100)
    return out

def okta_all(path, query=None):
    out, after = [], None
    while True:
        q = dict(query or {})
        q["limit"] = 200
        if after:
            q["after"] = after
        st, data = _http("GET", OKTA, path, q)
        if st != 200:
            die("Okta GET %s -> %s %s" % (path, st, data))
        if not isinstance(data, list):
            die("Okta GET %s did not return a list" % path)
        out.extend(data)
        if len(data) < 200:
            break
        after = data[-1]["id"]
    return out

def io_all(path, key, query=None):
    out, after = [], None
    while True:
        q = dict(query or {})
        q["page_size"] = 100
        if after:
            q["after"] = after
        st, data = _http("GET", IO, path, q)
        if st != 200:
            die("incident.io GET %s -> %s %s" % (path, st, data))
        out.extend(data.get(key, []))
        after = (data.get("pagination_meta") or {}).get("after")
        if not after:
            break
    return out

def parse_dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)

def window_days(start_iso, end_iso):
    start, end = parse_dt(start_iso), parse_dt(end_iso)
    days = []
    d = start
    while d < end:
        nxt = d + timedelta(days=1)
        days.append((d.date().isoformat(), d, min(nxt, end)))
        d = nxt
    return days

def pto_covers_day(pto_start, pto_end, day_str):
    return str(pto_start)[:10] <= day_str <= str(pto_end)[:10]

def approved(status):
    if isinstance(status, dict):
        status = status.get("status")
    return str(status).lower() == "approved"

def main():
    days = window_days(WINDOW_START, WINDOW_END)
    day_strs = [d[0] for d in days]

    pd_users = pd_all("/users", "users")
    primary = [u for u in pd_users if str(u.get("name", "")).strip().lower() == PRIMARY_NAME.lower()]
    if len(primary) != 1:
        die("expected exactly one PagerDuty user named %r, found %d" % (PRIMARY_NAME, len(primary)))
    primary = primary[0]
    email_by_pd_id = {u["id"]: str(u.get("email", "")).lower() for u in pd_users}
    pd_id_by_email = {str(u.get("email", "")).lower(): u["id"] for u in pd_users}

    schedules = pd_all("/schedules", "schedules")

    def layer_user_ids(sch):
        ids = []
        for layer in sch.get("schedule_layers") or []:
            for entry in layer.get("users") or []:
                u = entry.get("user") or {}
                if u.get("id"):
                    ids.append(u["id"])
        return ids

    targets = [s for s in schedules if primary["id"] in layer_user_ids(s)]
    if len(targets) != 1:
        die("expected primary on exactly one schedule layer, found %d" % len(targets))
    target = targets[0]
    base_rotation_emails = {email_by_pd_id.get(uid) for uid in layer_user_ids(target)}
    base_rotation_emails.discard("")
    base_rotation_emails.discard(None)
    if not base_rotation_emails:
        die("target schedule has no resolvable base-rotation emails")

    groups = okta_all("/api/v1/groups")
    qual_group = None
    for g in groups:
        members = okta_all("/api/v1/groups/%s/users" % g["id"])
        member_emails = {str((m.get("profile") or {}).get("email", "")).lower() for m in members}
        if base_rotation_emails <= member_emails:
            if qual_group is not None:
                die("qualification group is not unique (multiple groups superset the rotation)")
            qual_group = (g, member_emails)
    if qual_group is None:
        die("no Okta group is a superset of the base rotation")
    qualified_emails = {e for e in qual_group[1] if e}
    print("qualified pool (%d): %s" % (len(qualified_emails), sorted(qualified_emails)))

    qualified_emails = {e for e in qualified_emails if e in pd_id_by_email}

    st, directory = _http("GET", BAMBOO, "/api/v1/employees/directory")
    if st != 200:
        die("BambooHR directory -> %s %s" % (st, directory))
    empid_by_email = {}
    for emp in directory.get("employees", []):
        we = str(emp.get("workEmail", "")).lower()
        if we:
            empid_by_email[we] = str(emp["id"])

    pto_days = {e: set() for e in qualified_emails}
    for email in qualified_emails:
        empid = empid_by_email.get(email)
        if not empid:
            die("qualified engineer %s has no BambooHR employee record" % email)
        st, reqs = _http("GET", BAMBOO, "/api/v1/time_off/requests", {"employeeId": empid})
        if st != 200:
            die("BambooHR time_off/requests employeeId=%s -> %s %s" % (empid, st, reqs))
        for r in reqs or []:
            if not approved(r.get("status")):
                continue
            for ds in day_strs:
                if pto_covers_day(r.get("start"), r.get("end"), ds):
                    pto_days[email].add(ds)

    incidents = io_all("/v2/incidents", "incidents")
    preserved_emails = set()
    for inc in incidents:
        status = ((inc.get("incident_status") or {}).get("category") or "").lower()
        sev = ((inc.get("severity") or {}).get("name") or "").lower()
        active = status in ("triage", "live", "active")
        critical = "critical" in sev or "sev1" in sev or "sev-1" in sev
        if not (active and critical):
            continue
        for a in inc.get("incident_role_assignments") or []:
            role = ((a.get("role") or {}).get("name") or "").lower()
            if "lead" in role and a.get("assignee"):
                preserved_emails.add(str(a["assignee"].get("email", "")).lower())
    print("preserved (active-critical leads): %s" % sorted(e for e in preserved_emails if e))

    def feasible(day_str):
        out = []
        for e in sorted(qualified_emails):
            if e in preserved_emails:
                continue
            if day_str in pto_days[e]:
                continue
            out.append(e)
        return out

    assignment = {}
    for ds in day_strs:
        feas = feasible(ds)
        if not feas:
            die("no feasible engineer for day %s" % ds)
        assignment[ds] = feas[0]
    print("assignment: %s" % assignment)

    overrides = []
    for (ds, bstart, bend) in days:
        email = assignment[ds]
        overrides.append({
            "user": {"id": pd_id_by_email[email], "type": "user_reference"},
            "start": bstart.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": bend.strftime("%Y-%m-%dT%H:%M:%SZ"),
        })

    st, res = _http("POST", PD, "/schedules/%s/overrides" % target["id"], body={"overrides": overrides})
    if st not in (200, 201):
        die("override POST -> %s %s" % (st, res))
    for row in res:
        if row.get("status") not in (200, 201):
            die("override row failed: %s" % row)
    print("WRITE: created %d overrides on schedule %s (%s)" % (len(overrides), target["id"], target.get("name")))
    for o in overrides:
        print("  WRITE override day user=%s %s..%s" % (
            email_by_pd_id.get(o["user"]["id"]), o["start"], o["end"]))

    st, back = _http("GET", PD, "/schedules/%s/overrides" % target["id"],
                     {"since": WINDOW_START, "until": WINDOW_END})
    if st != 200:
        die("override readback -> %s %s" % (st, back))
    got = back.get("overrides", [])
    allowed = {e for e in qualified_emails
               if e not in preserved_emails and not set(day_strs) <= pto_days[e]}
    for (ds, bstart, bend) in days:
        covered = any(parse_dt(o["start"]) <= bstart and parse_dt(o["end"]) >= bend for o in got)
        if not covered:
            die("readback: day %s not covered" % ds)
    rostered_emails = set()
    for o in got:
        e = email_by_pd_id.get((o.get("user") or {}).get("id"))
        rostered_emails.add(e)
        if e not in allowed:
            die("readback: override user %s not in allowed set %s" % (e, sorted(allowed)))
        for (ds, bstart, bend) in days:
            touches = parse_dt(o["start"]) < bend and parse_dt(o["end"]) > bstart
            if touches and ds in pto_days.get(e, set()):
                die("readback: override for %s overlaps their PTO on %s" % (e, ds))
    print("OK: all %d days covered by qualified/available/non-preserved engineers; readback clean." % len(days))

    policies = pd_all("/escalation_policies", "escalation_policies")
    misrouted = [p for p in policies
                 if any(t.get("type") == "user_reference" and t.get("id") == primary["id"]
                        for r in (p.get("escalation_rules") or []) for t in (r.get("targets") or []))]
    if len(misrouted) != 1:
        die("expected exactly one escalation policy routing to the on-leave primary, found %d" % len(misrouted))
    policy = misrouted[0]
    new_rules = []
    for r in (policy.get("escalation_rules") or []):
        new_targets = []
        for t in (r.get("targets") or []):
            if t.get("type") == "user_reference" and t.get("id") == primary["id"]:
                new_targets.append({"id": target["id"], "type": "schedule_reference"})
            else:
                new_targets.append({"id": t["id"], "type": t["type"]})
        new_rules.append({"escalation_delay_in_minutes": r.get("escalation_delay_in_minutes", 30),
                          "targets": new_targets})
    st, res = _http("PUT", PD, "/escalation_policies/%s" % policy["id"],
                    body={"escalation_policy": {"escalation_rules": new_rules}})
    if st not in (200, 201):
        die("escalation policy repoint -> %s %s" % (st, res))
    print("WRITE: repointed escalation policy %s to schedule %s" % (policy["id"], target["id"]))

    st, back = _http("GET", PD, "/escalation_policies/%s" % policy["id"])
    if st != 200:
        die("policy readback -> %s" % st)
    tset = [(t.get("type"), t.get("id")) for r in back["escalation_policy"]["escalation_rules"] for t in r["targets"]]
    if ("schedule_reference", target["id"]) not in tset:
        die("readback: policy does not route to the covered schedule: %s" % tset)
    if ("user_reference", primary["id"]) in tset:
        die("readback: policy still routes to the on-leave primary")
    print("OK: Payments-DB service now pages the covered on-call schedule.")

if __name__ == "__main__":
    main()
