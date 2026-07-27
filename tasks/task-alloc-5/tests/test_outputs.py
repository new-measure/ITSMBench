#!/usr/bin/env python3
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

PRIMARY_NAME = "Priya Nair"
WINDOW_START = "2025-06-06T00:00:00Z"
WINDOW_END = "2025-06-11T00:00:00Z"

DOMAIN = "nimbuspay.com"
QUAL_EMAILS = {
    "priya.nair", "marcus.feldt", "devon.ross", "sofia.alvarez", "kenji.watts", "hannah.cole"}
BASE_ROTATION_EMAILS = {"priya.nair", "marcus.feldt", "devon.ross", "sofia.alvarez"}
CAST_APPROVED_PTO = {
    "priya.nair": {("2025-06-06", "2025-06-10")},
    "marcus.feldt": {("2025-06-08", "2025-06-10"), ("2025-07-01", "2025-07-03")},
    "sofia.alvarez": {("2025-06-06", "2025-06-08")},
    "kenji.watts": {("2025-06-06", "2025-06-06")},
    "hannah.cole": {("2025-06-06", "2025-06-10")},
}
INCIDENT_REF = "INC-2041"
INCIDENT_LEAD_EMAIL = "devon.ross@" + DOMAIN

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
            return e.code, (json.loads(raw) if raw else None)
        except Exception:
            return e.code, raw.decode("utf-8", "replace")

def pd_all(path, key, query=None):
    out, offset = [], 0
    while True:
        q = dict(query or {}); q.update({"limit": 100, "offset": offset})
        st, data = _http("GET", PD, path, q)
        assert st == 200, "PD GET %s -> %s %s" % (path, st, data)
        out.extend(data.get(key, []))
        if not data.get("more"):
            break
        offset += data.get("limit", 100)
    return out

def okta_all(path, query=None):
    out, after = [], None
    while True:
        q = dict(query or {}); q["limit"] = 200
        if after:
            q["after"] = after
        st, data = _http("GET", OKTA, path, q)
        assert st == 200 and isinstance(data, list), "Okta GET %s -> %s %s" % (path, st, data)
        out.extend(data)
        if len(data) < 200:
            break
        after = data[-1]["id"]
    return out

def io_all(path, key, query=None):
    out, after = [], None
    while True:
        q = dict(query or {}); q["page_size"] = 100
        if after:
            q["after"] = after
        st, data = _http("GET", IO, path, q)
        assert st == 200, "IO GET %s -> %s %s" % (path, st, data)
        out.extend(data.get(key, []))
        after = (data.get("pagination_meta") or {}).get("after")
        if not after:
            break
    return out

def parse_dt(s):
    return datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(timezone.utc)

def window_days():
    start, end = parse_dt(WINDOW_START), parse_dt(WINDOW_END)
    days, d = [], start
    while d < end:
        nxt = d + timedelta(days=1)
        days.append((d.date().isoformat(), d, min(nxt, end)))
        d = nxt
    return days

def pto_covers(start, end, day):
    return str(start)[:10] <= day <= str(end)[:10]

def approved(status):
    if isinstance(status, dict):
        status = status.get("status")
    return str(status).lower() == "approved"

