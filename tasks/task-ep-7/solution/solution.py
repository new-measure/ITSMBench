#!/usr/bin/env python3

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

TRIGGER_TICKET_ID = "1031"

ZO = "http://zohodesk.local.mock:8080/api/v1"
S1 = "http://sentinelone.local.mock:8080/web/api/v2.1"
SN = "http://microsoft-sentinel.local.mock:8080"
ZIA = "http://zscaler-zia.local.mock:8080/zia/api/v1"
PD = "http://pagerduty.local.mock:8080"
SN_API = "2024-04-01"

WRITES = []

def die(gate, message):
    print(f"ORACLE FAIL [{gate}]: {message}", file=sys.stderr)
    sys.exit(1)

def call(method, url, body=None, headers=None):
    data = None
    hdrs = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as err:
        die("HTTP", f"{method} {url} -> {err.code}: {err.read().decode()[:400]}")
    return json.loads(raw) if raw else {}

def get(url, headers=None):
    return call("GET", url, headers=headers)

def record_write(description, method, url, body=None, headers=None):
    WRITES.append(description)
    print(f"WRITE: {description}")
    return call(method, url, body=body, headers=headers)

def parse_ts(value):
    text = str(value).replace("Z", "+00:00")
    return datetime.fromisoformat(text).astimezone(timezone.utc)

def s1_all(path, **params):
    out, cursor = [], None
    while True:
        query = {"limit": "200", **{k: str(v) for k, v in params.items()}}
        if cursor:
            query["cursor"] = cursor
        page = get(f"{S1}{path}?{urllib.parse.urlencode(query)}")
        out.extend(page["data"])
        cursor = page["pagination"]["nextCursor"]
        if not cursor:
            return out

def pd_all(path, extra=""):
    out, offset = [], 0
    key = path.strip("/").split("/")[-1]
    while True:
        url = f"{PD}{path}?limit=100&offset={offset}"
        if extra:
            url += "&" + extra
        page = get(url)
        out.extend(page[key])
        if not page.get("more"):
            return out
        offset += len(page[key])

def zia_all(path):
    out, page = [], 1
    while True:
        rows = get(f"{ZIA}{path}?page={page}&pageSize=200")
        out.extend(rows)
        if len(rows) < 200:
            return out
        page += 1

def sn_url(path):
    joiner = "&" if "?" in path else "?"
    return f"{SN}{path}{joiner}api-version={SN_API}"

def sn_list(path, method="GET"):
    payload = call(method, sn_url(path))
    return payload.get("value", payload)

print("== Phase 1: trigger ticket ==")
trigger = get(f"{ZO}/tickets/{TRIGGER_TICKET_ID}")
trigger_text = f"{trigger.get('subject', '')} {trigger.get('description', '')}"
if str(trigger.get("status", "")).lower() in ("closed", "resolved"):
    die("C1", "trigger ticket is not open")

print("== Phase 2: full reads ==")
agents = s1_all("/agents")
count = get(f"{S1}/agents/count")["data"]["count"]
if len(agents) != count:
    die("C1", f"agent pagination mismatch: {len(agents)} != {count}")

lowered = trigger_text.lower()
flagged = [a for a in agents if a.get("computerName", "").lower() in lowered
           and a.get("computerName")]
if len(flagged) != 1:
    die("C1", f"ticket text resolves to {len(flagged)} agents (need exactly 1): "
              f"{[a.get('computerName') for a in flagged]}")
flagged = flagged[0]
print(f"flagged host: {flagged['computerName']} agent={flagged['id']}")

if flagged.get("networkStatus") != "disconnected":
    die("C2", f"flagged host networkStatus={flagged.get('networkStatus')}")

activities = s1_all("/activities", agentIds=flagged["id"])
disconnects = [a for a in activities
               if "disconnect" in str(a.get("primaryDescription", "")).lower()]
if len(disconnects) != 1:
    die("C3", f"{len(disconnects)} disconnect activities for flagged host")
anchor = parse_ts(disconnects[0]["createdAt"])
night_lo, night_hi = anchor - timedelta(hours=12), anchor + timedelta(hours=12)
print(f"containment at {anchor.isoformat()} by "
      f"{disconnects[0].get('userName', '?')}")

