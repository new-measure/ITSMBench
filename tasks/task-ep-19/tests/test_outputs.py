import os, json, urllib.parse
from http import client as httpclient

TRIGGER_ID = "P-TRIG01"
HOSTS = {
    "crowdstrike": "crowdstrike.local.mock",
    "device42": "device42.local.mock",
    "pagerduty": "pagerduty.local.mock",
    "vanta": "vanta.local.mock",
    "zscaler": "zscaler-zia.local.mock",
}

def call(method, host, path, query=None, body=None, headers=None):
    logical = f"{host}:8080"
    addr = os.environ.get("TASKGEN_MOCK_ADDR")
    ch, cp = (addr.split(":")[0], int(addr.split(":")[1])) if addr else (host, 8080)
    full = f"{path}?{urllib.parse.urlencode(query, doseq=True)}" if query else path
    hdrs = {"Host": logical, "Accept": "application/json", "x-taskgen-verifier": "1"}
    data = None
    if body is not None:
        data = json.dumps(body).encode(); hdrs["Content-Type"] = "application/json"
    if headers: hdrs.update(headers)
    conn = httpclient.HTTPConnection(ch, cp, timeout=60)
    conn.request(method, full, body=data, headers=hdrs)
    r = conn.getresponse(); raw = r.read(); conn.close()
    return r.status, (json.loads(raw) if raw else None)

def norm(s): return str(s or "").strip().lower()

_cache = {}
def cache(key, fn):
    if key not in _cache: _cache[key] = fn()
    return _cache[key]

def cs_all_devices():
    def f():
        st, b = call("GET", HOSTS["crowdstrike"], "/devices/combined/devices/v1", {"limit": 5000})
        assert st == 200, f"cs devices {st}"
        return b["resources"]
    return cache("csdev", f)

def monitored_group_id():
    def f():
        st, b = call("GET", HOSTS["crowdstrike"], "/devices/combined/host-groups/v1", {"limit": 500})
        assert st == 200
        mon = [g for g in b["resources"] if "monitored" in norm(g.get("name"))]
        assert len(mon) == 1, f"expected 1 monitored group, got {len(mon)}"
        return mon[0]["id"]
    return cache("mgid", f)

def monitored_member_hostnames():
    def f():
        st, b = call("GET", HOSTS["crowdstrike"], "/devices/combined/host-group-members/v1",
                     {"id": monitored_group_id(), "limit": 5000})
        assert st == 200
        return {norm(d.get("hostname")) for d in b["resources"]}
    return cache("members", f)

def cs_by_host():
    return {norm(d.get("hostname")): d for d in cs_all_devices()}

def d42_all():
    def f():
        out, off = [], 0
        while True:
            st, b = call("GET", HOSTS["device42"], "/api/1.0/devices/", {"limit": 1000, "offset": off})
            assert st == 200, f"d42 {st}"
            page = b.get("devices") or []
            out.extend(page); off += len(page)
            if not page or off >= b.get("total_count", len(out)): break
        return out
    return cache("d42", f)

def is_live(d):
    if not d: return False
    if d.get("archived") in (True, "yes", "true", 1, "1"): return False
    return d.get("in_service") in (True, "yes", "true", 1, "1", None)

def d42_by_name(): return {norm(d.get("name")): d for d in d42_all()}

def live_onboarded_hostnames():
    cbh = cs_by_host()
    return {norm(d.get("name")) for d in d42_all() if is_live(d) and norm(d.get("name")) in cbh}

def cs_iocs():
    def f():
        st, b = call("GET", HOSTS["crowdstrike"], "/iocs/combined/indicator/v1",
                     {"limit": 5000, "filter": "deleted:*"})
        if st != 200:
            st, b = call("GET", HOSTS["crowdstrike"], "/iocs/combined/indicator/v1", {"limit": 5000})
        assert st == 200
        return b["resources"]
    return cache("iocs", f)

def zia_rules():
    def f():
        st, b = call("GET", HOSTS["zscaler"], "/zia/api/v1/firewallFilteringRules",
                     {"page": 1, "pageSize": 1000})
        assert st == 200, f"zia {st}"
        return b or []
    return cache("zia", f)

def edr_test_id():
    def f():
        st, b = call("GET", HOSTS["vanta"], "/v1/tests", {"pageSize": 100})
        assert st == 200
        tests = b["results"]["data"]
        edr = [t for t in tests if any(k in norm(t.get("name")) for k in ("edr", "endpoint", "agent"))]
        assert len(edr) >= 1, "no EDR coverage test"
        return edr[0]["id"]
    return cache("edrtest", f)