class World:
    _cache = None

    @classmethod
    def load(cls):
        if cls._cache is not None:
            return cls._cache
        pd_users = pd_all("/users", "users")
        email_by_pd = {u["id"]: str(u.get("email", "")).lower() for u in pd_users}
        pd_by_email = {str(u.get("email", "")).lower(): u["id"] for u in pd_users}

        schedules = pd_all("/schedules", "schedules")

        def layer_ids(s):
            return [e["user"]["id"] for l in (s.get("schedule_layers") or [])
                    for e in (l.get("users") or []) if e.get("user")]

        prim = [u for u in pd_users if str(u.get("name", "")).strip().lower() == PRIMARY_NAME.lower()]
        assert len(prim) == 1, "primary not uniquely resolvable"
        targets = [s for s in schedules if prim[0]["id"] in layer_ids(s)]
        assert len(targets) == 1, "target schedule not uniquely resolvable"
        target = targets[0]
        base_emails = {email_by_pd[i] for i in layer_ids(target)}

        groups = okta_all("/api/v1/groups")
        qual = None
        for g in groups:
            members = okta_all("/api/v1/groups/%s/users" % g["id"])
            memails = {str((m.get("profile") or {}).get("email", "")).lower() for m in members}
            if base_emails <= memails:
                qual = (g, memails)
                break
        assert qual is not None, "qualification group not found"
        qualified = {e for e in qual[1] if e in pd_by_email}

        st, directory = _http("GET", BAMBOO, "/api/v1/employees/directory")
        assert st == 200
        empid_by_email = {str(e.get("workEmail", "")).lower(): str(e["id"])
                          for e in directory.get("employees", []) if e.get("workEmail")}
        pto_days = {}
        for email in qualified | {p for p in empid_by_email if p.split("@")[0] in QUAL_EMAILS}:
            eid = empid_by_email.get(email)
            if not eid:
                continue
            st, reqs = _http("GET", BAMBOO, "/api/v1/time_off/requests", {"employeeId": eid})
            assert st == 200
            ds = set()
            for r in reqs or []:
                if approved(r.get("status")):
                    for (day, _, _) in window_days():
                        if pto_covers(r.get("start"), r.get("end"), day):
                            ds.add(day)
            pto_days[email] = ds

        incidents = io_all("/v2/incidents", "incidents")
        preserved = set()
        for inc in incidents:
            cat = ((inc.get("incident_status") or {}).get("category") or "").lower()
            sev = ((inc.get("severity") or {}).get("name") or "").lower()
            if cat in ("triage", "live", "active") and "critical" in sev:
                for a in inc.get("incident_role_assignments") or []:
                    if "lead" in ((a.get("role") or {}).get("name") or "").lower() and a.get("assignee"):
                        preserved.add(str(a["assignee"].get("email", "")).lower())

        full_window = {day for (day, _, _) in window_days()}
        allowed = {e for e in qualified
                   if e not in preserved and pto_days.get(e, set()) != full_window}

        st, ov = _http("GET", PD, "/schedules/%s/overrides" % target["id"],
                       {"since": WINDOW_START, "until": WINDOW_END})
        assert st == 200, "override readback -> %s %s" % (st, ov)
        overrides = ov.get("overrides", [])

        st, svcs = _http("GET", PD, "/services", {"limit": 100})
        assert st == 200
        svc = next((s for s in svcs.get("services", []) if s.get("name") == "Payments Core DB"), None)
        assert svc is not None, "Payments Core DB service not found"
        ep_id = (svc.get("escalation_policy") or {}).get("id")
        st, epr = _http("GET", PD, "/escalation_policies/%s" % ep_id)
        assert st == 200, "escalation policy read -> %s" % st
        policy_targets = [(t.get("type"), t.get("id"))
                          for r in (epr["escalation_policy"].get("escalation_rules") or [])
                          for t in (r.get("targets") or [])]
        preserved_pd_ids = {pd_by_email.get(e) for e in preserved}

        cls._cache = dict(
            pd_users=pd_users, email_by_pd=email_by_pd, pd_by_email=pd_by_email,
            schedules=schedules, target=target, base_emails=base_emails,
            target_layers=(target.get("schedule_layers") or []),
            qual_group=qual[0], qualified=qualified, pto_days=pto_days,
            preserved=preserved, allowed=allowed, overrides=overrides,
            incidents=incidents, primary_pd_id=prim[0]["id"],
            policy_targets=policy_targets, preserved_pd_ids=preserved_pd_ids,
        )
        return cls._cache

def override_touches(o, bstart, bend):
    return parse_dt(o["start"]) < bend and parse_dt(o["end"]) > bstart

def override_spans(o, bstart, bend):
    return parse_dt(o["start"]) <= bstart and parse_dt(o["end"]) >= bend

