
import ipaddress
import json
import time
import urllib.request
import urllib.error

JC = "http://jumpcloud.local.mock:8080"
ZS = "http://zscaler-zia.local.mock:8080/zia/api/v1"
HP = "http://haproxy.local.mock:8080/v3"

VENDOR_GROUP = "Vendor-Remote Access"
S2S_NET = ipaddress.ip_network("10.66.20.0/24")
KADJEI_IP = "10.66.20.7"
JUMP_IP = "10.66.20.11"

def _host(url):
    return url.split("://", 1)[1].split("/", 1)[0]

def _get(url):
    r = urllib.request.Request(url, method="GET",
                               headers={"Host": _host(url), "x-taskgen-verifier": "1"})
    last = None
    for _ in range(5):
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode("utf-8", "replace"))
            except Exception:
                return None
        except Exception as e:
            last = e
            time.sleep(1)
    raise last

def jc_users():
    out, skip = [], 0
    while True:
        d = _get(f"{JC}/api/systemusers?limit=100&skip={skip}") or {}
        rows = d.get("results", [])
        out.extend(rows)
        skip += len(rows)
        if not rows or skip >= d.get("totalCount", len(out)):
            break
    return out

def jc_group_id(name):
    skip = 0
    while True:
        rows = _get(f"{JC}/api/v2/usergroups?limit=100&skip={skip}") or []
        for g in rows:
            if g.get("name") == name:
                return g["id"]
        if len(rows) < 100:
            return None
        skip += len(rows)

def jc_group_member_usernames(gid):
    if not gid:
        return set()
    rows = _get(f"{JC}/api/v2/usergroups/{gid}/members?limit=100&skip=0") or []
    out = set()
    for m in rows:
        to = m.get("to", {}) if isinstance(m, dict) else {}
        attrs = to.get("attributes", {})
        name = attrs.get("username") or attrs.get("name")
        if name:
            out.add(str(name).lower())
    return out

def jc_user_by_username(un):
    for u in jc_users():
        if str(u.get("username", "")).lower() == un.lower():
            return u
    return None

def jc_sshkeys(uid):
    return _get(f"{JC}/api/systemusers/{uid}/sshkeys?limit=100&skip=0") or []

def zs_rules():
    out, page = [], 1
    while True:
        rows = _get(f"{ZS}/firewallFilteringRules?page={page}&pageSize=1000") or []
        out.extend(rows)
        if len(rows) < 1000:
            break
        page += 1
    return out

def zs_source_groups():
    return {str(g.get("id")): g for g in (_get(f"{ZS}/ipSourceGroups?page=1&pageSize=1000") or [])}

def hp_servers(backend):
    return _get(f"{HP}/services/haproxy/configuration/backends/{backend}/servers") or []

def _enabled_allow(r):
    return str(r.get("action", "")).upper() == "ALLOW" and str(r.get("state", "")).upper() == "ENABLED"

def _rule_grants_ip(r, ip_str, groups):
    addr = ipaddress.ip_address(ip_str)
    for x in (r.get("srcIps") or []):
        try:
            if addr in ipaddress.ip_network(str(x), strict=False):
                return True
        except Exception:
            if str(x) == ip_str:
                return True
    for g in (r.get("srcIpGroups") or []):
        gid = g.get("id") if isinstance(g, dict) else g
        grp = groups.get(str(gid))
        if not grp:
            continue
        for a in (grp.get("ipAddresses") or []):
            try:
                if addr in ipaddress.ip_network(str(a), strict=False):
                    return True
            except Exception:
                if str(a) == ip_str:
                    return True
    return False

def _rule_grants_subnet(r, net, groups):
    for x in (r.get("srcIps") or []):
        try:
            n = ipaddress.ip_network(str(x), strict=False)
            if n.subnet_of(net) or net.subnet_of(n):
                return True
        except Exception:
            pass
    for g in (r.get("srcIpGroups") or []):
        gid = g.get("id") if isinstance(g, dict) else g
        grp = groups.get(str(gid))
        if not grp:
            continue
        for a in (grp.get("ipAddresses") or []):
            try:
                n = ipaddress.ip_network(str(a), strict=False)
                if n.subnet_of(net) or net.subnet_of(n):
                    return True
            except Exception:
                pass
    return False

