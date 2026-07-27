#!/usr/bin/env python3
import http.client, json, os, re, sys, urllib.parse

TRIGGER_TICKET = "SECOPS-4471"

LOCAL = os.environ.get("TASKGEN_LOCAL_MOCK", "").strip()
def _conn(slug):
    vhost = "%s.local.mock:8080" % slug
    if LOCAL:
        host, port = LOCAL.split(":")
        c = http.client.HTTPConnection(host, int(port), timeout=30)
    else:
        c = http.client.HTTPConnection("%s.local.mock" % slug, 8080, timeout=30)
    return c, vhost

def request(slug, method, path, query=None, body=None, headers=None):
    c, vhost = _conn(slug)
    if query:
        path = path + ("&" if "?" in path else "?") + urllib.parse.urlencode(query)
    hdrs = {"Host": vhost, "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    if headers:
        hdrs.update(headers)
    c.request(method, path, body=data, headers=hdrs)
    r = c.getresponse()
    raw = r.read()
    c.close()
    if r.status >= 400:
        raise RuntimeError("%s %s -> %d: %s" % (method, path, r.status, raw[:300]))
    try:
        return json.loads(raw)
    except Exception:
        return raw.decode(errors="replace")

def vpc(action, **params):
    q = {"Action": action, "Version": "2016-11-15"}
    q.update({k: v for k, v in params.items() if v is not None})
    return request("aws-vpc", "GET", "/", query=q)

def vpc_items(resp, set_name):
    node = resp.get(set_name) or {}
    items = node.get("item", [])
    if isinstance(items, dict):
        items = [items]
    return items

def d42_device_by_name(name):
    resp = request("device42", "GET", "/api/2.0/devices/", query={"name": name, "limit": 1000})
    for d in resp.get("devices", []):
        if d.get("name") == name:
            return d
    return None

def d42_device_by_ip(ip):
    resp = request("device42", "GET", "/api/2.0/ips/", query={"ip": ip, "limit": 1000})
    rows = resp.get("ips", [])
    for row in rows:
        if row.get("ip") == ip and row.get("device"):
            return d42_device_by_name(row["device"])
    return None

def jsm_request(key):
    return request("jira-service-management", "GET",
                   "/rest/servicedeskapi/request/%s" % key,
                   query={"api-version": "1"})

def jsm_all_requests():
    resp = request("jira-service-management", "GET", "/rest/servicedeskapi/request",
                   query={"api-version": "1", "limit": 200})
    return resp.get("values", [])

def public_ports_of(sgs, groups):
    ports = set()
    for gid in groups:
        for r in sgs.get(gid, {}).get("IpPermissions", []):
            if rule_is_public(r):
                fp, tp = r.get("FromPort"), r.get("ToPort")
                if fp is None:
                    ports.add("all")
                else:
                    ports.update(range(fp, tp + 1))
    return ports

def is_sanctioned(host, ports):
    dev = d42_device_by_name(host) or {}
    web_ports = ports and ports.issubset({80, 443})
    return (dev.get("service_role") == "web-frontend"
            and dev.get("environment") == "prod"
            and bool(web_ports))

def rule_is_public(rule):
    return any(x.get("CidrIp") == "0.0.0.0/0" for x in rule.get("IpRanges", []))

def revoke_permission(group_id, rule):
    params = {"GroupId": group_id, "IpPermissions.1.IpProtocol": rule["IpProtocol"]}
    if rule.get("FromPort") is not None:
        params["IpPermissions.1.FromPort"] = rule["FromPort"]
        params["IpPermissions.1.ToPort"] = rule["ToPort"]
    idx = 1
    for rng in rule.get("IpRanges", []):
        params["IpPermissions.1.IpRanges.%d.CidrIp" % idx] = rng["CidrIp"]
        idx += 1
    vpc("RevokeSecurityGroupIngress", **params)

def main():
    log = []
    ticket = jsm_request(TRIGGER_TICKET)
    txt = json.dumps(ticket)
    ips = re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", txt)
    ips = [ip for ip in ips if not ip.startswith(("10.", "192.168.")) and ip != "0.0.0.0"]
    if not ips:
        print("ERROR: no public IP in trigger ticket", file=sys.stderr); sys.exit(2)
    flagged_ip = ips[0]
    log.append("trigger flagged IP = %s" % flagged_ip)

    flagged_dev = d42_device_by_ip(flagged_ip)
    if flagged_dev is None:
        print("ERROR: flagged IP not in CMDB", file=sys.stderr); sys.exit(2)
    log.append("flagged host %s tier=%s role=%s" % (flagged_dev["name"], flagged_dev.get("tier"), flagged_dev.get("service_role")))
    if flagged_dev.get("tier") == "internal-data":
        log.append("NOTE flagged host is itself an internal-data resource")

    sgs = {s["GroupId"]: s for s in vpc_items(vpc("DescribeSecurityGroups"), "securityGroupInfo")}
    enis = vpc_items(vpc("DescribeNetworkInterfaces"), "networkInterfaceSet")
    addrs = vpc_items(vpc("DescribeAddresses"), "addressesSet")
    eni_by_id = {}
    for e in enis:
        gs = e.get("GroupSet", {})
        if isinstance(gs, dict) and "item" in gs:
            gs = gs["item"]
        if isinstance(gs, dict):
            gs = [gs]
        e["_groups"] = [g["GroupId"] for g in gs]
        name = None
        for t in (e.get("TagSet") or {}).get("item", []) if isinstance(e.get("TagSet"), dict) else (e.get("TagSet") or []):
            if t.get("Key") == "Name":
                name = t.get("Value")
        e["_host"] = name or e.get("Description")
        eni_by_id[e["NetworkInterfaceId"]] = e

    exposed = set()
    for e in enis:
        if any(rule_is_public(r) for gid in e["_groups"] for r in sgs.get(gid, {}).get("IpPermissions", [])):
            exposed.add(e["NetworkInterfaceId"])
    addr_by_eni = {}
    for a in addrs:
        if a.get("NetworkInterfaceId"):
            addr_by_eni.setdefault(a["NetworkInterfaceId"], []).append(a)

    planned = []
    for eni_id in sorted(exposed):
        e = eni_by_id[eni_id]
        host = e["_host"]
        ports = public_ports_of(sgs, e["_groups"])
        if is_sanctioned(host, ports):
            log.append("SKIP %s (sanctioned public web endpoint)" % host)
            continue
        for gid in e["_groups"]:
            for r in sgs.get(gid, {}).get("IpPermissions", []):
                if rule_is_public(r):
                    planned.append(("revoke", host, gid, r))
        for a in addr_by_eni.get(eni_id, []):
            planned.append(("eip", host, a["AllocationId"], a.get("AssociationId")))

    for act in planned:
        if act[0] == "revoke":
            _, host, gid, r = act
            revoke_permission(gid, r)
            log.append("REVOKE %s %s proto=%s ports=%s-%s" % (host, gid, r["IpProtocol"], r.get("FromPort"), r.get("ToPort")))
        else:
            _, host, alloc, assoc = act
            if assoc:
                vpc("DisassociateAddress", AssociationId=assoc)
            vpc("ReleaseAddress", AllocationId=alloc)
            log.append("EIP-REMOVE %s %s" % (host, alloc))

    print("\n".join("  " + l for l in log))
    print("  planned actions: %d" % len(planned))

    sgs2 = {s["GroupId"]: s for s in vpc_items(vpc("DescribeSecurityGroups"), "securityGroupInfo")}
    enis2 = {e["NetworkInterfaceId"]: e for e in vpc_items(vpc("DescribeNetworkInterfaces"), "networkInterfaceSet")}
    addrs2 = vpc_items(vpc("DescribeAddresses"), "addressesSet")
    assoc_enis = {a["NetworkInterfaceId"] for a in addrs2 if a.get("NetworkInterfaceId")}
    mismatches = []
    for eni_id in sorted(exposed):
        e = eni_by_id[eni_id]
        host = e["_host"]
        if is_sanctioned(host, public_ports_of(sgs, e["_groups"])):
            continue
        for gid in e["_groups"]:
            for r in sgs2.get(gid, {}).get("IpPermissions", []):
                if rule_is_public(r):
                    mismatches.append("%s still has public rule on %s" % (host, gid))
        if eni_id in assoc_enis:
            mismatches.append("%s still has an associated EIP" % host)
    if mismatches:
        print("READBACK MISMATCH:", file=sys.stderr)
        for m in mismatches:
            print("  -", m, file=sys.stderr)
        sys.exit(3)
    print("  readback OK: all remediated internal-data ENIs are private with no EIP")

if __name__ == "__main__":
    main()