def in_window(value):
    if not value:
        return False
    return night_lo <= parse_ts(value) <= night_hi

threats = s1_all("/threats")
flagged_threats = [t for t in threats
                   if t.get("agentRealtimeInfo", {}).get("agentId") == flagged["id"]]
if flagged_threats:
    die("C4", f"flagged host has {len(flagged_threats)} threats; premise not false")

night = [t for t in threats if in_window(t.get("threatInfo", {}).get("createdAt"))]
if len(night) < 2:
    die("C5", f"only {len(night)} night threats")

def handled(threat):
    info = threat.get("threatInfo", {})
    return (info.get("mitigationStatus") == "mitigated"
            and info.get("analystVerdict") == "true_positive"
            and info.get("incidentStatus") == "resolved")

worked = [t for t in night if handled(t)]
if len(worked) != 1:
    die("C5", f"{len(worked)} fully-handled night threats (need exactly 1)")
worked = worked[0]
broken = [t for t in night if t is not worked]
sec_ticket_id = str(worked.get("threatInfo", {}).get("externalTicketId") or "")
if not sec_ticket_id:
    die("C5", "worked example has no externalTicketId")
sec_ticket = get(f"{ZO}/tickets/{sec_ticket_id}")
if str(sec_ticket.get("status", "")).lower() in ("closed", "resolved"):
    die("C5", "security ticket already closed")

def dir_of(path):
    text = str(path or "").replace("/", "\\").lower()
    return text.rsplit("\\", 1)[0] if "\\" in text else text

worked_sha = str(worked["threatInfo"].get("sha1", "")).lower()
worked_dir = dir_of(worked["threatInfo"].get("filePath"))

subs = sn_list("/subscriptions")
sub = subs[0]["subscriptionId"]
rgs = sn_list(f"/subscriptions/{sub}/resourceGroups")
rg = rgs[0]["name"]
wss = sn_list(f"/subscriptions/{sub}/resourceGroups/{rg}"
              "/providers/Microsoft.OperationalInsights/workspaces")
ws = wss[0]["name"]
inc_base = (f"/subscriptions/{sub}/resourceGroups/{rg}"
            f"/providers/Microsoft.OperationalInsights/workspaces/{ws}"
            f"/providers/Microsoft.SecurityInsights/incidents")

night_shas = {str(t["threatInfo"].get("sha1", "")).lower() for t in night}
night_hosts = {t.get("agentRealtimeInfo", {}).get("agentComputerName", "").lower()
               for t in night}

incidents = sn_list(inc_base)
matches = []
for inc in incidents:
    if inc["properties"].get("status") == "Closed":
        continue
    ents = call("POST", sn_url(f"{inc_base}/{inc['name']}/entities"))["entities"]
    hashes = {str(e["properties"].get("hashValue", "")).lower()
              for e in ents if e.get("kind") == "FileHash"}
    hosts = {str(e["properties"].get("hostName", "")).lower()
             for e in ents if e.get("kind") == "Host"}
    if hashes & night_shas or hosts & night_hosts:
        matches.append((inc, ents, hosts))
if not matches:
    die("C7", "no open SIEM incidents match the night artifacts")
siem_entities = [e for _, ents, _ in matches for e in ents]
siem_hosts = set().union(*[h for _, _, h in matches])
siem_hashes = {str(e["properties"].get("hashValue", "")).lower()
               for e in siem_entities if e.get("kind") == "FileHash"}
c2_ips = sorted({e["properties"].get("address", "")
                 for e in siem_entities if e.get("kind") == "Ip"})
if not c2_ips:
    die("C7", "SIEM incidents have no Ip entities")
if flagged["computerName"].lower() in siem_hosts:
    die("C7", "flagged host appears in SIEM incident Host entities")
siem_incidents = [inc for inc, _, _ in matches]
print(f"SIEM incidents {[i['properties'].get('incidentNumber') for i in siem_incidents]} "
      f"C2={c2_ips}")

agents_by_name_lc = {}
for a in agents:
    agents_by_name_lc[a["computerName"].lower()] = a
hosts_with_threats = {t.get("agentRealtimeInfo", {}).get("agentComputerName", "").lower()
                      for t in threats}
