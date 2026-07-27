
import json
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).parent))
import cast as C

EXPECTED = json.loads((Path(__file__).parent / "expected.json").read_text())

SN = "http://servicenow.local.mock:8080"
D42 = "http://device42.local.mock:8080"
IB = "http://infoblox-nios.local.mock:8080/wapi/v2.14"
HAP = "http://haproxy.local.mock:8080/v3/services/haproxy"
ZIA = "http://zscaler-zia.local.mock:8080/zia/api/v1"
VPC = "http://aws-vpc.local.mock:8080"

_cache = {}

def get(url, params=None):
    key = (url, json.dumps(params, sort_keys=True) if params else None)
    if key not in _cache:
        r = requests.get(url, params=params, timeout=30)
        assert r.status_code == 200, f"GET {url} -> {r.status_code}: {r.text[:200]}"
        _cache[key] = r.json()
    return _cache[key]

def ib_all(record_type):
    rows, page_id = [], None
    while True:
        params = {"_paging": 1, "_max_results": 200, "_return_as_object": 1}
        if page_id:
            params["_page_id"] = page_id
        env = get(f"{IB}/{record_type}", params)
        rows.extend(env.get("result", []))
        page_id = env.get("next_page_id")
        if not page_id:
            return rows

def d42_all(path, list_key):
    rows, offset = [], 0
    while True:
        env = get(f"{D42}{path}", {"limit": 200, "offset": offset})
        rows.extend(env.get(list_key, []))
        offset += 200
        if offset >= int(env.get("total_count", 0)) or not env.get(list_key):
            return rows

def zia_rules_all():
    rows, page = [], 1
    while True:
        chunk = get(f"{ZIA}/firewallFilteringRules", {"page": page, "pageSize": 100})
        rows.extend(chunk)
        if len(chunk) < 100:
            return rows
        page += 1

def sn_all(table):
    rows, offset = [], 0
    while True:
        page = get(f"{SN}/api/now/table/{table}",
                   {"sysparm_limit": 200, "sysparm_offset": offset}).get("result", [])
        rows.extend(page)
        if len(page) < 200:
            return rows
        offset += 200

def sgs_all():
    out = requests.post(VPC + "/", data={"Action": "DescribeSecurityGroups",
                                         "Version": "2016-11-15", "MaxResults": "500"},
                        timeout=30)
    assert out.status_code == 200, out.text[:200]
    return out.json().get("securityGroupInfo", {}).get("item", [])

def perm_key(p):
    return json.dumps({
        "proto": p.get("IpProtocol"), "from": p.get("FromPort"), "to": p.get("ToPort"),
        "cidrs": sorted(r.get("CidrIp") for r in p.get("IpRanges", []) or []),
        "sgs": sorted(g.get("GroupId") for g in p.get("UserIdGroupPairs", []) or []),
    }, sort_keys=True)

def is_old(addr):
    return str(addr).startswith(C.OLD_SUBNET + ".")

RESIDUAL_DNS_HOSTS = sorted(C.RESIDUAL_DNS.values())
SCORED_SG = {gid: (gname, port, host) for gid, gname, port, host in C.SG_RESIDUALS}

@pytest.mark.parametrize("host", RESIDUAL_DNS_HOSTS)
def test_dns_repointed(host):
    recs = [r for r in ib_all("record:a") if r["name"] == f"{host}.{C.ZONE}"]
    assert len(recs) == 1, f"A record for {host} missing (deletion breaks the live host)"
    assert str(recs[0]["ipv4addr"]) == C.new_ip(host), \
        f"{host} A -> {recs[0]['ipv4addr']}, expected {C.new_ip(host)}"

def test_dns_sweep_no_old_subnet():
    hits = [r["name"] for r in ib_all("record:a") if is_old(r.get("ipv4addr"))]
    assert not hits, f"A records still on the retired subnet: {hits}"

@pytest.mark.parametrize("server", sorted(C.STALE_CONFIG_SERVERS))
def test_lb_config_repointed(server):
    host = next(h for mem in C.LB_BACKENDS.values() for n, h, _ in mem if n == server)
    bname = next(b for b, mem in C.LB_BACKENDS.items() if any(n == server for n, _, _ in mem))
    rows = [s for s in get(f"{HAP}/configuration/backends/{bname}/servers")
            if s["name"] == server]
    assert len(rows) == 1, f"config server {bname}/{server} missing"
    assert str(rows[0]["address"]) == C.new_ip(host), \
        f"{bname}/{server} at {rows[0]['address']}, expected {C.new_ip(host)}"

def test_lb_config_sweep_no_old_subnet():
    hits = []
    for b in get(f"{HAP}/configuration/backends"):
        for s in get(f"{HAP}/configuration/backends/{b['name']}/servers"):
            if is_old(s.get("address")):
                hits.append(f"{b['name']}/{s['name']}")
    assert not hits, f"config servers still on the retired subnet: {hits}"