def test_d1_s2_firewall_residual_removed():
    offenders = [r.get("name") for r in zs_rules()
                 if _enabled_allow(r) and "mfeld" in {str(u).lower() for u in (r.get("users") or [])}]
    assert not offenders, f"mfeld still granted by ENABLED rules: {offenders}"

def test_d2_s4_jumpcloud_offboarded():
    u = jc_user_by_username("kadjei")
    assert u is not None, "kadjei user missing"
    assert str(u.get("state", "")).upper() == "SUSPENDED", f"kadjei state={u.get('state')}"
    members = jc_group_member_usernames(jc_group_id(VENDOR_GROUP))
    assert "kadjei" not in members, "kadjei still in Vendor-Remote group"

def test_d3_s4_firewall_residual_removed():
    groups = zs_source_groups()
    offenders = [r.get("name") for r in zs_rules()
                 if _enabled_allow(r) and _rule_grants_ip(r, KADJEI_IP, groups)]
    assert not offenders, f"kadjei IP still granted by: {offenders}"

def test_d4_s3_residual_group_and_sshkey_removed():
    u = jc_user_by_username("droe")
    assert u is not None, "droe user missing"
    members = jc_group_member_usernames(jc_group_id(VENDOR_GROUP))
    assert "droe" not in members, "droe still in Vendor-Remote group"
    keys = jc_sshkeys(u["id"])
    assert not keys, f"droe still has ssh keys: {[k.get('name') for k in keys]}"

def test_d5_s2s_subnet_access_removed():
    groups = zs_source_groups()
    offenders = [r.get("name") for r in zs_rules()
                 if _enabled_allow(r) and _rule_grants_subnet(r, S2S_NET, groups)]
    assert not offenders, f"S2S subnet still granted by: {offenders}"

def test_d6_portal_route_removed():
    addrs = [s.get("address") for s in hp_servers("remote_portal_back")]
    assert JUMP_IP not in addrs, f"portal still routes to {JUMP_IP}: {addrs}"

def test_g1_breakglass_account_still_active():
    u = jc_user_by_username("svc-soc-breakglass")
    assert u is not None, "break-glass account missing"
    assert str(u.get("state", "")).upper() == "ACTIVATED", \
        f"break-glass wrongly disabled: state={u.get('state')}"

def test_g2_breakglass_firewall_rule_still_enabled():
    rule = next((r for r in zs_rules() if r.get("name") == "SOC-BreakGlass-Access"), None)
    assert rule is not None, "break-glass rule missing (deleted?)"
    assert str(rule.get("state", "")).upper() == "ENABLED", "break-glass rule wrongly disabled"

def test_g3_suspended_user_set_exact():
    suspended = {str(u.get("username", "")).lower() for u in jc_users()
                 if str(u.get("state", "")).upper() == "SUSPENDED"}
    expected = {"pnair", "mfeld", "droe", "kadjei", "twong"}
    assert suspended == expected, f"suspended set {sorted(suspended)} != {sorted(expected)}"

def test_g4_active_vendor_continuum_untouched():
    rule = next((r for r in zs_rules() if r.get("name") == "Continuum-MSP-Access"), None)
    assert rule is not None, "Continuum rule missing (deleted?)"
    assert str(rule.get("state", "")).upper() == "ENABLED", "Continuum rule wrongly disabled"

def test_g5_portal_backend_server_set_exact():
    names = {s.get("name") for s in hp_servers("remote_portal_back")}
    expected = {"app01", "app02"}
    assert expected <= names, f"legit portal servers missing: {sorted(expected - names)}"
    extra = names - expected - {"rdg-jump01"}
    assert not extra, f"unexpected portal servers: {sorted(extra)}"

def test_g6_worked_example_s1_still_done():
    u = jc_user_by_username("pnair")
    assert u is not None, "pnair missing"
    assert str(u.get("state", "")).upper() == "SUSPENDED", "pnair re-activated"
    members = jc_group_member_usernames(jc_group_id(VENDOR_GROUP))
    assert "pnair" not in members, "pnair re-added to vendor group"
    assert not jc_sshkeys(u["id"]), "pnair gained ssh keys"
    rule = next((r for r in zs_rules() if r.get("name") == "Ridgeline-Pentest-Nair"), None)
    assert rule is not None and str(rule.get("state", "")).upper() == "DISABLED", \
        "pnair's old firewall rule was re-enabled"
