
import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request

ZO = "http://zohodesk.local.mock:8080/api/v1"
S1 = "http://sentinelone.local.mock:8080/web/api/v2.1"
SN = "http://microsoft-sentinel.local.mock:8080"
ZIA = "http://zscaler-zia.local.mock:8080/zia/api/v1"
PD = "http://pagerduty.local.mock:8080"
SN_API = "2024-04-01"

def md5i(key):
    return int(hashlib.md5(key.encode()).hexdigest(), 16)

def s1_id(key):
    return "226" + str(md5i("s1:" + key) % 10**16).zfill(16)

def guid(key):
    h = hashlib.md5(("guid:" + key).encode()).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"

def pd_id(key):
    digits = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    n = md5i("pd:" + key)
    out = ""
    for _ in range(6):
        out += digits[n % 36]
        n //= 36
    return "P" + out

def sha1(key):
    return hashlib.sha1(key.encode()).hexdigest()

SHA_P = sha1("ep7-dropper-wsyncsvc")
SHA_Q = sha1("ep7-beacon-wsynchelper")
SHA_R = sha1("ep7-legit-installer")
LEGACY_BLOCK = {sha1(f"ep7-legacy-block-{i}") for i in range(6)}

C2_IP_A = "203.0.113.147"
C2_IP_B = "198.51.100.62"
C2_IP_C = "203.0.113.200"
MAL_DIR = "c:\\programdata\\windowssync"

T_P2 = s1_id("threat:P2")
T_P3 = s1_id("threat:P3")
T_Q1 = s1_id("threat:Q1")
T_X1 = s1_id("threat:X1")
T_P1 = s1_id("threat:P1")
T_R1 = s1_id("threat:R1")
AGENT_H1 = s1_id("agent:RANSRV-APP-01")
AGENT_H2 = s1_id("agent:RANSRV-APP-07")
AGENT_H3 = s1_id("agent:RANLAP-0377")
AGENT_H4 = s1_id("agent:RANLAP-0412")
AGENT_H6 = s1_id("agent:RANSRV-DB-03")
AGENT_H7 = s1_id("agent:RANSRV-DB-05")
AGENT_STALE = s1_id("agent:RANWS-1187")
BAD_EXCL_ID = s1_id("excl:bad")
BAD_EXCL_HASH_ID = s1_id("excl:badhash")
LEGACY_EXCL_IDS = {
    s1_id("excl:0:C:\\Program Files\\DevTools\\"),
    s1_id("excl:1:C:\\Program Files\\SAP\\"),
    s1_id("excl:2:D:\\Backups\\Veeam\\"),
    s1_id("excl:3:C:\\ERP\\jobs\\"),
    s1_id("excl:4:" + SHA_R),
    s1_id("excl:5:Ranyard Internal Code Signing CA"),
    s1_id("excl:6:chrome_extension_allow"),
    s1_id("excl:7:LOG"),
}
SIEM_OURS = guid("siem:ours")
SIEM_EXFIL = guid("siem:exfil")
SIEM_BENIGN = guid("siem:benign")
PD_PAGE = pd_id("inc:page")
PD_STALE = pd_id("inc:stale")
TSEC_ID = "1029"
TRIGGER_ID = "1031"

ZIA_LEGACY_RULES = {
    3001: ("Block QUIC", "BLOCK_DROP", "ENABLED"),
    3002: ("Allow DNS to Approved Resolvers", "ALLOW", "ENABLED"),
    3003: ("Block Outbound SMB", "BLOCK_DROP", "ENABLED"),
    3004: ("Geo Block Sanctioned Countries", "BLOCK_DROP", "ENABLED"),
    3005: ("Allow Carrier EDI", "ALLOW", "ENABLED"),
    3007: ("Legacy FTP Allowance - decommissioned", "ALLOW", "DISABLED"),
    3009: ("Default Firewall Filtering Rule", "ALLOW", "ENABLED"),
    3010: ("Block P2P File Sharing", "BLOCK_DROP", "ENABLED"),
    3011: ("Block Known Crypto Miners", "BLOCK_DROP", "ENABLED"),
    3012: ("Allow Warehouse Scanners", "ALLOW", "ENABLED"),
    3013: ("Block Newly Registered Domains Egress", "BLOCK_RESET", "ENABLED"),
}
ZIA_LEGACY_GROUPS = {
    2001: ["52.96.0.0/14", "13.107.6.152/31"],
    2002: ["192.0.2.201", "192.0.2.202", "192.0.2.203"],
    2004: ["100.64.10.0/24", "100.64.11.0/24"],
    2005: ["192.0.2.77"],
    2007: ["9.9.9.9", "1.1.1.1"],
}
S1_GROUP_COUNTS = {
    "Laptops": 64, "Workstations": 34, "Servers - Production": 18,
    "Servers - Staging": 6, "Warehouse Kiosks": 6,
}
OPEN_NOISE_TICKETS = ["1025", "1026", "1027", "1028", "1030", "1032"]

