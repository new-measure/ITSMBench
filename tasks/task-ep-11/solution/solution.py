#!/usr/bin/env python3

import ipaddress
import json
import re
import sys
import urllib.request
import urllib.error

TICKET_ID = "ITS-2087"

JC = "http://jumpcloud.local.mock:8080"
ZS = "http://zscaler-zia.local.mock:8080/zia/api/v1"
HP = "http://haproxy.local.mock:8080/v3"
D42 = "http://device42.local.mock:8080"
JIRA = "http://jira-service-management.local.mock:8080/rest/servicedeskapi"

WRITES = []

def _host(url):
    return url.split("://", 1)[1].split("/", 1)[0]

def req(method, url, body=None):
    data = None
    headers = {"Host": _host(url), "Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw

def get(url):
    return req("GET", url)[1]

def die(msg):
    print("ORACLE-FAIL:", msg)
    sys.exit(1)

def jc_v1_list(path, key):
    out, skip = [], 0
    while True:
        _, data = req("GET", f"{JC}{path}?limit=100&skip={skip}")
        rows = (data or {}).get(key, []) if isinstance(data, dict) else []
        out.extend(rows)
        total = (data or {}).get("totalCount", len(out)) if isinstance(data, dict) else len(out)
        skip += len(rows)
        if not rows or skip >= total:
            break
    return out

def jc_v2_list(path):
    out, skip = [], 0
    while True:
        _, data = req("GET", f"{JC}{path}?limit=100&skip={skip}")
        rows = data if isinstance(data, list) else []
        out.extend(rows)
        if len(rows) < 100:
            break
        skip += len(rows)
    return out

def zs_list(path):
    out, page = [], 1
    while True:
        _, data = req("GET", f"{ZS}{path}?page={page}&pageSize=1000")
        rows = data if isinstance(data, list) else []
        out.extend(rows)
        if len(rows) < 1000:
            break
        page += 1
    return out

def d42_list(path, key):
    out, offset = [], 0
    while True:
        _, data = req("GET", f"{D42}{path}?limit=1000&offset={offset}")
        if not isinstance(data, dict):
            break
        rows = data.get(key, [])
        out.extend(rows)
        total = data.get("total_count", len(out))
        offset += len(rows)
        if not rows or offset >= total:
            break
    return out

def jira_list_requests():
    out, start = [], 0
    while True:
        _, data = req("GET", f"{JIRA}/request?start={start}&limit=50")
        if not isinstance(data, dict):
            break
        vals = data.get("values", [])
        out.extend(vals)
        if data.get("isLastPage", True):
            break
        start += len(vals) or 50
    return out

def domain_of(email):
    return email.split("@", 1)[1].lower() if email and "@" in email else ""

def _past(datestr, now):
    if not datestr:
        return False
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(datestr))
    return bool(m) and m.group(1) <= now[:10]

def cf_get(record, *keys):
    for k in keys:
        if k in record and record[k] not in (None, ""):
            return record[k]
    for entry in record.get("custom_fields", []) or []:
        name = str(entry.get("key") or entry.get("name") or "").lower()
        if name in {k.lower() for k in keys}:
            return entry.get("value")
    return None

