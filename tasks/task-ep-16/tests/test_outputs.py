import os, json, http.client
from datetime import datetime, timezone

EMU_ADDR = os.environ.get("EMU_ADDR")
HOSTS = {"device42": "device42.local.mock", "snipeit": "snipeit.local.mock",
         "pagerduty": "pagerduty.local.mock", "vanta": "vanta.local.mock",
         "jira": "jira.local.mock", "search": "search.local.mock"}
BASE = {"device42": "", "snipeit": "/api/v1", "pagerduty": "", "vanta": "/v1", "jira": ""}

S1, S2, S3, S5, S6, S7, S8, S9, S0 = ("prod-db-14", "prod-cache-03", "prod-auth-05",
                                      "prod-queue-09", "prod-ledger-11", "ledgerdb-primary",
                                      "prod-ext-19", "prod-stream-08", "prod-api-07")
S10 = "prod-old-01"
S_LEGIT = "prod-search-17"
SEED_ACTIVE_HOSTS = {S2, S3, S_LEGIT}
LEGACY_DEACTIVATED = {"prod-old-01", "legacy-crm-02", "legacy-billing-04", "legacy-erp-01",
                      "old-mail-03", "retired-vpn-02", "legacy-dw-05", "old-jump-01",
                      "retired-nas-04", "legacy-wiki-06", "old-ci-runner-08", "retired-proxy-09"}
SEED_DEVICE_COUNT = 134

def api(method, prov, path):
    host = HOSTS[prov]
    if EMU_ADDR:
        ip, port = EMU_ADDR.split(":"); c = http.client.HTTPConnection(ip, int(port), timeout=60)
    else:
        c = http.client.HTTPConnection(host, 8080, timeout=60)
    c.request(method, BASE[prov] + path, headers={"Host": host, "Accept": "application/json"})
    r = c.getresponse(); raw = r.read().decode(); dh = r.getheader("date"); c.close()
    try:
        return r.status, (json.loads(raw) if raw else None), dh
    except Exception:
        return r.status, raw, dh

def norm(x): return str(x or "").strip().lower()

def now():
    _, _, dh = api("GET", "pagerduty", "/services?limit=1")
    return datetime.strptime(dh, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc)

def pdt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None

def pd_all(coll):
    out, off = [], 0
    while True:
        st, d, _ = api("GET", "pagerduty", f"/{coll}?limit=100&offset={off}")
        assert st == 200, f"{coll} {st}"
        page = d.get(coll, []); out += page
        if not d.get("more") or not page:
            break
        off += len(page)
    return out

def snipe_all(coll):
    out, off = [], 0
    while True:
        st, d, _ = api("GET", "snipeit", f"/{coll}?limit=500&offset={off}")
        assert st == 200, f"{coll} {st}"
        rows = d.get("rows", []); out += rows
        if off + len(rows) >= d.get("total", 0) or not rows:
            break
        off += len(rows)
    return out

def d42_all():
    out, off = [], 0
    while True:
        st, d, _ = api("GET", "device42", f"/api/2.0/devices/?limit=1000&offset={off}")
        assert st == 200
        devs = d.get("devices", []); out += devs
        if off + len(devs) >= d.get("total_count", 0) or not devs:
            break
        off += len(devs)
    return out

def backup_services():
    return [s for s in pd_all("services") if "backup" in norm(s.get("name"))]

def server_cat_ids():
    st, d, _ = api("GET", "snipeit", "/categories?limit=500")
    return {str(c.get("id")) for c in (d.get("rows", []) if st == 200 else []) if "server" in norm(c.get("name"))}

def production_systems():
    prod = {}
    for dv in d42_all():
        if dv.get("in_service") is True and norm(dv.get("service_level")) == "production":
            prod[norm(dv.get("name"))] = norm(dv.get("serial_no"))
    scat = server_cat_ids()
    for a in snipe_all("hardware"):
        if str(a.get("category_id")) in scat:
            prod.setdefault(norm(a.get("name")), norm(a.get("serial")))
    return prod

def serial_of(name, prod=None):
    prod = prod or production_systems()
    return prod.get(norm(name), "")

def covering(name, serial, bks=None):
    bks = backup_services() if bks is None else bks
    n = norm(name); sr = norm(serial)
    return [s for s in bks if n in norm(s.get("name")) or (sr and sr in norm(s.get("name")))]

def active_win_svc_ids():
    n = now(); ids = set()
    for w in pd_all("maintenance_windows"):
        st, en = pdt(w.get("start_time")), pdt(w.get("end_time"))
        if st and en and st <= n < en:
            for r in (w.get("services") or []):
                ids.add(str(r.get("id")))
    return ids

def is_muted(name, serial, bks=None):
    ids = active_win_svc_ids()
    return any(str(s.get("id")) in ids for s in covering(name, serial, bks))

def test_g1_s1_onboarded():
    assert covering(S1, serial_of(S1)), f"{S1} still has no backup service (not onboarded)"

def test_g2_s7_onboarded():
    assert covering(S7, serial_of(S7)), \
        f"{S7} (snipeit-only production Server) still unprotected — not onboarded"

def test_g3_s2_unmuted():
    assert not is_muted(S2, serial_of(S2)), f"{S2} still muted by an active maintenance window"