stealth_hosts = []
for host_lc in sorted(siem_hosts):
    if host_lc == flagged["computerName"].lower():
        continue
    if host_lc in hosts_with_threats:
        continue
    agent = agents_by_name_lc.get(host_lc)
    if agent and agent.get("networkStatus") == "connected":
        stealth_hosts.append(agent)
print(f"stealth hosts to contain: {[a['computerName'] for a in stealth_hosts]}")

never_contained = False
for t in broken:
    info = t["threatInfo"]
    sha = str(info.get("sha1", "")).lower()
    evidence = (sha == worked_sha or sha in siem_hashes
                or dir_of(info.get("filePath")) == worked_dir)
    if not evidence:
        die("C6", f"threat {t['id']} lacks evidence of being real")
    agent = next((a for a in agents
                  if a["id"] == t.get("agentRealtimeInfo", {}).get("agentId")), None)
    if agent is None:
        die("C6", f"threat {t['id']} has no agent")
    if agent["id"] == flagged["id"]:
        die("C6", "broken threat sits on the flagged host")
    if agent.get("networkStatus") == "connected":
        never_contained = True
if not never_contained:
    die("C6", "no infected agent was left un-contained; wrong-host story broken")

rules = zia_all("/firewallFilteringRules")
groups = zia_all("/ipDestinationGroups")
groups_by_id = {str(g["id"]): g for g in groups}
groups_by_name = {str(g.get("name", "")).lower(): g for g in groups}

def group_ips(group):
    return {str(ip) for ip in (group.get("ipAddresses") or [])} | \
           {str(ip) for ip in (group.get("addresses") or [])}

def resolve_groups(rule):
    out = []
    for ref in rule.get("destIpGroups") or []:
        if isinstance(ref, dict):
            g = groups_by_id.get(str(ref.get("id"))) or \
                groups_by_name.get(str(ref.get("name", "")).lower())
        else:
            g = groups_by_id.get(str(ref)) or groups_by_name.get(str(ref).lower())
        if g:
            out.append(g)
    return out

def rule_covers(rule, ip):
    ips = {str(a) for a in (rule.get("destAddresses") or [])}
    for g in resolve_groups(rule):
        ips |= group_ips(g)
    return str(ip) in ips

night_rules = [r for r in rules if in_window(r.get("created_at"))]
if len(night_rules) != 1:
    die("C8", f"{len(night_rules)} ZIA rules created in the night window")
c2_rule = night_rules[0]
if not str(c2_rule.get("action", "")).upper().startswith("BLOCK"):
    die("C8", f"night rule action={c2_rule.get('action')}")
c2_groups = resolve_groups(c2_rule)
target_group = next((g for g in c2_groups if group_ips(g) & set(c2_ips)), None)
if target_group is None:
    die("C8", "night rule's destination groups hold none of the C2 IPs")

block_order = int(c2_rule.get("order", 0))
shadow_edits = {}
for ip in c2_ips:
    for rule in rules:
        if str(rule.get("state", "")).upper() != "ENABLED":
            continue
        if not str(rule.get("action", "")).upper().startswith("ALLOW"):
            continue
        if int(rule.get("order", 0)) >= block_order:
            continue
        if not rule_covers(rule, ip):
            continue
        for g in resolve_groups(rule):
            if str(ip) in group_ips(g):
                shadow_edits.setdefault(g["id"], g)
if not shadow_edits:
    die("C8", "no shadowing higher-priority allow found for the C2 IPs")

pd_open = pd_all("/incidents",
                 "statuses[]=triggered&statuses[]=acknowledged&date_range=all")
pd_night = [i for i in pd_open if in_window(i.get("created_at"))]
if len(pd_night) != 1:
    die("C9", f"{len(pd_night)} open PD incidents in the night window")
pd_incident = pd_night[0]
assignments = pd_incident.get("assignments") or []
if not assignments:
    die("C9", "PD incident has no assignee")
assignee = get(f"{PD}/users/{assignments[0]['assignee']['id']}")["user"]
actor_email = assignee.get("email")
if not actor_email:
    die("C9", "PD assignee has no email")

entries = pd_all(f"/incidents/{pd_incident['id']}/log_entries")
notifies = sorted((e for e in entries if e.get("type") == "notify_log_entry"),
                  key=lambda e: str(e.get("created_at")))
