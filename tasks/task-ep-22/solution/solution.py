#!/usr/bin/env python3

import json
import sys
import urllib.parse
import urllib.request

TICKET = "INC0010042"

HAP = "http://haproxy.local.mock:8080"
IBX = "http://infoblox-nios.local.mock:8080"
D42 = "http://device42.local.mock:8080"
SNOW = "http://servicenow.local.mock:8080"
PD = "http://pagerduty.local.mock:8080"

WRITES = []

def _req(method, url, body=None, headers=None):
    data = None
    hdrs = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        return e.code, raw
    return 200, raw

def get_json(url):
    code, raw = _req("GET", url)
    try:
        return json.loads(raw)
    except Exception:
        return raw

def die(msg):
    print("SOLUTION-ABORT:", msg)
    sys.exit(2)

def hap_list(path):
    return get_json(HAP + path)

def hap_version():
    return int(get_json(HAP + "/v3/services/haproxy/configuration/version"))

def ibx_a_records():
    return get_json(IBX + "/wapi/v2.14/record:a?_max_results=1000")

def d42_all(path, key):
    out = []
    offset = 0
    while True:
        env = get_json(D42 + f"{path}?limit=1000&offset={offset}")
        rows = env.get(key, []) if isinstance(env, dict) else []
        out.extend(rows)
        total = env.get("total_count", len(out)) if isinstance(env, dict) else len(out)
        offset += 1000
        if offset >= total or not rows:
            break
    return out

def snow_table(table, query=None):
    url = SNOW + f"/api/now/table/{table}?sysparm_limit=1000"
    if query:
        url += "&sysparm_query=" + urllib.parse.quote(query)
    return get_json(url).get("result", [])

def pd_all(path, key):
    out = []
    offset = 0
    while True:
        env = get_json(PD + f"{path}?limit=100&offset={offset}")
        rows = env.get(key, []) if isinstance(env, dict) else []
        out.extend(rows)
        if not isinstance(env, dict) or not env.get("more"):
            break
        offset += 100
    return out

def ip_only(addr):
    return str(addr or "").split(":")[0].strip()

