#!/usr/bin/env python3
import http.client, json, os, urllib.parse
import pytest

LOCAL = os.environ.get("TASKGEN_LOCAL_MOCK", "").strip()

def request(slug, method, path, query=None):
    vhost = "%s.local.mock:8080" % slug
    if LOCAL:
        host, port = LOCAL.split(":"); c = http.client.HTTPConnection(host, int(port), timeout=30)
    else:
        c = http.client.HTTPConnection("%s.local.mock" % slug, 8080, timeout=30)
    if query:
        path = path + ("&" if "?" in path else "?") + urllib.parse.urlencode(query)
    c.request(method, path, headers={"Host": vhost, "Accept": "application/json"})
    r = c.getresponse(); raw = r.read(); c.close()
    assert r.status < 400, "%s %s -> %d: %s" % (method, path, r.status, raw[:200])
    return json.loads(raw)

def vpc(action, **params):
    q = {"Action": action, "Version": "2016-11-15"}; q.update(params)
    return request("aws-vpc", "GET", "/", query=q)

def _items(resp, name):
    node = resp.get(name) or {}
    it = node.get("item", [])
    return [it] if isinstance(it, dict) else it

def _list(x):
    if isinstance(x, dict) and "item" in x: x = x["item"]
    if isinstance(x, dict): x = [x]
    return x or []

_CACHE = {}
def state():
    if not _CACHE:
        sgs = {s["GroupId"]: s for s in _items(vpc("DescribeSecurityGroups"), "securityGroupInfo")}
        enis = _items(vpc("DescribeNetworkInterfaces"), "networkInterfaceSet")
        addrs = _items(vpc("DescribeAddresses"), "addressesSet")
        by_host = {}
        for e in enis:
            name = None
            for t in _list(e.get("TagSet")):
                if t.get("Key") == "Name": name = t.get("Value")
            host = name or e.get("Description")
            e["_groups"] = [g["GroupId"] for g in _list(e.get("GroupSet"))]
            by_host[host] = e
        assoc = {}
        for a in addrs:
            if a.get("NetworkInterfaceId"):
                assoc.setdefault(a["NetworkInterfaceId"], []).append(a)
        _CACHE.update(sgs=sgs, enis=enis, addrs=addrs, by_host=by_host, assoc=assoc)
    return _CACHE

def rule_public(r):
    return any(x.get("CidrIp") == "0.0.0.0/0" for x in _list(r.get("IpRanges")))

def host_public_sgs(host):
    s = state(); e = s["by_host"][host]
    out = []
    for gid in e["_groups"]:
        sg = s["sgs"].get(gid, {})
        if any(rule_public(r) for r in sg.get("IpPermissions", [])):
            out.append(sg.get("GroupName", gid))
    return out

def host_has_eip(host):
    s = state(); e = s["by_host"][host]
    return e["NetworkInterfaceId"] in s["assoc"]

def host_public_ports(host):
    s = state(); e = s["by_host"][host]
    ports = set()
    for gid in e["_groups"]:
        for r in s["sgs"].get(gid, {}).get("IpPermissions", []):
            if rule_public(r):
                fp, tp = r.get("FromPort"), r.get("ToPort")
                if fp is None:
                    ports.add("all")
                else:
                    ports.update(range(fp, tp + 1))
    return ports

def all_public_sg_names():
    s = state()
    return {sg.get("GroupName", gid) for gid, sg in s["sgs"].items()
            if any(rule_public(r) for r in sg.get("IpPermissions", []))}

REMEDIATE = ["records-db-prod", "session-cache-prod", "search-idx-prod",
             "etl-staging-db", "legacy-billing-db", "ops-admin-console", "metrics-frontend-prod",
             "legacy-portal-lb", "partner-preview-lb"]
SANCTIONED = ["www-public-lb", "cdn-edge-lb", "api-gateway-lb"]

@pytest.mark.parametrize("host", REMEDIATE)
def test_sg_closed(host):
    open_sgs = host_public_sgs(host)
    assert open_sgs == [], "%s still publicly reachable via SG(s): %s" % (host, open_sgs)

@pytest.mark.parametrize("host", REMEDIATE)
def test_eip_removed(host):
    assert not host_has_eip(host), "%s still has a live Elastic IP (public path not removed)" % host

def test_exact_public_set():
    allowed = {"www-lb-sg", "cdn-edge-lb-sg", "api-gateway-sg"}
    actual = all_public_sg_names()
    assert actual == allowed, "public-open SG set != allowed; extra=%s missing=%s" % (
        actual - allowed, allowed - actual)

def test_r3_both_ports_closed():
    ports = host_public_ports("search-idx-prod")
    assert 9200 not in ports and 9300 not in ports, \
        "search-idx-prod still exposes port(s) %s to 0.0.0.0/0" % sorted(p for p in ports if p in (9200, 9300))

def test_r2_legacy_sg_closed():
    assert "session-cache-legacy-sg" not in host_public_sgs("session-cache-prod"), \
        "session-cache-prod still publicly reachable via the rogue legacy SG"

def test_r7_mislabeled_db_closed():
    assert host_public_sgs("metrics-frontend-prod") == [], \
        "metrics-frontend-prod (a DB mislabelled web-frontend) still publicly reachable"

@pytest.mark.parametrize("host,sg", [("www-public-lb", "www-lb-sg"),
                                     ("cdn-edge-lb", "cdn-edge-lb-sg"),
                                     ("api-gateway-lb", "api-gateway-sg")])
def test_guard_sanctioned_sg_untouched(host, sg):
    assert sg in host_public_sgs(host), "%s wrongly locked down" % host

@pytest.mark.parametrize("host", SANCTIONED)
def test_guard_sanctioned_eip_untouched(host):
    assert host_has_eip(host), "%s lost its Elastic IP (over-action)" % host

def test_guard_done_resource_untouched():
    assert host_public_sgs("reporting-db-prod") == [], "reporting-db-prod SG changed unexpectedly"
    assert not host_has_eip("reporting-db-prod"), "reporting-db-prod gained an EIP"

def test_guard_clean_internal_untouched():
    s = state()
    for host in ["orders-db-prod", "billing-db-prod"]:
        e = s["by_host"][host]
        rules = [r for gid in e["_groups"] for r in s["sgs"].get(gid, {}).get("IpPermissions", [])]
        assert rules, "%s lost its ingress rules (over-action)" % host
        assert host_public_sgs(host) == [], "%s became public (unexpected)" % host