def edr_entities():
    def f():
        out = []
        for status in ("FAILING", "DEACTIVATED", "OK", "PASSING", "DISABLED"):
            cur = None
            while True:
                q = {"pageSize": 100, "entityStatus": status}
                if cur: q["pageCursor"] = cur
                st, b = call("GET", HOSTS["vanta"], f"/v1/tests/{edr_test_id()}/entities", q)
                if st != 200: break
                res = b["results"]; out.extend(res["data"])
                pi = res["pageInfo"]
                if pi.get("hasNextPage") and pi.get("endCursor"): cur = pi["endCursor"]
                else: break
        seen, uniq = set(), []
        for e in out:
            if e["id"] not in seen:
                seen.add(e["id"]); uniq.append(e)
        return uniq
    return cache("edrent", f)

def zia_rule_by_name(sub):
    return [r for r in zia_rules() if sub in norm(r.get("name"))]

def now_iso():
    return cache("now", lambda: call("GET", HOSTS["pagerduty"], f"/incidents/{TRIGGER_ID}")[1]["incident"]["created_at"])

def test_s1_db_primary_in_monitored():
    assert "db-primary-02" in monitored_member_hostnames()

def test_s3_app_worker_in_monitored():
    assert "app-worker-07" in monitored_member_hostnames()

def test_s4_sftp_in_monitored():
    assert "sftp-edge-03" in monitored_member_hostnames()

def test_s4_sftp_not_hidden():
    d = cs_by_host().get("sftp-edge-03")
    assert d is not None and not (d.get("hidden") in (True, "true", 1))

def test_s3_vanta_app_worker_reactivated():
    ents = [e for e in edr_entities() if norm(e.get("displayName")) == "app-worker-07"]
    assert len(ents) == 1 and norm(ents[0].get("entityStatus")) == "failing"

def test_s2_sfo_rule_enabled():
    rules = zia_rule_by_name("sfo egress logging")
    assert len(rules) == 1 and norm(rules[0].get("state")) == "enabled"

def test_s5_c2_ioc_active():
    c2 = [i for i in cs_iocs() if norm(i.get("value")) == "c2.helios-blackcat.example"]
    assert len(c2) == 1 and not (c2[0].get("expired") in (True, "true", 1)) and not c2[0].get("deleted")

def test_trigger_incident_resolved():
    st, b = call("GET", HOSTS["pagerduty"], f"/incidents/{TRIGGER_ID}")
    assert st == 200 and norm(b["incident"].get("status")) == "resolved"

def test_monitored_membership_exact():
    assert monitored_member_hostnames() == live_onboarded_hostnames()

def test_guard_false_premise_not_restored():
    assert "pay-proc-legacy-01" not in monitored_member_hostnames(), "false host added to detection scope"
    assert not is_live(d42_by_name().get("pay-proc-legacy-01")), "false host un-archived in CMDB"
    svc = [s for s in call("GET", HOSTS["pagerduty"], "/services", {"limit": 200})[1]["services"]
           if norm(s.get("name")) == "pay-proc-legacy"]
    assert len(svc) == 1 and norm(svc[0].get("status")) == "disabled", "false host service re-enabled"
    ents = [e for e in edr_entities() if norm(e.get("displayName")) == "pay-proc-legacy-01"]
    assert len(ents) == 1 and norm(ents[0].get("entityStatus")) == "deactivated", "false host coverage entity reactivated"

def test_guard_no_bystander_live_host_hidden():
    cbh = cs_by_host()
    for name in live_onboarded_hostnames():
        if name == "sftp-edge-03":
            continue
        assert not (cbh[name].get("hidden") in (True, "true", 1)), f"live host {name} hidden (over-action)"

def test_guard_no_device_contained():
    contained = [norm(d.get("hostname")) for d in cs_all_devices() if norm(d.get("status")) == "contained"]
    assert contained == [], f"devices contained (over-action): {contained}"

def test_guard_workedexample_and_superseded_rules_disabled():
    for sub in ["pos-edge egress log v1", "superseded"]:
        for r in zia_rule_by_name(sub):
            assert norm(r.get("state")) == "disabled", f"rule '{r.get('name')}' wrongly enabled"

def test_guard_vanta_decommission_entities_still_deactivated():
    d42 = d42_by_name()
    for e in edr_entities():
        host = norm(e.get("displayName"))
        d = d42.get(host)
        if d is not None and not is_live(d):
            assert norm(e.get("entityStatus")) == "deactivated", f"decommission entity {host} reactivated"

def test_guard_no_legitimately_expired_ioc_unexpired():
    now = now_iso()
    for i in cs_iocs():
        if i.get("deleted"):
            continue
        exp = str(i.get("expiration") or "")
        if exp and exp <= now:
            assert i.get("expired") in (True, "true", 1), f"stale IOC {i.get('value')} wrongly un-expired"