if not notifies:
    die("C11", "page has no notification log entries")
first_paged = notifies[0].get("user") or {}
ackers = {(e.get("agent") or {}).get("id")
          for e in entries if e.get("type") == "acknowledge_log_entry"}
if not first_paged.get("id"):
    die("C11", "first notify entry names no user")
if first_paged["id"] in ackers:
    die("C11", "first-notified user acknowledged the page; no mis-route")

eps = pd_all("/escalation_policies")
inc_ep = next((e for e in eps
               if e["id"] == pd_incident["escalation_policy"]["id"]), None)
if inc_ep is None:
    die("C11", "incident escalation policy not found")
level1_scheds = [t["id"] for t in inc_ep["escalation_rules"][0]["targets"]
                 if str(t.get("type", "")).startswith("schedule")]
if len(level1_scheds) != 1:
    die("C11", f"{len(level1_scheds)} level-1 schedules on the paging policy")
soc_sched_id = level1_scheds[0]

window = urllib.parse.urlencode({
    "since": night_lo.isoformat().replace("+00:00", "Z"),
    "until": night_hi.isoformat().replace("+00:00", "Z")})
night_overrides = get(f"{PD}/schedules/{soc_sched_id}/overrides?{window}")[
    "overrides"]
mis_overrides = [o for o in night_overrides
                 if (o.get("user") or {}).get("id") == first_paged["id"]]
if len(mis_overrides) != 1:
    die("C11", f"{len(mis_overrides)} overrides put the unresponsive user on "
               "the level-1 schedule that night")
bad_override = mis_overrides[0]

paged_user = get(f"{PD}/users/{first_paged['id']}")["user"]
paged_email = str(paged_user.get("email", "")).lower()
contacts = get(f"{ZO}/contacts")["data"]
paged_contacts = {c["id"] for c in contacts
                  if str(c.get("email", "")).lower() == paged_email}
if not paged_contacts:
    die("C11", "notified user has no helpdesk contact")
all_tickets = get(f"{ZO}/tickets")["data"]
origin = [t for t in all_tickets
          if t.get("contactId") in paged_contacts
          and ("on-call" in f"{t.get('subject', '')} {t.get('description', '')}".lower()
               or "pagerduty" in f"{t.get('subject', '')} {t.get('description', '')}".lower())]
if len(origin) != 1:
    die("C11", f"{len(origin)} helpdesk tickets from the notified user mention "
               "the on-call schedule")
origin = origin[0]
origin_text = f"{origin.get('subject', '')} {origin.get('description', '')}".lower()
MONTHS = ["january", "february", "march", "april", "may", "june", "july",
          "august", "september", "october", "november", "december"]
requested_months = {m for m in MONTHS
                    if re.search(rf"\b{m}\b", origin_text)}
override_months = {MONTHS[parse_ts(bad_override["start"]).month - 1],
                   MONTHS[parse_ts(bad_override["end"]).month - 1]}
if not requested_months:
    die("C11", "origin ticket names no month; mis-entry not provable")
if requested_months & override_months:
    die("C11", "override dates match the requested week; no mis-entry")

exclusions = s1_all("/exclusions")
bad_exclusions = []
for exc in exclusions:
    value = str(exc.get("value", "")).replace("/", "\\").lower().rstrip("\\*")
    covers = value and (value in worked_dir or worked_dir in value)
    if exc.get("type") == "white_hash" and str(exc.get("value", "")).lower() in night_shas:
        covers = True
    if covers:
        if not in_window(exc.get("createdAt")):
            die("C10", f"exclusion {exc['id']} covers malware dir but is not "
                       "from the incident night")
        bad_exclusions.append(exc)
if not bad_exclusions:
    die("C10", "no exclusions suppress the malware artifacts")

blocklist = s1_all("/restrictions")
blocked_values = {str(b.get("value", "")).lower() for b in blocklist}
missing_shas = sorted(night_shas - blocked_values)