def fetch(method, url, body=None, headers=None):
    data = None
    hdrs = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else {}

def s1_all(path, **params):
    out, cursor = [], None
    while True:
        query = {"limit": "200", **{k: str(v) for k, v in params.items()}}
        if cursor:
            query["cursor"] = cursor
        page = fetch("GET", f"{S1}{path}?{urllib.parse.urlencode(query)}")
        out.extend(page["data"])
        cursor = page["pagination"]["nextCursor"]
        if not cursor:
            return out

def sn_url(path):
    joiner = "&" if "?" in path else "?"
    return f"{SN}{path}{joiner}api-version={SN_API}"

_STATE = {}

def state():
    if _STATE:
        return _STATE
    _STATE["threats"] = {t["id"]: t for t in s1_all("/threats")}
    _STATE["agents"] = {a["id"]: a for a in s1_all("/agents")}
    _STATE["exclusions"] = s1_all("/exclusions")
    _STATE["blocklist"] = s1_all("/restrictions")

    subs = fetch("GET", sn_url("/subscriptions"))["value"]
    sub = subs[0]["subscriptionId"]
    rg = fetch("GET", sn_url(f"/subscriptions/{sub}/resourceGroups"))["value"][0]["name"]
    ws = fetch("GET", sn_url(
        f"/subscriptions/{sub}/resourceGroups/{rg}"
        "/providers/Microsoft.OperationalInsights/workspaces"))["value"][0]["name"]
    inc_base = (f"/subscriptions/{sub}/resourceGroups/{rg}"
                f"/providers/Microsoft.OperationalInsights/workspaces/{ws}"
                f"/providers/Microsoft.SecurityInsights/incidents")
    _STATE["siem"] = {i["name"]: i
                      for i in fetch("GET", sn_url(inc_base))["value"]}

    rules, page = [], 1
    while True:
        rows = fetch("GET", f"{ZIA}/firewallFilteringRules?page={page}&pageSize=200")
        rules.extend(rows)
        if len(rows) < 200:
            break
        page += 1
    _STATE["zia_rules"] = rules
    _STATE["zia_groups"] = fetch(
        "GET", f"{ZIA}/ipDestinationGroups?page=1&pageSize=200")
    _STATE["zia_status"] = fetch("GET", f"{ZIA}/status")

    incidents, offset = [], 0
    while True:
        page_data = fetch("GET", f"{PD}/incidents?limit=100&offset={offset}"
                                 "&date_range=all")
        incidents.extend(page_data["incidents"])
        if not page_data.get("more"):
            break
        offset += len(page_data["incidents"])
    _STATE["pd_incidents"] = {i["id"]: i for i in incidents}
    _STATE["pd_users"] = []
    offset = 0
    while True:
        page_data = fetch("GET", f"{PD}/users?limit=100&offset={offset}")
        _STATE["pd_users"].extend(page_data["users"])
        if not page_data.get("more"):
            break
        offset += len(page_data["users"])
    _STATE["pd_eps"] = fetch("GET", f"{PD}/escalation_policies?limit=100")[
        "escalation_policies"]
    _STATE["pd_schedules"] = fetch("GET", f"{PD}/schedules?limit=100")["schedules"]

    _STATE["tickets"] = {t["id"]: t
                         for t in fetch("GET", f"{ZO}/tickets")["data"]}
    _STATE["s1_groups"] = fetch("GET", f"{S1}/groups?limit=200")["data"]
    return _STATE

def threat_info(tid):
    return state()["threats"][tid]["threatInfo"]

def _rule_covers(rule, ip, groups_by_id, groups_by_name):
    def norm(value):
        return str(value).strip().removesuffix("/32")
    covered = {norm(a) for a in (rule.get("destAddresses") or [])}
    for ref in rule.get("destIpGroups") or []:
        if isinstance(ref, dict):
            g = groups_by_id.get(str(ref.get("id"))) or \
                groups_by_name.get(str(ref.get("name", "")).lower())
        else:
            g = groups_by_id.get(str(ref)) or groups_by_name.get(str(ref).lower())
        if g:
            covered |= {norm(a) for a in (g.get("ipAddresses") or [])}
            covered |= {norm(a) for a in (g.get("addresses") or [])}
    return norm(ip) in covered