def main():
    inc = snow_table("incident", f"number={TICKET}")
    if not inc:
        die(f"trigger incident {TICKET} not found")
    print("TRIGGER:", inc[0].get("number"), "-", inc[0].get("short_description"))

    changes = snow_table("change_request")
    cohort = {}
    for ch in changes:
        if str(ch.get("u_source_dc", "")).lower() == "ord1" and \
           str(ch.get("u_target_dc", "")).lower() == "dfw2":
            svc = str(ch.get("u_service", "")).strip()
            if svc:
                cohort[svc] = ch
    if not cohort:
        die("no ord1->dfw2 cutover change_requests found")
    print("COHORT:", sorted(cohort))

    devices = d42_all("/api/1.0/devices/", "devices")
    ips = d42_all("/api/2.0/ips/", "ips")
    sinsts = d42_all("/api/2.0/service_instances/", "service_details")
    a_recs = ibx_a_records()
    backends = hap_list("/v3/services/haproxy/configuration/backends")
    cmdb = snow_table("cmdb_ci_server")
    pd_incidents = pd_all("/incidents", "incidents")
    pd_users = pd_all("/users", "users")

    dev_by_name = {str(d.get("name", "")): d for d in devices}
    dev_by_id = {str(d.get("device_id") or d.get("id")): d for d in devices}
    ip_by_devid = {}
    ip_owner = {}
    for ipr in ips:
        did = ipr.get("device_id")
        if did is not None:
            ip_by_devid.setdefault(str(did), []).append(ipr)
            owner = dev_by_id.get(str(did))
            if owner:
                ip_owner[ip_only(ipr.get("ip"))] = str(owner.get("name", ""))

    def device_ip(devname):
        d = dev_by_name.get(devname)
        if not d:
            return None
        for ipr in ip_by_devid.get(str(d.get("device_id") or d.get("id")), []):
            return ip_only(ipr.get("ip"))
        return None

    def new_ip(svc):
        return device_ip(f"{svc}-dfw2-01")

    def new_dev(svc):
        return dev_by_name.get(f"{svc}-dfw2-01")

    def prefix16(ip):
        parts = ip_only(ip).split(".")
        return ".".join(parts[:2]) if len(parts) == 4 else ""

    def dominant(pred):
        counts = {}
        for rec in a_recs:
            if pred(str(rec.get("name", ""))):
                p = prefix16(rec.get("ipv4addr"))
                if p:
                    counts[p] = counts.get(p, 0) + 1
        return max(counts, key=counts.get) if counts else ""

    OLD16 = dominant(lambda n: ".ord1." in n)
    NEW16 = dominant(lambda n: ".dfw2." in n)
    if not OLD16 or not NEW16:
        die(f"could not derive DC prefixes (old={OLD16!r} new={NEW16!r})")
    print("PREFIXES: old", OLD16, "new", NEW16)

    def in_old(ip):
        return ip_only(ip).startswith(OLD16 + ".")

    def in_new(ip):
        return ip_only(ip).startswith(NEW16 + ".")

    from_email = None
    for u in pd_users:
        if u.get("email"):
            from_email = u["email"]
            break

    decommissioned_ips = set()
    for svc in cohort:
        for ci in cmdb:
            if str(ci.get("name", "")) == f"{svc}-ord1-01" and in_old(ci.get("ip_address")):
                decommissioned_ips.add(ip_only(ci.get("ip_address")))

    plan = []

    for b in backends:
        be = str(b.get("name"))
        servers = hap_list(f"/v3/services/haproxy/configuration/backends/{be}/servers")
        if not isinstance(servers, list):
            continue
        for s in servers:
            if ip_only(s.get("address")) in decommissioned_ips:
                plan.append((f"haproxy delete server {be}/{s['name']} ({ip_only(s.get('address'))})",
                             lambda be=be, name=s["name"]: hap_delete_server(be, name)))

    for svc in sorted(cohort):
        nip = new_ip(svc)
        if not nip or not in_new(nip):
            print(f"  [{svc}] no dfw2 footprint; skipping")
            continue

        be = f"be_{svc}"
        if any(str(b.get("name")) == be for b in backends):
            for s in hap_list(f"/v3/services/haproxy/configuration/backends/{be}/servers") or []:
                a = ip_only(s.get("address"))
                if in_new(a) and a != nip:
                    owner = ip_owner.get(a, "")
                    if owner and not owner.startswith(f"{svc}-"):
                        plan.append((f"haproxy repoint {be}/{s['name']} {a}->{nip} (was {owner})",
                                     lambda be=be, s=s, nip=nip: hap_replace_server(be, s, nip)))

        for rec in a_recs:
            if str(rec.get("name", "")) == f"{svc}.meridian.internal" and ip_only(rec.get("ipv4addr")) != nip:
                plan.append((f"dns repoint {rec['name']} {ip_only(rec.get('ipv4addr'))}->{nip}",
                             lambda ref=rec["_ref"], nip=nip: ibx_update_a(ref, nip)))

        for si in sinsts:
            if str(si.get("service_display_name", "")).strip() == svc and in_old(si.get("ipaddress")):
                ndev = new_dev(svc)
                oldip = ip_only(si.get("ipaddress"))
                plan.append((f"d42 repoint service_instance {svc} {oldip}->{nip}",
                             lambda sid=si.get("service_detail_id") or si.get("id"), nip=nip, ndev=ndev:
                             d42_update_sinst(sid, nip, ndev)))
                for ipr in ips:
                    if ip_only(ipr.get("ip")) == oldip and str(ipr.get("available", "")).lower() != "yes":
                        plan.append((f"d42 free ip {oldip}", lambda oldip=oldip: d42_clear_ip(oldip)))
                        break

        for ci in cmdb:
            if str(ci.get("name", "")) == f"{svc}-ord1-01":
                if str(ci.get("install_status", "")) not in ("7", "retired") and \
                   str(ci.get("operational_status", "")).lower() not in ("6", "retired"):
                    plan.append((f"snow retire CI {ci['name']}",
                                 lambda sid=ci["sys_id"]: snow_retire_ci(sid)))

        for pi in pd_incidents:
            title = (pi.get("title") or "") + " " + json.dumps(pi.get("service") or {})
            if f"{svc}-ord1" in title and pi.get("status") in ("triggered", "acknowledged"):
                if from_email:
                    plan.append((f"pd resolve incident {pi.get('id')} ({svc}-ord1)",
                                 lambda iid=pi["id"], em=from_email: pd_resolve(iid, em)))

    if not plan:
        print("NO ACTIONS PLANNED")
    for label, fn in plan:
        print("PLAN:", label)

    for label, fn in plan:
        fn()
        print("DID:", label)

    verify(cohort, new_ip, in_new, decommissioned_ips)
    print("WRITES:", len(WRITES))
    print("SOLUTION-OK")