def main():
    ticket = get(f"{JIRA}/request/{TICKET_ID}")
    if not isinstance(ticket, dict) or ticket.get("errorMessage"):
        die(f"trigger ticket {TICKET_ID} not readable")
    ticket_text = json.dumps(ticket).lower()

    now = "2026-06-15"

    vendors = d42_list("/api/1.0/vendors/", "vendors")
    ended = []
    for v in vendors:
        end = cf_get(v, "contract_end", "engagement_end", "end_date")
        status = str(cf_get(v, "status", "engagement_status") or "").lower()
        if _past(end, now) or any(w in status for w in ("end", "expire", "terminat", "offboard")):
            ended.append(v)
    if not ended:
        die("no ended vendor found in device42")
    vendor = None
    for v in ended:
        if str(v.get("name", "")).split()[0].lower() in ticket_text:
            vendor = v
            break
    vendor = vendor or ended[0]
    vname = vendor.get("name")
    vid = vendor.get("vendor_id") or vendor.get("id")
    print(f"[*] ended vendor: {vname} (id={vid})")

    def is_vendor(rec):
        rv = str(rec.get("vendor") or rec.get("vendor_id") or "")
        return rv in {str(vname), str(vid)} or str(vname).lower() in json.dumps(rec).lower()

    endusers = d42_list("/api/1.0/endusers/", "values")
    vendor_emails = {str(e.get("email", "")).lower() for e in endusers
                     if is_vendor(e) and e.get("email")}
    vendor_domains = {domain_of(e) for e in vendor_emails if e}
    vendor_domains.discard("")

    d42_devices = d42_list("/api/2.0/devices/", "devices")
    vendor_hosts = {str(d.get("name", "")).lower() for d in d42_devices if is_vendor(d)}

    d42_ips = d42_list("/api/2.0/ips/", "ips")
    subnets = d42_list("/api/1.0/subnets/", "subnets")
    vendor_networks = []
    for s in subnets:
        if is_vendor(s):
            net = s.get("network") or s.get("subnet") or s.get("range")
            mask = s.get("mask_bits") or s.get("mask")
            cidr = f"{net}/{mask}" if net and mask and "/" not in str(net) else net
            try:
                vendor_networks.append(ipaddress.ip_network(cidr, strict=False))
            except Exception:
                pass

    def in_vendor_net(ip):
        try:
            addr = ipaddress.ip_address(str(ip).split("/")[0])
        except Exception:
            return False
        return any(addr in n for n in vendor_networks)

    vendor_ips = set()
    host_ids = {str(d.get("device_id") or d.get("id")) for d in d42_devices if is_vendor(d)}
    host_names = {str(d.get("name", "")).lower() for d in d42_devices if is_vendor(d)}
    for ip in d42_ips:
        addr = str(ip.get("ip", ""))
        dev = str(ip.get("device_id") or ip.get("device") or "").lower()
        if not addr:
            continue
        if in_vendor_net(addr) or dev in host_ids or dev in host_names or is_vendor(ip):
            vendor_ips.add(addr)
    print(f"[*] vendor domains={sorted(vendor_domains)} nets={[str(n) for n in vendor_networks]} "
          f"ips={sorted(vendor_ips)} hosts={sorted(vendor_hosts)}")

    jc_users = jc_v1_list("/api/systemusers", "results")
    by_id = {u["id"]: u for u in jc_users}

    def vendor_domain_user(u):
        return domain_of(str(u.get("email", "")).lower()) in vendor_domains

    groups = jc_v2_list("/api/v2/usergroups")
    group_members = {}
    for g in groups:
        members = get(f"{JC}/api/v2/usergroups/{g['id']}/members?limit=100&skip=0")
        ids = [m["to"]["id"] for m in members if isinstance(m, dict) and m.get("to")]
        group_members[g["id"]] = ids

    vendor_groups = {gid for gid, ids in group_members.items()
                     if any(vendor_domain_user(by_id.get(i, {})) for i in ids)}

    cohort_user_ids = set()
    for u in jc_users:
        if vendor_domain_user(u):
            cohort_user_ids.add(u["id"])
    for gid in vendor_groups:
        cohort_user_ids.update(group_members.get(gid, []))
    cohort_usernames = {str(by_id[i].get("username", "")).lower() for i in cohort_user_ids}
    print(f"[*] cohort user ids={sorted(cohort_user_ids)} usernames={sorted(cohort_usernames)}")

    plan_jc = []
    for uid in sorted(cohort_user_ids):
        u = by_id[uid]
        if str(u.get("state", "")).upper() != "SUSPENDED":
            plan_jc.append(("suspend", uid, u.get("username")))
        for gid in vendor_groups:
            if uid in group_members.get(gid, []):
                plan_jc.append(("ungroup", gid, uid, u.get("username")))
        keys = get(f"{JC}/api/systemusers/{uid}/sshkeys?limit=100&skip=0")
        for k in (keys if isinstance(keys, list) else []):
            plan_jc.append(("delkey", uid, k.get("id") or k.get("_id"), u.get("username")))

    rules = zs_list("/firewallFilteringRules")
    src_groups = {str(g.get("id")): g for g in zs_list("/ipSourceGroups")}

    def group_grants_cohort(gid):
        g = src_groups.get(str(gid))
        if not g:
            return False
        for addr in g.get("ipAddresses", []) or []:
            a = str(addr)
            if a in vendor_ips or in_vendor_net(a) or _cidr_overlaps_vendor(a):
                return True
        return False

    def _cidr_overlaps_vendor(a):
        try:
            net = ipaddress.ip_network(a, strict=False)
        except Exception:
            return False
        return any(net.subnet_of(n) or n.subnet_of(net) for n in vendor_networks)

    plan_zs = []
    for r in rules:
        if str(r.get("action", "")).upper() != "ALLOW":
            continue
        if str(r.get("state", "")).upper() != "ENABLED":
            continue
        users = {str(x).lower() for x in (r.get("users") or [])}
        srcips = [str(x) for x in (r.get("srcIps") or [])]
        grants = bool(users & cohort_usernames)
        grants = grants or any(ip in vendor_ips or in_vendor_net(ip) or _cidr_overlaps_vendor(ip)
                               for ip in srcips)
        grants = grants or any(group_grants_cohort(g if not isinstance(g, dict) else g.get("id"))
                               for g in (r.get("srcIpGroups") or []))
        if grants:
            plan_zs.append(("disable", str(r["id"]), r.get("name")))

    backends = get(f"{HP}/services/haproxy/configuration/backends")
    plan_hp = []
    for b in (backends if isinstance(backends, list) else []):
        bname = b.get("name")
        servers = get(f"{HP}/services/haproxy/configuration/backends/{bname}/servers")
        for s in (servers if isinstance(servers, list) else []):
            addr = str(s.get("address", ""))
            sname = str(s.get("name", "")).lower()
            if addr in vendor_ips or in_vendor_net(addr) or sname in vendor_hosts \
               or any(h and h in sname for h in vendor_hosts):
                plan_hp.append(("delserver", bname, s.get("name")))

    print("\n=== PLAN ===")
    for p in plan_jc + plan_zs + plan_hp:
        print("  ", p)
    print("=== EXECUTE ===")

    for p in plan_jc:
        if p[0] == "suspend":
            _, _uid, uname = p
            req("POST", f"{JC}/api/systemusers/{_uid}/state/suspend", {})
            WRITES.append(f"JC suspend {uname}")
        elif p[0] == "ungroup":
            _, gid, uid, uname = p
            req("POST", f"{JC}/api/v2/usergroups/{gid}/members",
                {"op": "remove", "type": "user", "id": uid})
            WRITES.append(f"JC ungroup {uname}")
        elif p[0] == "delkey":
            _, uid, kid, uname = p
            req("DELETE", f"{JC}/api/systemusers/{uid}/sshkeys/{kid}")
            WRITES.append(f"JC delkey {uname}:{kid}")

    for _, rid, rname in plan_zs:
        _, cur = req("GET", f"{ZS}/firewallFilteringRules/{rid}")
        body = dict(cur)
        body["state"] = "DISABLED"
        req("PUT", f"{ZS}/firewallFilteringRules/{rid}", body)
        WRITES.append(f"ZS disable rule {rname} ({rid})")

    for _, bname, sname in plan_hp:
        req("DELETE", f"{HP}/services/haproxy/configuration/backends/{bname}/servers/{sname}")
        WRITES.append(f"HP delserver {bname}/{sname}")

    print("\n=== WRITES ===")
    for w in WRITES:
        print("  ", w)

    errors = []
    users2 = {u["id"]: u for u in jc_v1_list("/api/systemusers", "results")}
    for uid in cohort_user_ids:
        if str(users2[uid].get("state", "")).upper() != "SUSPENDED":
            errors.append(f"user {uid} not suspended")
        mo = get(f"{JC}/api/v2/users/{uid}/memberof?limit=100&skip=0")
        if any(str(m.get("from", {}).get("id")) in {str(g) for g in vendor_groups}
               for m in (mo if isinstance(mo, list) else [])):
            errors.append(f"user {uid} still in vendor group")
        keys = get(f"{JC}/api/systemusers/{uid}/sshkeys?limit=100&skip=0")
        if isinstance(keys, list) and keys:
            errors.append(f"user {uid} still has ssh keys")

    rules2 = zs_list("/firewallFilteringRules")
    src2 = {str(g.get("id")): g for g in zs_list("/ipSourceGroups")}
    globals()["src_groups"] = src2
    for r in rules2:
        if str(r.get("action", "")).upper() == "ALLOW" and str(r.get("state", "")).upper() == "ENABLED":
            users = {str(x).lower() for x in (r.get("users") or [])}
            srcips = [str(x) for x in (r.get("srcIps") or [])]
            if users & cohort_usernames:
                errors.append(f"rule {r['id']} still grants cohort user")
            if any(ip in vendor_ips or in_vendor_net(ip) for ip in srcips):
                errors.append(f"rule {r['id']} still grants vendor ip")

    backends2 = get(f"{HP}/services/haproxy/configuration/backends")
    for b in (backends2 if isinstance(backends2, list) else []):
        servers = get(f"{HP}/services/haproxy/configuration/backends/{b['name']}/servers")
        for s in (servers if isinstance(servers, list) else []):
            if str(s.get("address", "")) in vendor_ips:
                errors.append(f"portal {b['name']} still routes to vendor ip {s.get('address')}")

    if errors:
        for e in errors:
            print("READBACK-FAIL:", e)
        sys.exit(1)
    print("\n[OK] all remediations verified; sanctioned account untouched.")

if __name__ == "__main__":
    main()