def test_lb_runtime_sweep_no_old_subnet():
    hits = []
    for b in get(f"{HAP}/configuration/backends"):
        for r in get(f"{HAP}/runtime/backends/{b['name']}/servers"):
            if is_old(r.get("address")):
                hits.append(f"{b['name']}/{r.get('server_name')}")
    assert not hits, f"runtime rows still on the retired subnet: {hits}"

@pytest.mark.parametrize("rule_name,host", [
    (C.ZIA_SCALEHUB_RULE[0], C.ZIA_SCALEHUB_RULE[2]),
    (C.ZIA_COLDVAULT_RULE[0], C.ZIA_COLDVAULT_RULE[2]),
])
def test_zia_rule_repointed(rule_name, host):
    rules = [r for r in zia_rules_all() if r.get("name") == rule_name]
    assert len(rules) == 1, f"rule {rule_name} missing (it serves a live host)"
    assert [str(s) for s in rules[0].get("srcIps") or []] == [C.new_ip(host)], \
        f"{rule_name} srcIps {rules[0].get('srcIps')}, expected [{C.new_ip(host)}]"

def test_zia_hall1_group_repointed():
    groups = [g for g in get(f"{ZIA}/ipSourceGroups") if g["name"] == C.ZIA_HALL1_GROUP[0]]
    assert len(groups) == 1, "hall1 source group missing"
    addrs = [str(a) for a in groups[0].get("ipAddresses") or []]
    assert C.NEW_CIDR in addrs and C.OLD_CIDR not in addrs, f"group holds {addrs}"

def test_zia_sweep_no_old_subnet():
    hits = []
    for r in zia_rules_all():
        if any(is_old(s) for s in r.get("srcIps") or []):
            hits.append(f"rule {r.get('name')}")
    for g in get(f"{ZIA}/ipSourceGroups"):
        if any(str(a) == C.OLD_CIDR or is_old(str(a).split("/")[0])
               for a in g.get("ipAddresses") or []):
            hits.append(f"group {g.get('name')}")
    assert not hits, f"ZIA still references the retired subnet: {hits}"

def test_zia_activation_active():
    assert get(f"{ZIA}/status").get("status") == "ACTIVE"

@pytest.mark.parametrize("gid", sorted(SCORED_SG))
def test_sg_repointed(gid):
    gname, port, host = SCORED_SG[gid]
    groups = [g for g in sgs_all() if g.get("GroupId") == gid]
    assert len(groups) == 1, f"{gname} missing"
    cidrs = {str(r.get("CidrIp")): p.get("FromPort")
             for p in groups[0].get("IpPermissions") or []
             for r in p.get("IpRanges") or []}
    assert f"{C.old_ip(host)}/32" not in cidrs, f"{gname} still allows the retired /32"
    assert cidrs.get(f"{C.new_ip(host)}/32") == port, \
        f"{gname} missing tcp/{port} from {C.new_ip(host)}/32 (got {cidrs})"

def test_sg_sweep_no_old_subnet():
    hits = [f"{g.get('GroupName')} {r.get('CidrIp')}"
            for g in sgs_all() for p in g.get("IpPermissions") or []
            for r in p.get("IpRanges") or [] if is_old(str(r.get("CidrIp", "")).split("/")[0])]
    assert not hits, f"SG ingress still references the retired subnet: {hits}"

def test_incident_resolved():
    rows = [r for r in sn_all("incident") if r.get("number") == C.TRIGGER_INCIDENT]
    assert len(rows) == 1
    assert str(rows[0].get("state")) in ("6", "7"), f"state {rows[0].get('state')!r}"

def test_guard_migrated_and_bystander_dns_values_intact():
    residual_names = set(C.RESIDUAL_DNS)
    got = {r["name"]: str(r["ipv4addr"]) for r in ib_all("record:a")}
    for name, ip in EXPECTED["a_records"].items():
        if name in residual_names:
            continue
        assert got.get(name) == ip, f"{name}: {got.get(name)} != {ip}"

def test_guard_dns_no_bystander_create_or_delete():
    seeded = set(EXPECTED["a_records"])
    got = set(r["name"] for r in ib_all("record:a"))
    assert seeded - set(C.RESIDUAL_DNS) <= got, \
        f"records deleted: {seeded - set(C.RESIDUAL_DNS) - got}"
    assert got <= seeded, f"unexpected records created: {got - seeded}"

def test_guard_cnames_exact():
    got = sorted(r["name"] for r in ib_all("record:cname"))
    assert got == EXPECTED["cname_names"], f"CNAMEs changed: {got}"

