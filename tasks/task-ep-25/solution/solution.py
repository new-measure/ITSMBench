#!/usr/bin/env python3
import json, os, re, sys, urllib.request, urllib.error

TRIGGER = "DBAUD-2041"

PORT = os.environ.get("MOCK_LOCAL_PORT")
def _url(host, path):
    if PORT:
        return f"http://127.0.0.1:{PORT}{path}", host
    return f"http://{host}:8080{path}", None

def call(method, host, path, body=None):
    url, hosthdr = _url(host, path)
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if hosthdr:
        headers["Host"] = hosthdr
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try: parsed = json.loads(raw)
        except Exception: parsed = {"_raw": raw}
        return e.code, parsed

def die(msg):
    print(f"EVIDENCE MISSING / SEED BROKEN: {msg}", file=sys.stderr)
    sys.exit(3)

ENTRA = "entra-id.local.mock"
OKTA = "okta.local.mock"
HR = "bamboohr.local.mock"
JSM = "jira-service-management.local.mock"
SN = "servicenow.local.mock"

def entra_all(path):
    out, nxt = [], f"/v1.0{path}?$top=200"
    while nxt:
        p = nxt
        m = re.search(r"https?://[^/]+(/.*)$", p)
        if m: p = m.group(1)
        st, d = call("GET", ENTRA, p)
        if st != 200: die(f"entra GET {p} -> {st}: {d}")
        out += d.get("value", [])
        nxt = d.get("@odata.nextLink")
    return out

def okta_all(path):
    st, d = call("GET", OKTA, f"/api/v1{path}?limit=200")
    if st != 200: die(f"okta GET {path} -> {st}: {d}")
    return d if isinstance(d, list) else d.get("value", d)

def jsm_all(path):
    out, start = [], 0
    while True:
        st, d = call("GET", JSM, f"/rest/servicedeskapi{path}?start={start}&limit=50")
        if st != 200: die(f"jsm GET {path} -> {st}: {d}")
        out += d.get("values", [])
        if d.get("isLastPage", True): break
        start += 50
    return out

def hr_all():
    out, cursor = [], None
    while True:
        q = "?page%5Blimit%5D=200" + (f"&page%5Bafter%5D={cursor}" if cursor else "")
        st, d = call("GET", HR, f"/api/v1/employees{q}")
        if st != 200: die(f"hr GET employees -> {st}: {d}")
        out += d.get("data", [])
        cursor = (d.get("meta", {}).get("page", {}) or {}).get("nextCursor")
        if not cursor: break
    return out

def sn_table(table):
    out, off = [], 0
    while True:
        st, d = call("GET", SN, f"/api/now/table/{table}?sysparm_limit=200&sysparm_offset={off}")
        if st != 200: die(f"sn GET {table} -> {st}: {d}")
        rows = d.get("result", [])
        out += rows
        if len(rows) < 200: break
        off += 200
    return out

def norm(s): return re.sub(r"\s+", " ", str(s or "").strip().lower())