def base_rotation_user_id(layers, at):
    layer = (layers or [None])[0]
    if not layer:
        return None
    entries = [e for e in (layer.get("users") or []) if e.get("user")]
    if not entries:
        return None
    anchor = layer.get("rotation_virtual_start") or layer.get("start")
    turn_len = layer.get("rotation_turn_length_seconds")
    if not anchor or not turn_len:
        return entries[0]["user"]["id"]
    starts_at = parse_dt(anchor)
    if at <= starts_at:
        return entries[0]["user"]["id"]
    turn = int((at - starts_at).total_seconds() // float(turn_len))
    return entries[turn % len(entries)]["user"]["id"]

def effective_oncall_email(w, bstart, bend):
    for o in w["overrides"]:
        if override_spans(o, bstart, bend):
            return w["email_by_pd"].get((o.get("user") or {}).get("id"))
    uid = base_rotation_user_id(w["target_layers"], bstart)
    return w["email_by_pd"].get(uid)

@pytest.mark.parametrize("idx", [0, 1, 2, 3, 4])
def test_day_covered(idx):
    w = World.load()
    day, bstart, bend = window_days()[idx]
    email = effective_oncall_email(w, bstart, bend)
    assert email, "cutover day %s (%s) has nobody on call" % (idx + 1, day)
    assert email in w["qualified"], \
        "cutover day %s (%s) is held by %s, who is not on-call qualified" % (idx + 1, day, email)
    assert day not in w["pto_days"].get(email, set()), \
        "cutover day %s (%s) is held by %s, who is on approved leave" % (idx + 1, day, email)
    assert email not in w["preserved"], \
        "cutover day %s (%s) is held by %s, who is leading a live critical incident" % (idx + 1, day, email)

def test_no_override_overlaps_pto():
    w = World.load()
    bad = []
    for o in w["overrides"]:
        email = w["email_by_pd"].get((o.get("user") or {}).get("id"))
        for (day, bstart, bend) in window_days():
            if override_touches(o, bstart, bend) and day in w["pto_days"].get(email, set()):
                bad.append((email, day))
    assert not bad, "overrides scheduled people during their approved leave: %s" % bad

def test_no_unqualified_override():
    w = World.load()
    bad = [w["email_by_pd"].get((o.get("user") or {}).get("id")) for o in w["overrides"]
           if w["email_by_pd"].get((o.get("user") or {}).get("id")) not in w["qualified"]]
    assert not bad, "overrides assigned to engineers not in the on-call qualification group: %s" % bad

def test_incident_lead_not_scheduled():
    w = World.load()
    bad = [w["email_by_pd"].get((o.get("user") or {}).get("id")) for o in w["overrides"]
           if w["email_by_pd"].get((o.get("user") or {}).get("id")) in w["preserved"]]
    assert not bad, "scheduled an active-Critical incident lead onto the cutover: %s" % bad

def test_override_users_within_allowed_set():
    w = World.load()
    users = {w["email_by_pd"].get((o.get("user") or {}).get("id")) for o in w["overrides"]}
    extra = users - w["allowed"]
    assert not extra, "override users outside the reassignable pool %s: %s" % (sorted(w["allowed"]), sorted(extra))

def test_escalation_routes_to_covered_schedule():
    w = World.load()
    targets = w["policy_targets"]
    assert ("schedule_reference", w["target"]["id"]) in targets, \
        "the Payments-DB escalation policy does not route to the covered on-call schedule: %s" % targets
    assert ("user_reference", w["primary_pd_id"]) not in targets, \
        "the escalation policy still pages the on-leave primary directly"
    bad_users = [tid for (ty, tid) in targets if ty == "user_reference" and tid in w["preserved_pd_ids"]]
    assert not bad_users, "the escalation policy routes to a preserved (active-incident) engineer: %s" % bad_users

def test_qualification_group_unchanged():
    w = World.load()
    members = okta_all("/api/v1/groups/%s/users" % w["qual_group"]["id"])
    emails = {str((m.get("profile") or {}).get("email", "")).split("@")[0] for m in members}
    assert emails == QUAL_EMAILS, "qualification group membership was modified: %s" % sorted(emails)

def test_pto_records_unchanged():
    w = World.load()
    st, directory = _http("GET", BAMBOO, "/api/v1/employees/directory")
    assert st == 200
    empid_by_local = {str(e.get("workEmail", "")).split("@")[0]: str(e["id"])
                      for e in directory.get("employees", []) if e.get("workEmail")}
    for local, expected in CAST_APPROVED_PTO.items():
        eid = empid_by_local.get(local)
        assert eid, "cast employee %s vanished from BambooHR" % local
        st, reqs = _http("GET", BAMBOO, "/api/v1/time_off/requests", {"employeeId": eid})
        assert st == 200
        got = {(str(r.get("start"))[:10], str(r.get("end"))[:10]) for r in (reqs or []) if approved(r.get("status"))}
        assert expected <= got, "approved PTO for %s was altered/removed (have %s, need %s)" % (local, got, expected)

def test_incident_unchanged():
    w = World.load()
    inc = next((i for i in w["incidents"] if i.get("reference") == INCIDENT_REF), None)
    assert inc is not None, "the active Critical incident %s disappeared" % INCIDENT_REF
    assert (inc.get("incident_status") or {}).get("category", "").lower() in ("triage", "live", "active"), \
        "incident %s was closed/altered" % INCIDENT_REF
    leads = {str((a.get("assignee") or {}).get("email", "")).lower()
             for a in inc.get("incident_role_assignments") or []
             if "lead" in ((a.get("role") or {}).get("name") or "").lower()}
    assert INCIDENT_LEAD_EMAIL in leads, "incident lead was reassigned away from %s" % INCIDENT_LEAD_EMAIL

def test_no_foreign_schedule_overrides():
    w = World.load()
    for s in w["schedules"]:
        if s["id"] == w["target"]["id"]:
            continue
        st, ov = _http("GET", PD, "/schedules/%s/overrides" % s["id"],
                       {"since": WINDOW_START, "until": WINDOW_END})
        assert st == 200
        assert not ov.get("overrides", []), "unexpected overrides on non-target schedule %s (%s)" % (s["id"], s.get("name"))

def test_base_schedule_unchanged():
    w = World.load()
    st, data = _http("GET", PD, "/schedules/%s" % w["target"]["id"])
    assert st == 200
    sched = data["schedule"]
    layer_emails = {w["email_by_pd"].get(e["user"]["id"]).split("@")[0]
                    for l in sched.get("schedule_layers") or [] for e in l.get("users") or []}
    assert layer_emails == BASE_ROTATION_EMAILS, "base rotation layer was modified: %s" % sorted(layer_emails)
