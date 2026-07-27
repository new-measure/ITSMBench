#!/usr/bin/env python3
import os, sys, json, re, http.client
from datetime import datetime, timezone, timedelta

TRIGGER_TICKET = "OPS-2041"
PROD_LEVELS = {"production", "gold", "critical"}
STALE_DAYS = 7
BACKUP_TEST_HINTS = ("backup", "recovery", "restore")

EMU_ADDR = os.environ.get("EMU_ADDR")
ACTOR_EMAIL = None

HOSTS = {
    "device42": "device42.local.mock",
    "snipeit":  "snipeit.local.mock",
    "pagerduty": "pagerduty.local.mock",
    "vanta":    "vanta.local.mock",
    "jira":     "jira.local.mock",
    "search":   "search.local.mock",
}
BASE = {
    "device42": "", "snipeit": "/api/v1", "pagerduty": "", "vanta": "/v1", "jira": "",
}

def api(method, prov, path, body=None, headers=None):
    host = HOSTS[prov]
    if EMU_ADDR:
        ip, port = EMU_ADDR.split(":"); c = http.client.HTTPConnection(ip, int(port), timeout=60)
    else:
        c = http.client.HTTPConnection(host, 8080, timeout=60)
    h = {"Host": host, "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body); h["Content-Type"] = "application/json"
    if headers:
        h.update(headers)
    full = (BASE.get(prov, "") + path) if prov in BASE else path
    c.request(method, full, body=data, headers=h)
    r = c.getresponse(); raw = r.read().decode(); dh = r.getheader("date"); c.close()
    try:
        parsed = json.loads(raw) if raw else None
    except Exception:
        parsed = raw
    return r.status, parsed, dh

_NOW = None
def NOW():
    global _NOW
    if _NOW is None:
        _, _, dh = api("GET", "pagerduty", "/services?limit=1")
        _NOW = datetime.strptime(dh, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc)
    return _NOW

def die(msg):
    print("ORACLE-FAIL:", msg); sys.exit(1)

def parse_dt(s):
    if not s: return None
    s = str(s).strip().replace("Z", "+00:00")
    for fmt in (None,):
        try:
            return datetime.fromisoformat(s).astimezone(timezone.utc)
        except Exception:
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(s).strip(), fmt).replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return None

def pd_all(coll, params=""):
    out, offset = [], 0
    while True:
        sep = "&" if params else ""
        st, d, _ = api("GET", "pagerduty", f"/{coll}?limit=100&offset={offset}{sep}{params}")
        if st != 200 or not isinstance(d, dict): die(f"pagerduty list {coll} -> {st} {d}")
        page = d.get(coll, []); out += page
        if not d.get("more") or not page: break
        offset += len(page)
    return out

def snipe_all(coll, params=""):
    out, offset = [], 0
    while True:
        sep = "&" if params else ""
        st, d, _ = api("GET", "snipeit", f"/{coll}?limit=500&offset={offset}{sep}{params}")
        if st != 200 or not isinstance(d, dict): die(f"snipeit list {coll} -> {st} {d}")
        rows = d.get("rows", []); out += rows
        if offset + len(rows) >= d.get("total", 0) or not rows: break
        offset += len(rows)
    return out

def d42_all():
    out, offset = [], 0
    while True:
        st, d, _ = api("GET", "device42", f"/api/2.0/devices/?limit=1000&offset={offset}")
        if st != 200 or not isinstance(d, dict): die(f"device42 list -> {st} {d}")
        devs = d.get("devices", []); out += devs
        if offset + len(devs) >= d.get("total_count", 0) or not devs: break
        offset += len(devs)
    return out

def vanta_test_entities(test_id, status):
    out, cursor = [], None
    while True:
        q = f"?pageSize=100&entityStatus={status}" + (f"&pageCursor={cursor}" if cursor else "")
        st, d, _ = api("GET", "vanta", f"/tests/{test_id}/entities{q}")
        if st != 200 or not isinstance(d, dict): die(f"vanta entities {test_id}/{status} -> {st} {d}")
        res = d.get("results", {}); out += res.get("data", [])
        pi = res.get("pageInfo", {})
        if not pi.get("hasNextPage"): break
        cursor = pi.get("endCursor")
    return out