def test_guard_backends_and_servers_intact():
    got_backends = {b["name"] for b in get(f"{HAP}/configuration/backends")}
    assert got_backends == set(EXPECTED["backend_servers"]), \
        f"backend set changed: {got_backends ^ set(EXPECTED['backend_servers'])}"
    for bname, seeded in EXPECTED["backend_servers"].items():
        got = sorted((s["name"], str(s["address"]))
                     for s in get(f"{HAP}/configuration/backends/{bname}/servers"))
        seeded_names = sorted(n for n, _ in seeded)
        assert sorted(n for n, _ in got) == seeded_names, f"{bname} server names changed"
        for name, addr in got:
            if name not in C.STALE_CONFIG_SERVERS:
                assert (name, addr) in [tuple(x) for x in seeded], \
                    f"{bname}/{name} address changed to {addr}"

def test_guard_healthy_runtime_rows_intact():
    for bname, seeded in EXPECTED["runtime_rows"].items():
        if bname in C.STALE_RUNTIME_BACKENDS:
            continue
        got = sorted((r.get("server_name"), str(r.get("address")))
                     for r in get(f"{HAP}/runtime/backends/{bname}/servers"))
        assert got == [tuple(x) for x in seeded], f"{bname} runtime rows changed"

def test_guard_zia_noise_rules_unchanged():
    scored = {C.ZIA_SCALEHUB_RULE[0], C.ZIA_COLDVAULT_RULE[0]}
    got = {r["name"]: str(r.get("state")).upper() for r in zia_rules_all()}
    for name, state in EXPECTED["zia_rule_states"].items():
        if name in scored:
            continue
        assert got.get(name) == state, f"rule {name}: {got.get(name)} != {state}"

def test_guard_zia_noise_groups_unchanged():
    got = {g["name"]: sorted(str(a) for a in g.get("ipAddresses") or [])
           for g in get(f"{ZIA}/ipSourceGroups")}
    for name, addrs in EXPECTED["zia_groups"].items():
        if name == C.ZIA_HALL1_GROUP[0]:
            continue
        assert got.get(name) == addrs, f"group {name} changed: {got.get(name)}"

def test_guard_sg_no_bystander_changes():
    scored_new = {}
    for gid, (gname, port, host) in SCORED_SG.items():
        scored_new[gid] = json.dumps({
            "proto": "tcp", "from": port, "to": port,
            "cidrs": [f"{C.new_ip(host)}/32"], "sgs": []}, sort_keys=True)
    for g in sgs_all():
        gid = g["GroupId"]
        seeded = set(EXPECTED["sg_ingress"].get(gid, []))
        got = {perm_key(p) for p in g.get("IpPermissions") or []}
        old_perm = {k for k in seeded if C.OLD_SUBNET + "." in k}
        required = seeded - old_perm
        allowed = seeded | ({scored_new[gid]} if gid in scored_new else set())
        assert required <= got, f"{g['GroupName']} live ingress removed: {required - got}"
        assert got <= allowed, f"{g['GroupName']} unexpected ingress added: {got - allowed}"

def test_guard_device42_untouched():
    devices = d42_all("/api/2.0/devices/", "devices")
    got_state = {d["name"]: bool(d.get("in_service")) for d in devices}
    for name, exp in EXPECTED["device_state"].items():
        assert got_state.get(name) == exp["in_service"], f"{name} in_service changed"
    rows = d42_all("/api/2.0/ips/", "ips")
    got = sorted(f"{r['ip']}|{r.get('device')}" for r in rows if r.get("device"))
    assert got == EXPECTED["assigned_ips"], "Device42 IP assignments changed"

def test_guard_blamed_change_not_reopened():
    rows = [r for r in sn_all("change_request") if r.get("number") == C.BLAMED_CHANGE]
    assert len(rows) == 1, "blamed change missing"
    exp = EXPECTED["cr_states"][C.BLAMED_CHANGE]
    assert str(rows[0].get("state")) == exp["state"], \
        "the blamed change was reopened/altered — it is innocent"
    assert str(rows[0].get("closed_at")) == exp["closed_at"]

def test_guard_noise_incidents_unchanged():
    got = {r["number"]: str(r.get("state")) for r in sn_all("incident")}
    for number, state in EXPECTED["noise_incident_states"].items():
        assert got.get(number) == state, f"{number}: {got.get(number)} != {state}"

def test_guard_lookalike_subnet_untouched():
    a = {r["name"]: str(r["ipv4addr"]) for r in ib_all("record:a")}
    assert a.get(f"hvac-ctl-01.{C.ZONE}") == "10.40.12.5"
    groups = {g["name"]: [str(x) for x in g.get("ipAddresses") or []]
              for g in get(f"{ZIA}/ipSourceGroups")}
    assert groups.get(C.ZIA_LOOKALIKE_GROUP[0]) == [f"{C.LOOKALIKE_SUBNET}.0/24"]
    ot = [g for g in sgs_all() if g.get("GroupName") == "sg-floor-ot"]
    assert ot and any(f"{C.LOOKALIKE_SUBNET}.5/32" in [r.get("CidrIp") for r in p.get("IpRanges") or []]
                      for p in ot[0].get("IpPermissions") or [])