def hap_delete_server(be, name):
    v = hap_version()
    code, raw = _req("DELETE", HAP + f"/v3/services/haproxy/configuration/backends/{be}/servers/{urllib.parse.quote(str(name))}?version={v}")
    if code not in (200, 202, 204):
        die(f"haproxy delete {be}/{name} -> {code} {raw}")
    WRITES.append(("hap_delete", be, name))

def hap_replace_server(be, server, ip):
    v = hap_version()
    name = server["name"]
    body = {k: server[k] for k in ("name", "port", "check") if k in server}
    body["name"] = name
    body["address"] = ip
    code, raw = _req("PUT", HAP + f"/v3/services/haproxy/configuration/backends/{be}/servers/{urllib.parse.quote(str(name))}?version={v}", body=body)
    if code not in (200, 202):
        die(f"haproxy replace {be}/{name} -> {code} {raw}")
    WRITES.append(("hap_replace", be, name, ip))

def ibx_update_a(ref, ip):
    enc = urllib.parse.quote(ref, safe="")
    code, raw = _req("PUT", IBX + f"/wapi/v2.14/record:a/{enc}", body={"ipv4addr": ip})
    if code not in (200, 201):
        die(f"infoblox update {ref} -> {code} {raw}")
    WRITES.append(("dns_update", ref, ip))

def d42_update_sinst(sid, ip, ndev):
    body = {"service_detail_id": sid, "ipaddress": ip}
    if ndev:
        body["device_id"] = ndev.get("device_id") or ndev.get("id")
        body["device_name"] = ndev.get("name")
    code, raw = _req("POST", D42 + "/api/2.0/service_instances/", body=body)
    if code not in (200, 201):
        die(f"d42 service_instance update {sid} -> {code} {raw}")
    WRITES.append(("d42_sinst", sid, ip))

def d42_clear_ip(ip):
    code, raw = _req("POST", D42 + "/api/1.0/clear_ip/", body={"ip": ip})
    if code not in (200, 201):
        die(f"d42 clear_ip {ip} -> {code} {raw}")
    WRITES.append(("d42_clear_ip", ip))

def snow_retire_ci(sid):
    code, raw = _req("PATCH", SNOW + f"/api/now/table/cmdb_ci_server/{sid}",
                     body={"install_status": "7", "operational_status": "6"})
    if code not in (200,):
        die(f"snow retire CI {sid} -> {code} {raw}")
    WRITES.append(("snow_retire", sid))

def pd_resolve(iid, email):
    code, raw = _req("PUT", PD + f"/incidents/{iid}",
                     body={"incident": {"type": "incident_reference", "status": "resolved"}},
                     headers={"From": email})
    if code not in (200,):
        die(f"pd resolve {iid} -> {code} {raw}")
    WRITES.append(("pd_resolve", iid))

def verify(cohort, new_ip, in_new, decommissioned_ips):
    backends = hap_list("/v3/services/haproxy/configuration/backends")
    for b in backends:
        be = str(b.get("name"))
        servers = hap_list(f"/v3/services/haproxy/configuration/backends/{be}/servers")
        if isinstance(servers, list):
            if any(ip_only(s.get("address")) in decommissioned_ips for s in servers):
                die(f"verify: {be} still routes to a decommissioned ord1 host")
    a_recs = ibx_a_records()
    for svc in cohort:
        nip = new_ip(svc)
        for rec in a_recs:
            if str(rec.get("name", "")) == f"{svc}.meridian.internal":
                if nip and ip_only(rec.get("ipv4addr")) != nip:
                    die(f"verify: A {rec['name']} != own dfw2 host {nip}")
    print("VERIFY-OK")

if __name__ == "__main__":
    main()