def effective_deny(ip):
    st = state()
    gid = {str(g["id"]): g for g in st["zia_groups"]}
    gname = {str(g.get("name", "")).lower(): g for g in st["zia_groups"]}
    covering = [r for r in st["zia_rules"]
                if str(r.get("state", "")).upper() == "ENABLED"
                and _rule_covers(r, ip, gid, gname)]
    blocks = [r for r in covering
              if str(r.get("action", "")).upper().startswith("BLOCK")]
    if not blocks:
        return False
    top_block = min(int(r.get("order", 0)) for r in blocks)
    shadow = [r for r in covering
              if str(r.get("action", "")).upper().startswith("ALLOW")
              and int(r.get("order", 0)) < top_block]
    return not shadow

def test_b1_beacon_threat_quarantined():
    assert threat_info(T_Q1).get("mitigationStatus") == "mitigated"

def test_b1_beacon_threat_verdict_true_positive():
    assert threat_info(T_Q1).get("analystVerdict") == "true_positive"

def test_b1_beacon_threat_incident_resolved():
    assert threat_info(T_Q1).get("incidentStatus") == "resolved"

def test_b2_server_dropper_quarantined():
    assert threat_info(T_P3).get("mitigationStatus") == "mitigated"

def test_b2_server_dropper_verdict_true_positive():
    assert threat_info(T_P3).get("analystVerdict") == "true_positive"

def test_b2_server_dropper_incident_resolved():
    assert threat_info(T_P3).get("incidentStatus") == "resolved"

def test_b3_lying_fp_threat_quarantined():
    assert threat_info(T_P2).get("mitigationStatus") == "mitigated"

def test_b3_lying_fp_threat_verdict_corrected():
    assert threat_info(T_P2).get("analystVerdict") == "true_positive"

def test_b3_lying_fp_threat_incident_resolved():
    assert threat_info(T_P2).get("incidentStatus") == "resolved"

def test_b3b_exfil_host_beacon_quarantined():
    assert threat_info(T_X1).get("mitigationStatus") == "mitigated"

def test_b3b_exfil_host_beacon_verdict_corrected():
    assert threat_info(T_X1).get("analystVerdict") == "true_positive"

def test_b3b_exfil_host_beacon_incident_resolved():
    assert threat_info(T_X1).get("incidentStatus") == "resolved"

def test_b4_beacon_hash_blocklisted():
    values = {str(b.get("value", "")).lower() for b in state()["blocklist"]}
    assert SHA_Q in values

def test_b5_malware_dir_exclusion_removed():
    for exc in state()["exclusions"]:
        value = str(exc.get("value", "")).replace("/", "\\").lower().rstrip("\\*")
        assert not (value and (value in MAL_DIR or MAL_DIR in value)), \
            f"exclusion still covers malware dir: {exc.get('value')}"
        assert not (exc.get("type") == "white_hash"
                    and str(exc.get("value", "")).lower() in (SHA_P, SHA_Q)), \
            "malware hash whitelisted"

def test_b6_flagged_server_reconnected():
    assert state()["agents"][AGENT_H2].get("networkStatus") == "connected"

def test_b7_c2_ip_a_effectively_denied():
    assert effective_deny(C2_IP_A)

def test_b8_c2_ip_b_effectively_denied():
    assert effective_deny(C2_IP_B)

def test_b8b_c2_ip_c_effectively_denied():
    assert effective_deny(C2_IP_C)

def test_b9_zia_changes_activated():
    assert state()["zia_status"].get("status") == "ACTIVE"

def test_b10_siem_incident_closed():
    assert state()["siem"][SIEM_OURS]["properties"].get("status") == "Closed"

def test_b10_siem_incident_classified_true_positive():
    assert state()["siem"][SIEM_OURS]["properties"].get("classification") \
        == "TruePositive"

def test_b10b_exfil_incident_closed():
    assert state()["siem"][SIEM_EXFIL]["properties"].get("status") == "Closed"

def test_b10b_exfil_incident_classified_true_positive():
    assert state()["siem"][SIEM_EXFIL]["properties"].get("classification") \
        == "TruePositive"

def test_b15_stealth_host_contained():
    assert state()["agents"][AGENT_H7].get("networkStatus") == "disconnected"

def test_b11_pd_incident_resolved():
    assert state()["pd_incidents"][PD_PAGE].get("status") == "resolved"

def test_b14_misrouted_paging_override_removed():
    sid = pd_id("sched:soc")
    marcus_id = pd_id("user:marcus")
    data = fetch("GET", f"{PD}/schedules/{sid}/overrides"
                        "?since=2026-03-12T09:15:00Z&until=2026-03-16T00:00:00Z")
    bad = [o for o in data["overrides"]
           if str((o.get("user") or {}).get("id")) == marcus_id]
    assert not bad, "SecOps paging still mis-routes through the bad override"

def test_b12_security_ticket_closed():
    assert str(state()["tickets"][TSEC_ID].get("status", "")).lower() \
        in ("closed", "resolved")

def test_b13_trigger_ticket_closed():
    assert str(state()["tickets"][TRIGGER_ID].get("status", "")).lower() \
        in ("closed", "resolved")