print("== Phase 3: plan ==")
broken_ids = sorted(t["id"] for t in broken)
plan = [
    f"S1 quarantine threats {broken_ids}",
    f"S1 verdict true_positive {broken_ids}",
    f"S1 incidentStatus resolved {broken_ids}",
    f"S1 blocklist add {missing_shas}",
    f"S1 delete exclusions {[e['id'] for e in bad_exclusions]}",
    f"S1 reconnect {flagged['computerName']}",
    f"S1 contain stealth hosts {[a['computerName'] for a in stealth_hosts]}",
    f"ZIA group {target_group['name']} -> {c2_ips}",
    f"ZIA de-shadow groups {[g['name'] for g in shadow_edits.values()]}",
    f"ZIA enable rule {c2_rule['name']}",
    "ZIA activate",
    f"SIEM close {[i['properties'].get('incidentNumber') for i in siem_incidents]} TruePositive",
    f"PD resolve {pd_incident['id']} as {actor_email}",
    f"PD delete mis-dated override {bad_override['id']} "
    f"({bad_override['start']}..{bad_override['end']}, requested "
    f"{sorted(requested_months)})",
    f"Zoho close {sec_ticket_id} and {TRIGGER_TICKET_ID}",
]
print("\n".join("  " + step for step in plan))

print("== Phase 4: execute ==")
id_filter = {"ids": broken_ids}
record_write("quarantine broken threats", "POST", f"{S1}/threats/mitigate/quarantine",
             {"filter": id_filter})
record_write("verdict true_positive", "POST", f"{S1}/threats/analyst-verdict",
             {"filter": id_filter, "data": {"analystVerdict": "true_positive"}})
record_write("incidentStatus resolved", "POST", f"{S1}/threats/incident",
             {"filter": id_filter, "data": {"incidentStatus": "resolved"}})

for sha in missing_shas:
    carrier = next(t for t in night
                   if str(t["threatInfo"].get("sha1", "")).lower() == sha)
    os_type = carrier.get("agentRealtimeInfo", {}).get("agentOsType", "windows")
    record_write(f"blocklist {sha}", "POST", f"{S1}/restrictions",
                 {"data": {"type": "black_hash", "value": sha, "osType": os_type,
                           "description": "Hash observed in overnight intrusion "
                                          f"(threat {carrier['id']})"}})

record_write("delete night exclusions", "DELETE", f"{S1}/exclusions",
             {"data": {"ids": [e["id"] for e in bad_exclusions]}})
record_write("reconnect flagged host", "POST", f"{S1}/agents/actions/connect",
             {"filter": {"ids": [flagged["id"]]}})
if stealth_hosts:
    record_write(f"contain stealth hosts {[a['computerName'] for a in stealth_hosts]}",
                 "POST", f"{S1}/agents/actions/disconnect",
                 {"filter": {"ids": [a["id"] for a in stealth_hosts]}})

record_write("fix C2 group IPs", "PUT",
             f"{ZIA}/ipDestinationGroups/{target_group['id']}",
             {"ipAddresses": c2_ips})
for gid, g in shadow_edits.items():
    kept = [ip for ip in (g.get("ipAddresses") or []) if str(ip) not in c2_ips]
    record_write(f"de-shadow group {g['name']}", "PUT",
                 f"{ZIA}/ipDestinationGroups/{gid}", {"ipAddresses": kept})
record_write("enable C2 rule", "PUT",
             f"{ZIA}/firewallFilteringRules/{c2_rule['id']}",
             {"state": "ENABLED"})
record_write("activate ZIA config", "POST", f"{ZIA}/status/activate")

for inc in siem_incidents:
    props = inc["properties"]
    new_props = {k: props[k] for k in
                 ("title", "description", "severity", "firstActivityTimeUtc",
                  "lastActivityTimeUtc", "owner", "labels") if k in props}
    new_props.update({"status": "Closed", "classification": "TruePositive",
                      "classificationComment":
                          "Confirmed intrusion; endpoints remediated and C2 blocked."})
    record_write(f"close SIEM incident #{props.get('incidentNumber')}", "PUT",
                 sn_url(f"{inc_base}/{inc['name']}"),
                 {"properties": new_props})

record_write("resolve PD incident", "PUT", f"{PD}/incidents/{pd_incident['id']}",
             {"incident": {"type": "incident", "status": "resolved"}},
             headers={"From": actor_email})
record_write("delete mis-dated on-call override", "DELETE",
             f"{PD}/schedules/{soc_sched_id}/overrides/{bad_override['id']}")

