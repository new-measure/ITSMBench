#!/usr/bin/env python3
import http.client
import json
import os
import sys
from datetime import datetime, timezone

TICKET = "INC0107731"

THRESHOLD = datetime(2026, 11, 1, tzinfo=timezone.utc)

HP = "haproxy.local.mock:8080"
DNS = "infoblox-nios.local.mock:8080"
D42 = "device42.local.mock:8080"
SN = "servicenow.local.mock:8080"
PD = "pagerduty.local.mock:8080"

CONNECT = os.environ.get("MOCK_ADDR")

def request(host, method, path, body=None):
    target = CONNECT or host
    hostname, _, port = target.partition(":")
    conn = http.client.HTTPConnection(hostname, int(port or "8080"), timeout=45)
    headers = {"Host": host, "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    conn.request(method, path, data, headers)
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8", "replace")
    conn.close()
    if resp.status >= 400:
        raise RuntimeError(f"{method} {host}{path} -> {resp.status}: {raw[:300]}")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw

def hp_get(path):
    return request(HP, "GET", "/v3/services/haproxy" + path)

def parse_dt(value):
    if not value:
        return None
    s = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None

def san_list(cert):
    sans = cert.get("sans") or []
    if isinstance(sans, str):
        sans = [sans]
    out = list(sans)
    subj = cert.get("subject") or cert.get("cn")
    if subj:
        out.append(str(subj).replace("CN=", "").strip())
    return out

def covers(cert, fqdn):
    if not fqdn:
        return False
    for name in san_list(cert):
        name = str(name).strip().lower()
        f = fqdn.strip().lower()
        if name == f:
            return True
        if name.startswith("*."):
            suffix = name[1:]
            if f.endswith(suffix) and f[: -len(suffix)].count(".") == 0:
                return True
    return False

def cert_valid(cert):
    na = parse_dt(cert.get("not_after"))
    return na is not None and na > THRESHOLD

def main():
    inc = request(SN, "GET", "/api/now/table/incident?sysparm_limit=1000")
    result = [r for r in ((inc or {}).get("result") or []) if r.get("number") == TICKET]
    if not result:
        sys.exit(f"trigger incident {TICKET} not found")
    print(f"[trigger] {TICKET}: {result[0].get('short_description','')}")

    store_paths = {c["name"] for c in (hp_get("/storage/ssl_certificates") or [])}
    inv = request(SN, "GET", "/api/now/table/cmdb_ci_certificate?sysparm_limit=1000")
    certs = {}
    for r in ((inv or {}).get("result") or []):
        path = r.get("u_deployed_path")
        if path:
            certs[path] = {"name": path, "not_after": r.get("valid_to"),
                           "sans": (r.get("u_san") or "").split(","), "subject": r.get("subject")}
    frontends = hp_get("/configuration/frontends") or []
    a_records = request(DNS, "GET", "/wapi/v2.14/record:a") or []
    vip_to_fqdn = {}
    for rec in a_records:
        ip = rec.get("ipv4addr")
        if ip and ip not in vip_to_fqdn:
            vip_to_fqdn[ip] = rec.get("name")

    def host_of(fe_name, binds):
        for b in binds:
            addr = b.get("address")
            if addr and addr in vip_to_fqdn:
                return vip_to_fqdn[addr]
        return None

    def pick_replacement(fqdn):
        cands = [c for c in certs.values()
                 if c["name"] in store_paths and cert_valid(c) and covers(c, fqdn)]
        if not cands:
            raise RuntimeError(f"no valid store cert covers {fqdn} (seed contract broken)")
        return sorted(cands, key=lambda c: c["name"])[0]["name"]

    plan = []
    for fe in frontends:
        fe_name = fe["name"]
        binds = hp_get(f"/configuration/frontends/{fe_name}/binds") or []
        suses = hp_get(f"/configuration/frontends/{fe_name}/ssl_front_uses") or []
        needs = False
        pending = []
        for su in suses:
            cur = certs.get(su.get("certificate"))
            pending.append(("suse", su.get("index"), su.get("certificate"), cur))
        for b in binds:
            if b.get("ssl_certificate"):
                cur = certs.get(b.get("ssl_certificate"))
                pending.append(("bind", b.get("name"), b.get("ssl_certificate"), cur))
        fqdn = host_of(fe_name, binds)
        for kind, key, curname, cur in pending:
            bad = (cur is None) or (not cert_valid(cur)) or (fqdn and not covers(cur, fqdn))
            if bad:
                needs = True
        if not needs:
            continue
        if not fqdn:
            raise RuntimeError(f"frontend {fe_name} has a broken binding but no resolvable host")
        good = pick_replacement(fqdn)
        for kind, key, curname, cur in pending:
            bad = (cur is None) or (not cert_valid(cur)) or (not covers(cur, fqdn))
            if bad and curname != good:
                plan.append((kind, fe_name, key, curname, good, fqdn))

    print(f"[plan] {len(plan)} binding(s) to remediate:")
    for kind, fe_name, key, old, new, fqdn in plan:
        print(f"    {fe_name} [{kind}:{key}] {fqdn}: {old} -> {new}")

    for kind, fe_name, key, old, new, fqdn in plan:
        if kind == "suse":
            request(HP, "PUT",
                    f"/v3/services/haproxy/configuration/frontends/{fe_name}/ssl_front_uses/{key}",
                    {"index": int(key), "certificate": new})
        else:
            bind = request(HP, "GET",
                           f"/v3/services/haproxy/configuration/frontends/{fe_name}/binds/{key}")
            payload = {k: v for k, v in bind.items() if k not in ("created_at", "created_by")}
            payload["ssl_certificate"] = new
            request(HP, "PUT",
                    f"/v3/services/haproxy/configuration/frontends/{fe_name}/binds/{key}", payload)

    certs2 = certs
    mismatches = []
    for kind, fe_name, key, old, new, fqdn in plan:
        if kind == "suse":
            row = request(HP, "GET",
                          f"/v3/services/haproxy/configuration/frontends/{fe_name}/ssl_front_uses/{key}")
            got = row.get("certificate")
        else:
            row = request(HP, "GET",
                          f"/v3/services/haproxy/configuration/frontends/{fe_name}/binds/{key}")
            got = row.get("ssl_certificate")
        if got != new:
            mismatches.append(f"{fe_name}[{kind}:{key}] expected {new} got {got}")

    for fe in hp_get("/configuration/frontends") or []:
        fe_name = fe["name"]
        binds = hp_get(f"/configuration/frontends/{fe_name}/binds") or []
        suses = hp_get(f"/configuration/frontends/{fe_name}/ssl_front_uses") or []
        fqdn = host_of(fe_name, binds)
        surfaces = [("suse", su.get("certificate")) for su in suses]
        surfaces += [("bind", b.get("ssl_certificate")) for b in binds if b.get("ssl_certificate")]
        for kind, cname in surfaces:
            cur = certs2.get(cname)
            if cur is None or not cert_valid(cur):
                mismatches.append(f"residual expiring binding {fe_name}[{kind}] -> {cname}")
            elif fqdn and not covers(cur, fqdn):
                mismatches.append(f"residual host-mismatch {fe_name}[{kind}] {fqdn} -> {cname}")

    if mismatches:
        print("[FAIL] readback/invariant mismatches:")
        for m in mismatches:
            print("   ", m)
        sys.exit(1)
    print("[OK] all remediations applied; estate invariant holds.")

if __name__ == "__main__":
    main()