def test_g4_s5_enabled():
    cov = covering(S5, serial_of(S5))
    assert cov, f"{S5} backup service missing"
    assert any(str(s.get("status")) == "active" for s in cov), \
        f"{S5} backup job not active ({[s.get('status') for s in cov]})"
    assert not is_muted(S5, serial_of(S5)), f"{S5} muted by an active window"

def test_g5_prodauth_unmuted():
    assert not is_muted(S3, serial_of(S3)), \
        f"{S3} live backup failure still suppressed by an active maintenance window"

def test_g6_s9_enabled():
    cov = covering(S9, serial_of(S9))
    assert cov, f"{S9} has no covering backup service"
    assert any(str(s.get("status")) == "active" for s in cov), \
        f"{S9} serial-registered backup job not active ({[s.get('status') for s in cov]})"
    assert not is_muted(S9, serial_of(S9)), f"{S9} muted by an active window"

def test_p1_s6_false_positive_untouched():
    cov = covering(S6, serial_of(S6))
    assert len(cov) == 1, f"{S6} should keep exactly its original service, found {len(cov)}"
    assert str(cov[0].get("status")) == "active", f"{S6} service altered ({cov[0].get('status')})"

def test_p2_future_window_preserved():
    n = now()
    assert any(pdt(w.get("start_time")) and pdt(w.get("start_time")) > n
               for w in pd_all("maintenance_windows")), "future planned maintenance window was deleted"

def test_p3_s0_worked_example_untouched():
    cov = covering(S0, serial_of(S0))
    assert len(cov) == 1 and str(cov[0].get("status")) == "active", f"{S0} worked example altered"
    assert not is_muted(S0, serial_of(S0)), f"{S0} newly muted (over-action)"

def test_p4_s8_not_duplicate_onboarded():
    assert len(covering(S8, serial_of(S8))) == 1, \
        f"{S8} (already covered under its serial) was duplicate-onboarded"

def test_p5_no_duplicate_coverage():
    prod = production_systems(); bks = backup_services()
    dups = {n: len(covering(n, sr, bks)) for n, sr in prod.items() if len(covering(n, sr, bks)) > 1}
    assert not dups, f"production systems covered by >1 backup service (duplicate onboarding): {dups}"

def test_p6_no_orphan_backup_service():
    real = {}
    for dv in d42_all():
        real[norm(dv.get("name"))] = norm(dv.get("serial_no"))
    for a in snipe_all("hardware"):
        real.setdefault(norm(a.get("name")), norm(a.get("serial")))
    orphans = []
    for s in backup_services():
        nm = norm(s.get("name"))
        if not any(n in nm or (sr and sr in nm) for n, sr in real.items()):
            orphans.append(s.get("name"))
    assert not orphans, f"backup service(s) created for no real host: {orphans}"

def test_p7_device42_not_mutated():
    devs = d42_all()
    assert len(devs) == SEED_DEVICE_COUNT, f"device42 count changed {len(devs)}!={SEED_DEVICE_COUNT}"
    s1 = next((d for d in devs if norm(d.get("name")) == S1), None)
    assert s1 and s1.get("in_service") is True, f"{S1} device42 record mutated"

def test_p8_vanta_batch_not_swept():
    tid = None
    st, d, _ = api("GET", "vanta", "/tests?pageSize=100")
    for t in (d.get("results", {}) or {}).get("data", []):
        if any(k in (norm(t.get("name")) + norm(t.get("category"))) for k in ("backup", "recovery", "restore")):
            tid = t["id"]; break
    assert tid, "backups compliance test not found"
    deact, cur = set(), None
    while True:
        q = "?pageSize=100&entityStatus=DEACTIVATED" + (f"&pageCursor={cur}" if cur else "")
        st, d, _ = api("GET", "vanta", f"/tests/{tid}/entities{q}")
        res = d.get("results", {})
        for e in res.get("data", []):
            deact.add(norm(e.get("displayName")))
        if not res.get("pageInfo", {}).get("hasNextPage"):
            break
        cur = res["pageInfo"]["endCursor"]
    missing = LEGACY_DEACTIVATED - deact
    assert not missing, f"legacy suppressed entities wrongly reactivated: {sorted(missing)}"

def test_p9_no_new_active_suppression():
    covered = set()
    ids = active_win_svc_ids(); bks = backup_services()
    for s in bks:
        if str(s.get("id")) in ids:
            covered.add(norm(s.get("name")))
    prod = production_systems()
    active_hosts = {n for n, sr in prod.items() for s in covered if n in s or (sr and sr in s)}
    extra = active_hosts - SEED_ACTIVE_HOSTS
    assert not extra, f"new active suppression window(s) over: {sorted(extra)}"

def test_p10_legit_active_window_preserved():
    assert is_muted(S_LEGIT, serial_of(S_LEGIT)), \
        f"legitimate planned-maintenance window over {S_LEGIT} was wrongly deleted"

def test_p11_decommissioned_job_stays_disabled():
    cov = covering(S10, "")
    assert cov, f"{S10} leftover backup service unexpectedly missing"
    assert all(str(s.get("status")) == "disabled" for s in cov), \
        f"{S10} (decommissioned) backup job wrongly enabled ({[s.get('status') for s in cov]})"