for tid in (sec_ticket_id, TRIGGER_TICKET_ID):
    record_write(f"close zoho ticket {tid}", "PATCH", f"{ZO}/tickets/{tid}",
                 {"status": "Closed"})

print("== Phase 5: read back ==")
mismatches = []

def expect(label, actual, wanted):
    if actual != wanted:
        mismatches.append(f"{label}: {actual!r} != {wanted!r}")

final_threats = {t["id"]: t for t in s1_all("/threats")}
for tid in broken_ids:
    info = final_threats[tid]["threatInfo"]
    expect(f"threat {tid} mitigation", info.get("mitigationStatus"), "mitigated")
    expect(f"threat {tid} verdict", info.get("analystVerdict"), "true_positive")
    expect(f"threat {tid} incident", info.get("incidentStatus"), "resolved")
w_info = final_threats[worked["id"]]["threatInfo"]
expect("worked example untouched verdict", w_info.get("analystVerdict"),
       "true_positive")

final_block = {str(b.get("value", "")).lower() for b in s1_all("/restrictions")}
for sha in night_shas:
    expect(f"blocklist {sha}", sha in final_block, True)

final_exc = s1_all("/exclusions")
expect("night exclusion gone",
       any(e["id"] in {b["id"] for b in bad_exclusions} for e in final_exc), False)

final_agents = {a["id"]: a for a in s1_all("/agents")}
expect("flagged host reconnected",
       final_agents[flagged["id"]].get("networkStatus"), "connected")
for a in stealth_hosts:
    expect(f"stealth host {a['computerName']} contained",
           final_agents[a["id"]].get("networkStatus"), "disconnected")

final_rules = zia_all("/firewallFilteringRules")
final_groups = {str(g["id"]): g for g in zia_all("/ipDestinationGroups")}

def effective_deny(ip):
    def covers(rule, ip):
        ips = {str(a) for a in (rule.get("destAddresses") or [])}
        for ref in rule.get("destIpGroups") or []:
            g = final_groups.get(str(ref["id"] if isinstance(ref, dict) else ref))
            if g:
                ips |= {str(a) for a in (g.get("ipAddresses") or [])}
                ips |= {str(a) for a in (g.get("addresses") or [])}
        return str(ip) in ips

    covering = [r for r in final_rules
                if str(r.get("state", "")).upper() == "ENABLED" and covers(r, ip)]
    blocks = [r for r in covering
              if str(r.get("action", "")).upper().startswith("BLOCK")]
    if not blocks:
        return False
    top_block = min(int(r.get("order", 0)) for r in blocks)
    allows = [r for r in covering
              if str(r.get("action", "")).upper().startswith("ALLOW")
              and int(r.get("order", 0)) < top_block]
    return not allows

for ip in c2_ips:
    expect(f"C2 {ip} effectively denied", effective_deny(ip), True)
expect("ZIA activation", get(f"{ZIA}/status").get("status"), "ACTIVE")

for inc in siem_incidents:
    final_inc = get(sn_url(f"{inc_base}/{inc['name']}"))
    num = inc["properties"].get("incidentNumber")
    expect(f"SIEM #{num} status", final_inc["properties"].get("status"), "Closed")
    expect(f"SIEM #{num} classification",
           final_inc["properties"].get("classification"), "TruePositive")

final_pd = get(f"{PD}/incidents/{pd_incident['id']}")["incident"]
expect("PD resolved", final_pd.get("status"), "resolved")

readback_window = urllib.parse.urlencode({
    "since": anchor.isoformat().replace("+00:00", "Z"),
    "until": bad_override["end"]})
final_overrides = get(
    f"{PD}/schedules/{soc_sched_id}/overrides?{readback_window}")["overrides"]
expect("mis-dated override gone",
       any((o.get("user") or {}).get("id") == first_paged["id"]
           for o in final_overrides), False)

for tid in (sec_ticket_id, TRIGGER_TICKET_ID):
    expect(f"zoho {tid} closed",
           str(get(f"{ZO}/tickets/{tid}").get("status", "")).lower(), "closed")

if mismatches:
    print("READBACK MISMATCHES:", file=sys.stderr)
    for m in mismatches:
        print("  " + m, file=sys.stderr)
    sys.exit(2)

print(f"ORACLE OK: {len(WRITES)} writes, zero mismatches")