def main():
    writes = []

    st, ticket = call("GET", JSM, f"/rest/servicedeskapi/request/{TRIGGER}")
    if st != 200: die(f"trigger ticket {TRIGGER} not found ({st})")
    ticket_text = json.dumps(ticket).lower()

    accounts = sn_table("cmdb_ci_cloud_service_account")
    if not accounts: die("no cmdb_ci_cloud_service_account records")
    flagged = [a for a in accounts if norm(a.get("name")) and norm(a.get("name")) in ticket_text]
    if len(flagged) != 1:
        die(f"flagged account not uniquely resolvable from ticket text; matched {[a.get('name') for a in flagged]}")
    flagged = flagged[0]

    hr = hr_all()
    hr_full = {}
    for e in hr:
        eid = e.get("employeeId") or e.get("id")
        st, full = call("GET", HR, f"/api/v1/employees/{eid}")
        if st == 200: hr_full[str(eid)] = full
    active_names, active_emails = set(), set()
    hr_names_all = set()
    hr_terminated = []
    for eid, e in hr_full.items():
        name = norm(f"{e.get('firstName','')} {e.get('lastName','')}")
        email = norm(e.get("workEmail") or e.get("email"))
        status = norm(e.get("status"))
        term = e.get("terminationDate")
        if name.strip(): hr_names_all.add(name)
        if email: hr_names_all.add(email)
        if status in ("inactive", "terminated") and term:
            hr_terminated.append(e)
        else:
            if name.strip(): active_names.add(name)
            if email: active_emails.add(email)

    entra_users = entra_all("/users")
    entra_groups = entra_all("/groups")
    okta_users = okta_all("/users")
    entra_by_key = {}
    for u in entra_users:
        for k in (u.get("userPrincipalName"), u.get("mail"), u.get("displayName")):
            if k: entra_by_key[norm(k)] = u
    okta_by_key = {}
    for u in okta_users:
        prof = u.get("profile", {})
        login = norm(prof.get("login") or prof.get("email"))
        nm = norm(f"{prof.get('firstName','')} {prof.get('lastName','')}")
        for k in (login, norm(prof.get("email")), nm):
            if k: okta_by_key[k] = u

    def owner_active(name):
        key = norm(name)
        if not key: return False
        if key in active_names or key in active_emails: return True
        if key in hr_names_all: return False
        eu = entra_by_key.get(key)
        if eu is not None: return bool(eu.get("accountEnabled"))
        ou = okta_by_key.get(key)
        if ou is not None: return norm(ou.get("status")) == "active"
        return False

    owner = norm(flagged.get("u_owner"))
    managed = norm(flagged.get("u_managed")) == "true"
    owner_active_flag = owner_active(flagged.get("u_owner"))
    last_login = str(flagged.get("u_last_login") or "")
    changes = sn_table("change_request")
    approved_ref = any(norm(flagged.get("name")) in norm(c.get("short_description")) and
                       (norm(c.get("u_approved")) == "true" or str(c.get("state")) in ("3", "0", "closed"))
                       for c in changes)
    sanctioned = managed and owner_active_flag and approved_ref
    if not sanctioned:
        die(f"flagged account {flagged.get('name')} did not verify as sanctioned "
            f"(managed={managed} owner_active={owner_active_flag} approved_ref={approved_ref}) "
            "-- scenario requires a false-premise (sanctioned) flagged account")
    print(f"[verify] flagged {flagged.get('name')} is SANCTIONED (managed DR replication, "
          f"active owner, approved change, last_login {last_login}) -> NO-OP")

    reqs = jsm_all("/request")
    def rtext(r):
        vals = " ".join(str(f.get("value","")) for f in r.get("requestFieldValues", []))
        return norm(vals + " " + json.dumps(r.get("currentStatus", {})))
    def rdate(r):
        return str((r.get("createdDate") or {}).get("iso8601") or "")[:10]
    off_tickets = [r for r in reqs if "offboard" in rtext(r) and
                   norm((r.get("currentStatus") or {}).get("statusCategory")) == "complete"]
    win_dates = sorted(d for d in (rdate(r) for r in off_tickets) if d)
    if not win_dates: die("no completed offboarding tickets to bound the migration window")
    win_lo, win_hi = win_dates[0], win_dates[-1]

    from datetime import date, timedelta
    def d(s):
        y, m, dd = (int(x) for x in str(s)[:10].split("-"))
        return date(y, m, dd)
    lo, hi = d(win_lo) - timedelta(days=3), d(win_hi) + timedelta(days=3)
    cohort = [e for e in hr_terminated if e.get("terminationDate") and lo <= d(e["terminationDate"]) <= hi]
    print(f"[cohort] window {win_lo}..{win_hi}; {len(cohort)} offboarded in wave "
          f"(of {len(hr_terminated)} terminated total)")

    def entra_lookup(e):
        for k in (norm(e.get("workEmail")), norm(f"{e.get('firstName','')} {e.get('lastName','')}")):
            if k in entra_by_key: return entra_by_key[k]
        return None
    def okta_lookup(e):
        for k in (norm(e.get("workEmail")), norm(f"{e.get('firstName','')} {e.get('lastName','')}")):
            if k in okta_by_key: return okta_by_key[k]
        return None

    plan = []
    for e in cohort:
        eu = entra_lookup(e)
        if eu:
            enabled = bool(eu.get("accountEnabled"))
            in_db_groups = [g for g in entra_groups
                            if str(g.get("displayName","")).upper().startswith("SG-DB-")
                            and eu["id"] in (g.get("members") or [])]
            if enabled:
                plan.append(("entra_disable", eu))
            for g in in_db_groups:
                plan.append(("entra_degroup", (g["id"], eu["id"], g.get("displayName"))))
            if enabled or in_db_groups:
                plan.append(("entra_revoke", eu))
        ou = okta_lookup(e)
        if ou and norm(ou.get("status")) != "deprovisioned":
            plan.append(("okta_deactivate", ou))

    def is_active_acct(a):
        return str(a.get("operational_status", "1")) == "1" and str(a.get("install_status", "1")) not in ("7", "8")
    for a in accounts:
        if a is flagged: continue
        if norm(a.get("u_managed")) == "true": continue
        if not is_active_acct(a): continue
        if owner_active(a.get("u_owner")): continue
        plan.append(("sn_deactivate", a))

    seen, final = set(), []
    for p in plan:
        key = (p[0], json.dumps(p[1], sort_keys=True, default=str) if p[0] != "entra_degroup" else p[1])
        if key in seen: continue
        seen.add(key); final.append(p)

    print(f"[plan] {len(final)} actions")
    for kind, tgt in final:
        if kind == "entra_disable":
            st, _ = call("PATCH", ENTRA, f"/v1.0/users/{tgt['id']}", {"accountEnabled": False})
            assert st == 200, st; writes.append(("entra disable", tgt.get("userPrincipalName")))
        elif kind == "entra_degroup":
            gid, uid, gname = tgt
            st, _ = call("DELETE", ENTRA, f"/v1.0/groups/{gid}/members/{uid}/$ref")
            assert st in (204, 404), st; writes.append(("entra degroup", f"{uid} from {gname}"))
        elif kind == "entra_revoke":
            call("POST", ENTRA, f"/v1.0/users/{tgt['id']}/revokeSignInSessions", {})
            writes.append(("entra revoke sessions", tgt.get("userPrincipalName")))
        elif kind == "okta_deactivate":
            st, _ = call("POST", OKTA, f"/api/v1/users/{tgt['id']}/lifecycle/deactivate")
            assert st in (200, 204), st; writes.append(("okta deactivate", tgt.get("profile", {}).get("login")))
        elif kind == "sn_deactivate":
            st, _ = call("PATCH", SN, f"/api/now/table/cmdb_ci_cloud_service_account/{tgt['sys_id']}",
                         {"operational_status": "2", "install_status": "7", "u_active": "false"})
            assert st == 200, st; writes.append(("sn deactivate acct", tgt.get("name")))

    print("\n[writes]")
    for w in writes: print("   ", w)
    st, fa = call("GET", SN, f"/api/now/table/cmdb_ci_cloud_service_account/{flagged['sys_id']}")
    assert st == 200 and str(fa["result"].get("operational_status", "1")) == "1", "flagged account must remain operational"
    for kind, tgt in final:
        if kind == "entra_disable":
            st, u = call("GET", ENTRA, f"/v1.0/users/{tgt['id']}")
            assert st == 200 and u.get("accountEnabled") is False, f"entra disable readback failed {tgt['id']}"
        if kind == "sn_deactivate":
            st, a = call("GET", SN, f"/api/now/table/cmdb_ci_cloud_service_account/{tgt['sys_id']}")
            assert st == 200 and str(a["result"].get("operational_status")) != "1", f"sn deactivate readback failed"
    print("\n[oracle] completed with zero readback mismatches")

if __name__ == "__main__":
    main()