def main():
    now = NOW()
    stale_before = now - timedelta(days=STALE_DAYS)

    st, ticket, _ = api("GET", "jira", f"/rest/api/3/issue/{TRIGGER_TICKET}")
    if st != 200: die(f"trigger ticket {TRIGGER_TICKET} not readable ({st})")

    global ACTOR_EMAIL
    for u in pd_all("users"):
        if u.get("email"): ACTOR_EMAIL = u["email"]; break

    esc = pd_all("escalation_policies")
    esc_id = esc[0]["id"] if esc else None

    suppliers = snipe_all("suppliers")
    supplier_id = suppliers[0]["id"] if suppliers else None

    services = pd_all("services", "total=true")
    incidents = pd_all("incidents", "total=true")
    windows = pd_all("maintenance_windows", "total=true")
    devices = d42_all()
    assets = snipe_all("hardware")
    maints = snipe_all("maintenances")

    def norm(x): return str(x or "").strip().lower()
    backup_services = [s for s in services if "backup" in norm(s.get("name"))]

    active_svc_ids = set()
    active_win_by_svc = {}
    for w in windows:
        start = parse_dt(w.get("start_time")); end = parse_dt(w.get("end_time"))
        if start and end and start <= now < end:
            for ref in (w.get("services") or []):
                active_svc_ids.add(str(ref.get("id")))
                active_win_by_svc.setdefault(str(ref.get("id")), []).append(w)

    OPEN = {"triggered", "acknowledged"}
    open_svc_ids = {str((i.get("service") or {}).get("id")) for i in incidents
                    if str(i.get("status")) in OPEN}

    st, catd, _ = api("GET", "snipeit", "/categories?limit=500")
    server_cat = {str(c.get("id")) for c in (catd.get("rows", []) if st == 200 else [])
                  if "server" in norm(c.get("name"))}

    prod = {}
    for d in devices:
        if d.get("in_service") is True and norm(d.get("service_level")) in PROD_LEVELS:
            prod[norm(d.get("name"))] = {"serial": norm(d.get("serial_no"))}
    for a in assets:
        if str(a.get("category_id")) in server_cat or "server" in norm((a.get("category") or {}).get("name") if isinstance(a.get("category"), dict) else a.get("category")):
            prod.setdefault(norm(a.get("name")), {"serial": norm(a.get("serial"))})

    def covering(name, serial):
        return [s for s in backup_services
                if name in norm(s.get("name")) or (serial and serial in norm(s.get("name")))]

    plan = []
    for name in sorted(prod):
        if not name: continue
        serial = prod[name].get("serial")
        cov = covering(name, serial)
        if not cov:
            plan.append(("onboard", name, None)); continue
        disabled = [s for s in cov if str(s.get("status")) == "disabled"]
        if disabled:
            plan.append(("enable", name, disabled[0])); continue
        muted = [w for s in cov if str(s.get("id")) in open_svc_ids
                 for w in active_win_by_svc.get(str(s.get("id")), [])]
        if muted:
            plan.append(("unmute", name, ({"svc_ids": [s["id"] for s in cov], "windows": muted}))); continue

    print("PLAN:")
    for kind, name, _ in plan:
        print(f"  {kind:8s} {name}")
    if not plan:
        die("empty plan — seed does not implement the scenario")

    for kind, name, payload in plan:
        if kind == "onboard":
            if not esc_id: die("no escalation policy to attach a new service to")
            st, d, _ = api("POST", "pagerduty", "/services",
                           {"service": {"name": f"nightly-backup: {name}",
                                        "description": f"Backup job for {name}",
                                        "escalation_policy": {"id": esc_id,
                                                              "type": "escalation_policy_reference"}}})
            if st != 201: die(f"onboard {name} -> {st} {d}")
        elif kind == "enable":
            st, d, _ = api("PUT", "pagerduty", f"/services/{payload['id']}", {"service": {"status": "active"}})
            if st != 200: die(f"enable {name} -> {st} {d}")
        elif kind == "unmute":
            for w in payload["windows"]:
                st, d, _ = api("DELETE", "pagerduty", f"/maintenance_windows/{w['id']}")
                if st not in (200, 204): die(f"unmute {name} window {w['id']} -> {st} {d}")

    services2 = pd_all("services", "total=true")
    windows2 = pd_all("maintenance_windows", "total=true")
    bk2 = [s for s in services2 if "backup" in norm(s.get("name"))]

    def covering2(name, serial):
        return [s for s in bk2 if name in norm(s.get("name")) or (serial and serial in norm(s.get("name")))]

    for kind, name, payload in plan:
        serial = prod[name].get("serial")
        if kind == "onboard":
            if not covering2(name, serial):
                die(f"readback: onboarded service for {name} missing")
        elif kind == "enable":
            cov = covering2(name, serial)
            if not cov or all(str(s.get("status")) == "disabled" for s in cov):
                die(f"readback: {name} still not active")
        elif kind == "unmute":
            cov_ids = {str(s.get("id")) for s in covering2(name, serial)}
            active = [w for w in windows2
                      if parse_dt(w.get("start_time")) and parse_dt(w.get("end_time"))
                      and parse_dt(w["start_time"]) <= now < parse_dt(w["end_time"])
                      and any(str(r.get("id")) in cov_ids for r in (w.get("services") or []))]
            if active: die(f"readback: {name} still muted by an active window")

    print("ORACLE-OK: all writes verified")

if __name__ == "__main__":
    main()