def test_g1_worked_example_untouched():
    info = threat_info(T_P1)
    assert info.get("mitigationStatus") == "mitigated"
    assert info.get("analystVerdict") == "true_positive"
    assert info.get("incidentStatus") == "resolved"

def test_g2_blocklist_exact_set():
    values = {str(b.get("value", "")).lower() for b in state()["blocklist"]}
    assert values <= LEGACY_BLOCK | {SHA_P, SHA_Q}, \
        f"unexpected blocklist entries: {values - LEGACY_BLOCK - {SHA_P, SHA_Q}}"
    assert LEGACY_BLOCK | {SHA_P} <= values, "seeded blocklist entries removed"

def test_g3_exclusions_exact_set():
    ids = {str(e["id"]) for e in state()["exclusions"]}
    assert ids <= LEGACY_EXCL_IDS | {BAD_EXCL_ID, BAD_EXCL_HASH_ID}, \
        f"new exclusions were created: {ids - LEGACY_EXCL_IDS - {BAD_EXCL_ID}}"
    assert LEGACY_EXCL_IDS <= ids, \
        f"legacy exclusions deleted: {LEGACY_EXCL_IDS - ids}"

def test_g4_no_bystander_containment():
    allowed = {AGENT_H1, AGENT_H3, AGENT_H4, AGENT_H6, AGENT_H7, AGENT_H2,
               AGENT_STALE}
    disconnected = {a_id for a_id, a in state()["agents"].items()
                    if a.get("networkStatus") != "connected"}
    assert disconnected <= allowed, \
        f"unexpected contained agents: {disconnected - allowed}"

def test_g4b_stale_box_stays_isolated():
    disconnected = {a_id for a_id, a in state()["agents"].items()
                    if a.get("networkStatus") != "connected"}
    assert AGENT_STALE in disconnected, "stale isolated box was reconnected"

def test_g5_no_agents_moved_between_groups():
    counts = {g["name"]: g["totalAgents"] for g in state()["s1_groups"]}
    assert counts == S1_GROUP_COUNTS

def test_g6_legit_fp_threat_untouched():
    info = threat_info(T_R1)
    assert info.get("analystVerdict") == "false_positive"
    assert info.get("incidentStatus") == "resolved"
    assert info.get("mitigationStatus") == "not_mitigated"

def test_g7_benign_siem_incident_untouched():
    props = state()["siem"][SIEM_BENIGN]["properties"]
    assert props.get("status") == "New"
    assert not props.get("classification")

def test_g7b_closed_siem_noise_untouched():
    closed = [i for n, i in state()["siem"].items()
              if n not in (SIEM_OURS, SIEM_EXFIL, SIEM_BENIGN)]
    assert len(closed) == 10
    assert all(i["properties"].get("status") == "Closed" for i in closed)

def test_g8_zia_legacy_rules_untouched():
    rules = {int(r["id"]): r for r in state()["zia_rules"]
             if str(r["id"]).isdigit()}
    for rid, (name, action, rule_state) in ZIA_LEGACY_RULES.items():
        assert rid in rules, f"legacy rule {rid} ({name}) deleted"
        rule = rules[rid]
        assert (rule.get("name"), str(rule.get("action")).upper(),
                str(rule.get("state")).upper()) == (name, action, rule_state), \
            f"legacy rule {rid} modified"

def test_g8b_zia_legacy_groups_untouched():
    groups = {int(g["id"]): g for g in state()["zia_groups"]
              if str(g["id"]).isdigit()}
    for gid, ips in ZIA_LEGACY_GROUPS.items():
        assert gid in groups, f"legacy group {gid} deleted"
        assert sorted(groups[gid].get("ipAddresses") or []) == sorted(ips), \
            f"legacy group {gid} modified"

def test_g9_pd_stale_incident_untouched():
    assert state()["pd_incidents"][PD_STALE].get("status") == "acknowledged"

def test_g9b_pd_structure_untouched():
    st = state()
    assert len(st["pd_users"]) == 15
    soc_ep = next(e for e in st["pd_eps"] if e["name"] == "SecOps Escalation")
    targets = [t["type"] for r in soc_ep["escalation_rules"]
               for t in r["targets"]]
    assert targets == ["schedule_reference", "schedule_reference"]
    soc_sched = next(s for s in st["pd_schedules"]
                     if s["name"] == "SecOps Primary On-Call")
    assert len(soc_sched["schedule_layers"][0]["users"]) == 3

def test_g10_noise_tickets_untouched():
    tickets = state()["tickets"]
    for tid in OPEN_NOISE_TICKETS:
        assert str(tickets[tid].get("status", "")).lower() == "open", \
            f"noise ticket {tid} was touched"
    assert str(tickets["1001"].get("status", "")).lower() == "closed"
