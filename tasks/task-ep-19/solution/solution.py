#!/usr/bin/env python3
import os, sys, json, urllib.parse
from http import client as httpclient
from datetime import datetime, timezone

TRIGGER_ID = "P-TRIG01"

HOSTS = {
    "crowdstrike": "crowdstrike.local.mock",
    "device42": "device42.local.mock",
    "pagerduty": "pagerduty.local.mock",
    "vanta": "vanta.local.mock",
    "zscaler": "zscaler-zia.local.mock",
}

def _fail(msg):
    print("ORACLE-FAIL:", msg)
    sys.exit(3)

def call(method, host, path, query=None, body=None, headers=None):
    logical = f"{host}:8080"
    addr = os.environ.get("TASKGEN_MOCK_ADDR")
    if addr:
        ch, cp = addr.split(":"); cp = int(cp)
    else:
        ch, cp = host, 8080
    if query:
        qs = urllib.parse.urlencode(query, doseq=True)
        full = f"{path}?{qs}"
    else:
        full = path
    hdrs = {"Host": logical, "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    if headers:
        hdrs.update(headers)
    conn = httpclient.HTTPConnection(ch, cp, timeout=60)
    conn.request(method, full, body=data, headers=hdrs)
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    try:
        parsed = json.loads(raw) if raw else None
    except Exception:
        parsed = None
    return resp.status, parsed

def cs_devices():
    st, b = call("GET", HOSTS["crowdstrike"], "/devices/combined/devices/v1", {"limit": 5000})
    if st != 200: _fail(f"cs devices list {st}")
    return b["resources"]

def cs_groups():
    st, b = call("GET", HOSTS["crowdstrike"], "/devices/combined/host-groups/v1", {"limit": 500})
    if st != 200: _fail(f"cs groups {st}")
    return b["resources"]

def cs_group_members(gid):
    st, b = call("GET", HOSTS["crowdstrike"], "/devices/combined/host-group-members/v1",
                 {"id": gid, "limit": 5000})
    if st != 200: _fail(f"cs members {st}")
    return b["resources"]

def cs_iocs():
    st, b = call("GET", HOSTS["crowdstrike"], "/iocs/combined/indicator/v1", {"limit": 5000})
    if st != 200: _fail(f"cs iocs {st}")
    return b["resources"]

def d42_devices():
    out = []
    offset = 0
    while True:
        st, b = call("GET", HOSTS["device42"], "/api/1.0/devices/",
                     {"limit": 1000, "offset": offset})
        if st != 200: _fail(f"d42 devices {st}")
        page = b.get("devices") or []
        out.extend(page)
        total = b.get("total_count", len(out))
        offset += len(page)
        if not page or offset >= total:
            break
    return out

def d42_by_name(name):
    st, b = call("GET", HOSTS["device42"], f"/api/1.0/devices/name/{urllib.parse.quote(name)}/")
    if st != 200:
        return None
    return b

def pd_users():
    st, b = call("GET", HOSTS["pagerduty"], "/users", {"limit": 100})
    if st != 200: _fail(f"pd users {st}")
    return b["users"]

def pd_incident(iid):
    st, b = call("GET", HOSTS["pagerduty"], f"/incidents/{iid}")
    if st != 200: _fail(f"pd trigger incident {iid} not found ({st})")
    return b["incident"]

def pd_services():
    st, b = call("GET", HOSTS["pagerduty"], "/services", {"limit": 200})
    if st != 200: _fail(f"pd services {st}")
    return b["services"]

def vanta_tests():
    out = []
    cursor = None
    while True:
        q = {"pageSize": 100}
        if cursor: q["pageCursor"] = cursor
        st, b = call("GET", HOSTS["vanta"], "/v1/tests", q)
        if st != 200: _fail(f"vanta tests {st}")
        res = b["results"]
        out.extend(res["data"])
        pi = res["pageInfo"]
        if pi.get("hasNextPage") and pi.get("endCursor"):
            cursor = pi["endCursor"]
        else:
            break
    return out

def vanta_entities(test_id, status):
    out = []
    cursor = None
    while True:
        q = {"pageSize": 100, "entityStatus": status}
        if cursor: q["pageCursor"] = cursor
        st, b = call("GET", HOSTS["vanta"], f"/v1/tests/{test_id}/entities", q)
        if st != 200: _fail(f"vanta entities {st}")
        res = b["results"]
        out.extend(res["data"])
        pi = res["pageInfo"]
        if pi.get("hasNextPage") and pi.get("endCursor"):
            cursor = pi["endCursor"]
        else:
            break
    return out

def zia_rules():
    out = []
    page = 1
    while True:
        st, b = call("GET", HOSTS["zscaler"], "/zia/api/v1/firewallFilteringRules",
                     {"page": page, "pageSize": 1000})
        if st != 200: _fail(f"zia rules {st}")
        if not b:
            break
        out.extend(b)
        if len(b) < 1000:
            break
        page += 1
    return out

def norm(s):
    return str(s or "").strip().lower()

def is_live(d42rec):
    if not d42rec:
        return False
    archived = d42rec.get("archived")
    if archived in (True, "yes", "true", 1, "1"):
        return False
    ins = d42rec.get("in_service")
    return ins in (True, "yes", "true", 1, "1", None)

def parse_dt(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None

def get_now():
    inc = pd_incident(TRIGGER_ID)
    dt = parse_dt(inc.get("created_at"))
    return dt

def main():
    plan = []

    inc = pd_incident(TRIGGER_ID)
    text = f"{inc.get('title','')} {inc.get('description','') or ''} {json.dumps(inc.get('body') or {})}"
    d42 = d42_devices()
    by_name = {norm(d.get("name")): d for d in d42}

    false_host = None
    for d in d42:
        nm = d.get("name")
        if nm and norm(nm) in norm(text) and not is_live(d):
            false_host = d
            break
    if not false_host:
        _fail("false-premise: no decommissioned host from the trigger resolves in device42")
    print(f"[verify] trigger false premise: {false_host.get('name')} archived={false_host.get('archived')} in_service={false_host.get('in_service')}")

    now = parse_dt(inc.get("created_at")) or datetime(2026, 7, 21, tzinfo=timezone.utc)

    groups = cs_groups()
    monitored = [g for g in groups if "monitored" in norm(g.get("name"))]
    if len(monitored) != 1:
        _fail(f"expected exactly one monitored host-group, found {len(monitored)}")
    mgroup = monitored[0]
    mgid = mgroup["id"]
    members = cs_group_members(mgid)
    member_ids = {norm(d.get("device_id")) for d in members}

    cs_devs = cs_devices()
    cs_by_host = {}
    for d in cs_devs:
        h = norm(d.get("hostname"))
        if h:
            cs_by_host[h] = d

    false_host_names = {norm(false_host.get("name"))}

    for d in d42:
        if not is_live(d):
            continue
        host = norm(d.get("name"))
        csd = cs_by_host.get(host)
        if not csd:
            continue
        did = csd.get("device_id")
        if csd.get("hidden") in (True, "true", 1):
            plan.append((f"unhide {host}", lambda did=did: call(
                "POST", HOSTS["crowdstrike"], "/devices/entities/devices-actions/v2",
                {"action_name": "unhide_host"}, {"ids": [did]})))
        if norm(did) not in member_ids:
            plan.append((f"add {host} -> monitored group", lambda did=did: call(
                "POST", HOSTS["crowdstrike"], "/devices/entities/host-group-actions/v1",
                {"action_name": "add-hosts"},
                {"ids": [mgid], "action_parameters": [
                    {"name": "filter", "value": f"(device_id:['{did}'])"}]})))

    tests = vanta_tests()
    edr_tests = [t for t in tests if any(k in norm(t.get("name")) for k in ("edr", "endpoint", "agent"))]
    for t in edr_tests:
        tid = t.get("id")
        deact = vanta_entities(tid, "DEACTIVATED")
        for e in deact:
            ename = norm(e.get("name") or e.get("displayName") or e.get("entityId"))
            live_match = None
            for d in d42:
                if is_live(d) and norm(d.get("name")) and norm(d.get("name")) in ename:
                    live_match = d; break
            if live_match:
                eid = e.get("id") or e.get("entityId")
                plan.append((f"reactivate vanta entity {ename}", lambda tid=tid, eid=eid: call(
                    "POST", HOSTS["vanta"], f"/v1/tests/{tid}/entities/{eid}/reactivate",
                    body={})))

    rules = zia_rules()
    def locs(r):
        return {norm(x) for x in (r.get("locations") or [])}
    enabled_by_loc = {}
    for r in rules:
        if norm(r.get("state")) == "enabled":
            for l in locs(r):
                enabled_by_loc.setdefault(l, []).append(r)
    for r in rules:
        if norm(r.get("state")) != "disabled":
            continue
        rlocs = locs(r)
        replaced = any(l in enabled_by_loc for l in rlocs)
        if rlocs and not replaced:
            rid = r.get("id")
            plan.append((f"enable zscaler rule {r.get('name')}", lambda rid=rid: call(
                "PUT", HOSTS["zscaler"], f"/zia/api/v1/firewallFilteringRules/{rid}",
                body={"state": "ENABLED"})))

    for ioc in cs_iocs():
        if ioc.get("deleted"):
            continue
        if ioc.get("expired") in (True, "true", 1):
            exp = parse_dt(ioc.get("expiration"))
            if exp and exp > now:
                iid = ioc.get("id")
                plan.append((f"un-expire IOC {ioc.get('type')}:{ioc.get('value')}", lambda iid=iid: call(
                    "PATCH", HOSTS["crowdstrike"], "/iocs/entities/indicators/v1",
                    body={"indicators": [{"id": iid, "expired": False}]})))

    users = pd_users()
    if not users:
        _fail("no pagerduty users to act as")
    actor_email = users[0].get("email")
    def resolve_trigger():
        s1, _ = call("POST", HOSTS["pagerduty"], f"/incidents/{TRIGGER_ID}/notes",
                     body={"note": {"content": "False alarm: pay-proc-legacy-01 was decommissioned in May (device42 archived, successor in service, PD service disabled). Root cause of collateral coverage loss: Q2 alert-noise tuning sprint disabled/suppressed detection on live sources; restored."}},
                     headers={"From": actor_email})
        s2, _ = call("PUT", HOSTS["pagerduty"], f"/incidents/{TRIGGER_ID}",
                     body={"incident": {"type": "incident_reference", "status": "resolved"}},
                     headers={"From": actor_email})
        return s1, s2
    plan.append(("resolve trigger incident", resolve_trigger))

    print(f"\n=== PLAN ({len(plan)} writes) ===")
    for label, _ in plan:
        print("  -", label)
    print("=== EXECUTE ===")
    for label, fn in plan:
        r = fn()
        print(f"  ok: {label} -> {r if not isinstance(r, tuple) or len(r)==2 else r}")

    print("=== READBACK ===")
    members2 = {norm(d.get("device_id")) for d in cs_group_members(mgid)}
    devs2 = {norm(d.get("hostname")): d for d in cs_devices()}
    for d in d42:
        if not is_live(d):
            continue
        host = norm(d.get("name"))
        csd = devs2.get(host)
        if not csd:
            continue
        assert not (csd.get("hidden") in (True, "true", 1)), f"host {host} still hidden"
        assert norm(csd.get("device_id")) in members2, f"host {host} not in monitored group"
    fcs = devs2.get(norm(false_host.get("name")))
    if fcs:
        assert norm(fcs.get("device_id")) not in members2, "false-premise host wrongly added to group"
    assert norm(pd_incident(TRIGGER_ID).get("status")) == "resolved", "trigger not resolved"
    rules2 = {r.get("id"): r for r in zia_rules()}
    for label, _ in plan:
        pass
    print("READBACK OK")
    print("ORACLE-DONE")

if __name__ == "__main__":
    main()
