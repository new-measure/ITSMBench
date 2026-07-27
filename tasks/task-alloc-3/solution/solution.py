#!/usr/bin/env python3
import json
import sys
import urllib.parse
import urllib.request
import urllib.error

SUBNET_PREFIX = "10.20.30."
USABLE_HOSTS = range(1, 63)
NEED = 8

D42 = "http://device42.local.mock:8080"
HAP = "http://haproxy.local.mock:8080/v3"
IBX = "http://infoblox-nios.local.mock:8080/wapi/v2.14"

def _req(method, url, body=None):
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        raise RuntimeError(f"{method} {url} -> {e.code}: {raw[:300]}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw

def get(url):
    return _req("GET", url)

def post(url, body):
    return _req("POST", url, body)

def delete(url):
    return _req("DELETE", url)

def d42_list(collection):
    out = []
    offset = 0
    limit = 1000
    while True:
        page = get(f"{D42}/api/2.0/{collection}/?limit={limit}&offset={offset}")
        rows = page.get(collection, []) if isinstance(page, dict) else []
        out.extend(rows)
        total = page.get("total_count", len(out)) if isinstance(page, dict) else len(out)
        offset += limit
        if offset >= total or not rows:
            break
    return out

def norm(v):
    return "" if v is None else str(v)

def is_false(v):
    return norm(v).strip().lower() in ("false", "0", "no", "n")

def main():
    ips = d42_list("ips")
    devices = d42_list("devices")
    print(f"[discovery] device42: {len(ips)} ip records, {len(devices)} devices")

    dev_by_id = {norm(d.get("device_id") or d.get("id")): d for d in devices}
    dev_by_name = {norm(d.get("name")).lower(): d for d in devices if d.get("name")}

    def holder_retired(ip_row):
        d = None
        did = ip_row.get("device_id")
        if did is not None:
            d = dev_by_id.get(norm(did))
        if d is None and ip_row.get("device"):
            d = dev_by_name.get(norm(ip_row.get("device")).lower())
        if d is None:
            return False
        return is_false(d.get("in_service"))

    frontends = get(f"{HAP}/services/haproxy/configuration/frontends")
    wired = set()
    for ft in frontends:
        if ft.get("default_backend"):
            wired.add(ft["default_backend"])
        for rule in ft.get("backend_switching_rules", []) or []:
            if rule.get("name"):
                wired.add(rule["name"])

    def resolve_addr(addr):
        if addr and addr[0].isdigit():
            return {addr}
        ips_out = set()
        for rec in (get(f"{IBX}/record:a?name={urllib.parse.quote(addr)}") or []):
            ips_out.add(norm(rec.get("ipv4addr")))
        short = addr.split(".")[0].lower() if addr else ""
        d = dev_by_name.get(short)
        if d is not None:
            did = norm(d.get("device_id") or d.get("id"))
            for r in ips:
                if norm(r.get("device_id")) == did:
                    ips_out.add(norm(r.get("ip")))
        return {a for a in ips_out if a}

    live_addrs = set()
    for be in get(f"{HAP}/services/haproxy/configuration/backends"):
        name = be.get("name")
        if name not in wired:
            continue
        for srv in get(f"{HAP}/services/haproxy/configuration/backends/{name}/servers"):
            if norm(srv.get("maintenance")).strip().lower() in ("enabled", "true", "1"):
                continue
            live_addrs |= resolve_addr(norm(srv.get("address")))
    for ft in frontends:
        for bind in get(f"{HAP}/services/haproxy/configuration/frontends/{ft.get('name')}/binds"):
            addr = norm(bind.get("address"))
            if addr:
                live_addrs.add(addr)
    print(f"[discovery] haproxy: wired={sorted(wired)}; live addresses={sorted(a for a in live_addrs if a.startswith(SUBNET_PREFIX))}")

    subnet_targets = {f"{SUBNET_PREFIX}{h}" for h in USABLE_HOSTS}
    reclaimable = []
    preserved_retired = []
    for row in ips:
        addr = norm(row.get("ip"))
        if addr not in subnet_targets:
            continue
        if not holder_retired(row):
            continue
        if addr in live_addrs:
            preserved_retired.append(addr)
            continue
        reclaimable.append((addr, norm(row.get("label") or row.get("device"))))

    reclaimable.sort(key=lambda t: [int(x) for x in t[0].split(".")])
    print(f"[plan] retired-but-preserved (live traffic): {sorted(preserved_retired)}")
    print(f"[plan] reclaimable ({len(reclaimable)}): {[a for a, _ in reclaimable]}")

    if len(reclaimable) < NEED:
        print(f"FATAL: only {len(reclaimable)} safely reclaimable, need {NEED}", file=sys.stderr)
        sys.exit(2)

    freed = []
    for addr, who in reclaimable:
        resp = post(f"{D42}/api/1.0/clear_ip/", {"ip": addr})
        print(f"[write] clear_ip {addr} ({who}) -> {resp.get('msg') if isinstance(resp, dict) else resp}")
        freed.append(addr)

    dns_deleted = []
    for addr in freed:
        recs = get(f"{IBX}/record:a?ipv4addr={addr}")
        for rec in (recs if isinstance(recs, list) else []):
            ref = urllib.parse.quote(str(rec.get("_ref")), safe="")
            delete(f"{IBX}/record:a/{ref}")
            print(f"[write] delete DNS {rec.get('name')} -> {addr}")
            dns_deleted.append(addr)

    ips_after = d42_list("ips")
    by_addr = {norm(r.get("ip")): r for r in ips_after}
    mism = 0
    for addr in freed:
        r = by_addr.get(addr)
        if r is not None and norm(r.get("available")).lower() != "yes":
            print(f"MISMATCH: {addr} still allocated after clear_ip", file=sys.stderr)
            mism += 1
    for addr in preserved_retired:
        r = by_addr.get(addr)
        if r is None or norm(r.get("available")).lower() == "yes":
            print(f"MISMATCH: preserved {addr} was freed", file=sys.stderr)
            mism += 1
    for addr in freed:
        for rec in (get(f"{IBX}/record:a?ipv4addr={addr}") or []):
            if str(rec.get("disable")).lower() != "true":
                print(f"MISMATCH: DNS still resolves to freed {addr}", file=sys.stderr)
                mism += 1
    if mism:
        print(f"FATAL: {mism} readback mismatches", file=sys.stderr)
        sys.exit(3)

    print(f"[done] reclaimed {len(freed)} addresses in {SUBNET_PREFIX}0/26 "
          f"and deprovisioned {len(dns_deleted)} stale DNS records; "
          f"requirement of {NEED} satisfied.")

if __name__ == "__main__":
    main()
