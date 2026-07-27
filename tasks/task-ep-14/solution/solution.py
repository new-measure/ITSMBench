#!/usr/bin/env python3

import json
import sys
import urllib.request
import urllib.error
import urllib.parse

TRIGGER_INCIDENT = "INC0007001"

SN = "http://servicenow.local.mock:8080"
D42 = "http://device42.local.mock:8080"
SLACK = "http://slack.local.mock:8080"
PD = "http://pagerduty.local.mock:8080"
JSM = "http://jira-service-management.local.mock:8080"
SNIPE = "http://snipeit.local.mock:8080/api/v1"

WRITES = []

def _req(method, url, body=None, headers=None):
    data = None
    hdrs = {"Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    if body is not None:
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        raise RuntimeError(f"{method} {url} -> {e.code}: {raw[:300]}")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}

def norm(s):
    return "".join(ch for ch in str(s or "").lower() if ch.isalnum())

def sn_list(table, query=None):
    out, offset, limit = [], 0, 100
    while True:
        url = f"{SN}/api/now/table/{table}?sysparm_limit={limit}&sysparm_offset={offset}"
        if query:
            url += f"&sysparm_query={urllib.parse.quote(query)}"
        page = _req("GET", url).get("result", [])
        out.extend(page)
        if len(page) < limit:
            break
        offset += limit
    return out

def sn_get(table, sys_id):
    return _req("GET", f"{SN}/api/now/table/{table}/{sys_id}").get("result", {})

def sn_get_by_number(table, number):
    r = _req("GET", f"{SN}/api/now/table/{table}?sysparm_query=number={number}").get("result", [])
    return r[0] if r else None

def sn_patch(table, sys_id, body):
    WRITES.append(f"SN PATCH {table}/{sys_id} {body}")
    return _req("PATCH", f"{SN}/api/now/table/{table}/{sys_id}", body).get("result", {})

def sn_create(table, body):
    WRITES.append(f"SN CREATE {table} {body}")
    return _req("POST", f"{SN}/api/now/table/{table}", body).get("result", {})

def d42_list(resource, key, path="2.0"):
    out, offset, limit = [], 0, 1000
    while True:
        url = f"{D42}/api/{path}/{resource}/?limit={limit}&offset={offset}"
        j = _req("GET", url)
        page = j.get(key, [])
        out.extend(page)
        total = j.get("total_count", len(out))
        if len(page) < limit or offset + len(page) >= total:
            break
        offset += limit
    return out

def pd_list(resource, key):
    out, offset, limit = [], 0, 100
    while True:
        j = _req("GET", f"{PD}/{resource}?limit={limit}&offset={offset}")
        page = j.get(key, [])
        out.extend(page)
        if not j.get("more") or len(page) < limit:
            break
        offset += limit
    return out

def snipe_list(resource):
    out, offset, limit = [], 0, 500
    while True:
        j = _req("GET", f"{SNIPE}/{resource}?limit={limit}&offset={offset}")
        page = j.get("rows", [])
        out.extend(page)
        total = j.get("total", len(out))
        if len(page) < limit or offset + len(page) >= total:
            break
        offset += limit
    return out

def slack_channels():
    out, cursor = [], ""
    while True:
        url = f"{SLACK}/api/conversations.list?limit=1000&exclude_archived=false"
        if cursor:
            url += f"&cursor={cursor}"
        j = _req("GET", url)
        out.extend(j.get("channels", []))
        cursor = (j.get("response_metadata") or {}).get("next_cursor") or ""
        if not cursor:
            break
    return out

def slack_history(channel):
    out, cursor = [], ""
    while True:
        url = f"{SLACK}/api/conversations.history?channel={channel}&limit=1000"
        if cursor:
            url += f"&cursor={cursor}"
        j = _req("GET", url)
        out.extend(j.get("messages", []))
        cursor = (j.get("response_metadata") or {}).get("next_cursor") or ""
        if not cursor:
            break
    return out

def slack_replies(channel, ts):
    j = _req("GET", f"{SLACK}/api/conversations.replies?channel={channel}&ts={ts}&limit=1000")
    return j.get("messages", [])

def jsm_requests():
    out, start = [], 0
    while True:
        j = _req("GET", f"{JSM}/rest/servicedeskapi/request?limit=50&start={start}")
        vals = j.get("values", [])
        out.extend(vals)
        if j.get("isLastPage") or not vals:
            break
        start += len(vals)
    return out

INSTALLED = {"1", "installed", "operational"}

def is_prod(rec):
    return norm(rec.get("u_environment") or rec.get("environment")) == "production"

def main():
    trigger = sn_get_by_number("incident", TRIGGER_INCIDENT)
    if not trigger:
        print(f"FATAL: trigger incident {TRIGGER_INCIDENT} not found", file=sys.stderr)
        sys.exit(2)

    changes = sn_list("change_request")
    approvals = sn_list("sysapproval_approver")
    appls = sn_list("cmdb_ci_appl")
    dbs = sn_list("cmdb_ci_database")
    servers = sn_list("cmdb_ci_server")
    services = sn_list("cmdb_ci_service_technical") + sn_list("cmdb_ci_service")

    d42_services = d42_list("services", "services", "2.0")
    d42_devices = d42_list("devices", "devices", "2.0")

    pd_incidents = pd_list("incidents", "incidents")
    pd_users = pd_list("users", "users")

    snipe_assets = snipe_list("hardware")
    snipe_status = snipe_list("statuslabels")

    reality_ver = {norm(s.get("displayname") or s.get("name")): s for s in d42_services}
    reality_dev = {norm(d.get("name")): d for d in d42_devices}
    service_by_id = {s.get("sys_id"): s for s in services}
    change_target_norm = {}
    for ch in changes:
        svc = service_by_id.get(ch.get("u_service"))
        change_target_norm[ch["sys_id"]] = norm(svc.get("name")) if svc else norm(ch.get("short_description"))

    def approval_state_for(change_sys_id):
        for ap in approvals:
            if ap.get("sysapproval") == change_sys_id:
                return norm(ap.get("state"))
        return None

    plan_patches = []
    plan_creates = []

    drifted_ci_norms = set()
    for ci in appls + dbs:
        if not is_prod(ci):
            continue
        r = reality_ver.get(norm(ci.get("name")))
        if not r:
            continue
        rv = str(r.get("version") or "")
        if rv and rv != str(ci.get("version") or ""):
            table = ci.get("sys_class_name") or "cmdb_ci_appl"
            body = {"version": rv, "install_status": "1", "operational_status": "1",
                    "last_discovered": r.get("last_updated") or r.get("last_edited")}
            plan_patches.append((table, ci["sys_id"], body,
                                 lambda rec, rv=rv: rv in str(rec.get("version") or "")))
            drifted_ci_norms.add(norm(ci.get("name")))

    for ch in changes:
        if str(ch.get("state")) == "3":
            continue
        tgt = change_target_norm.get(ch["sys_id"])
        if tgt in drifted_ci_norms and approval_state_for(ch["sys_id"]) == "approved":
            plan_patches.append(("change_request", ch["sys_id"],
                                 {"state": "3", "close_code": "successful"},
                                 lambda rec: str(rec.get("state")) == "3"
                                 and norm(rec.get("close_code")) == "successful"))

    cmdb_server_keys = set()
    for s in servers:
        cmdb_server_keys.add(norm(s.get("name")))
        cmdb_server_keys.add(norm(s.get("fqdn")))
    for dev in d42_devices:
        if dev.get("archived") is True or dev.get("in_service") is False:
            continue
        if not is_prod(dev):
            continue
        if norm(dev.get("type") or "physical") not in ("physical", "virtual", "server", ""):
            continue
        nm = norm(dev.get("name"))
        if nm in cmdb_server_keys:
            continue
        fqdn = dev.get("fqdn") or f"{dev.get('name')}.prod.northwind.internal"
        body = {"name": dev.get("name"), "fqdn": fqdn, "ip_address": dev.get("ip") or "",
                "u_environment": "production", "install_status": "1",
                "operational_status": "1", "discovery_source": "Device42"}
        plan_creates.append(("cmdb_ci_server", body,
                             lambda rec, nm=nm: norm(rec.get("name")) == nm or norm(rec.get("fqdn")).startswith(nm)))

    deployed_ids, archived_id = set(), None
    for st in snipe_status:
        t = norm(st.get("status_type") or st.get("status_meta") or st.get("name"))
        if "archiv" in t:
            archived_id = st.get("id")
        if "deploy" in t or "ready" in t:
            deployed_ids.add(str(st.get("id")))
    for s in servers:
        if not is_prod(s):
            continue
        if norm(s.get("install_status")) not in INSTALLED:
            continue
        r = reality_dev.get(norm(s.get("name")))
        decommissioned = (r is None) or (r.get("archived") is True) or (r.get("in_service") is False)
        if not decommissioned:
            continue
        plan_patches.append(("cmdb_ci_server", s["sys_id"],
                             {"install_status": "7", "operational_status": "6"},
                             lambda rec: str(rec.get("install_status")) == "7"))
        serial = s.get("serial_number") or s.get("u_serial")
        if serial and archived_id is not None:
            for a in snipe_assets:
                if norm(a.get("serial")) == norm(serial):
                    plan_patches.append(("__snipe__", a.get("id"),
                                         {"status_id": archived_id},
                                         lambda rec, aid=str(archived_id): str(
                                             (rec.get("status_label") or {}).get("id")) == aid))

    channels = slack_channels()
    cm = next((c for c in channels if "change" in norm(c.get("name"))), None)
    cm_msgs = slack_history(cm["id"]) if cm else []

    def slack_approved(change_number):
        key = norm(change_number)
        for m in cm_msgs:
            if key and key in norm(m.get("text")):
                for r in (m.get("reactions") or []):
                    if "check" in norm(r.get("name")) and int(r.get("count") or 0) >= 1:
                        return True
                for rp in slack_replies(cm["id"], m.get("ts")):
                    if "approved" in norm(rp.get("text")):
                        return True
        return False

    for ap in approvals:
        if norm(ap.get("state")) != "requested":
            continue
        ch = next((c for c in changes if c["sys_id"] == ap.get("sysapproval")), None)
        if not ch or not is_prod(ch):
            continue
        if not slack_approved(ch.get("number")):
            continue
        plan_patches.append(("sysapproval_approver", ap["sys_id"],
                             {"state": "approved"},
                             lambda rec: norm(rec.get("state")) == "approved"))

    actor_email = next((u.get("email") for u in pd_users if u.get("email")), None)
    for inc in pd_incidents:
        if norm(inc.get("status")) not in ("triggered", "acknowledged"):
            continue
        svc = (inc.get("service") or {})
        svc_norm = norm(svc.get("summary") or svc.get("name"))
        title_norm = norm(inc.get("title"))
        cands = [ch for ch in changes
                 if norm(ch.get("close_code")) == "successful"
                 and change_target_norm.get(ch["sys_id"]) == svc_norm]
        if len(cands) > 1:
            kw = [t for t in ("ratelimiter", "limiter", "failover", "rollout",
                              "config", "deploy") if t in title_norm]
            narrowed = [ch for ch in cands
                        if any(k in norm(ch.get("short_description")) for k in kw)]
            if len(narrowed) == 1:
                cands = narrowed
        if len(cands) == 1:
            ch = cands[0]
            plan_patches.append(("change_request", ch["sys_id"],
                                 {"close_code": "unsuccessful"},
                                 lambda rec: norm(rec.get("close_code")) in ("unsuccessful", "failed")))
        plan_patches.append(("__pd__", inc.get("id"),
                             {"status": "resolved", "email": actor_email},
                             lambda rec: norm(rec.get("status")) == "resolved"))

    pd_services = pd_list("services", "services")
    pd_eps = pd_list("escalation_policies", "escalation_policies")
    ep_by_id = {e.get("id"): e for e in pd_eps}

    def ep_team_id(ep):
        ts = (ep or {}).get("teams") or []
        return ts[0].get("id") if ts else None

    policy_for_team = {}
    for e in pd_eps:
        t = ep_team_id(e)
        if t and t not in policy_for_team:
            policy_for_team[t] = e.get("id")
    for svc in pd_services:
        teams = svc.get("teams") or []
        own = teams[0].get("id") if teams else None
        cur_ep = ep_by_id.get((svc.get("escalation_policy") or {}).get("id"))
        cur_team = ep_team_id(cur_ep)
        if own and cur_team and own != cur_team and own in policy_for_team:
            correct = policy_for_team[own]
            plan_patches.append(("__pdsvc__", svc.get("id"),
                                 {"escalation_policy": correct},
                                 lambda rec, cid=correct: ((rec.get("escalation_policy") or {}).get("id")) == cid))

    print(f"[oracle] planned {len(plan_patches)} patches, {len(plan_creates)} creates")
    for table, body, _ in plan_creates:
        sn_create(table, body)
    for table, sid, body, _ in plan_patches:
        if table == "__pd__":
            email = body.pop("email")
            WRITES.append(f"PD PUT incidents/{sid} {body} (From:{email})")
            _req("PUT", f"{PD}/incidents/{sid}",
                 {"incident": {"type": "incident_reference", "status": "resolved",
                               "resolution": "Change rolled back; reconciled during CAB catch-up."}},
                 headers={"From": email or ""})
        elif table == "__snipe__":
            WRITES.append(f"SNIPE PATCH hardware/{sid} {body}")
            _req("PATCH", f"{SNIPE}/hardware/{sid}", body)
        elif table == "__pdsvc__":
            WRITES.append(f"PD PUT services/{sid} {body}")
            _req("PUT", f"{PD}/services/{sid}",
                 {"service": {"escalation_policy": {"id": body["escalation_policy"],
                                                    "type": "escalation_policy_reference"}}})
        else:
            sn_patch(table, sid, body)

    print("[oracle] WRITES:")
    for w in WRITES:
        print("   ", w)

    mismatches = []
    for table, body, verify in plan_creates:
        rows = sn_list(table)
        if not any(verify(r) for r in rows):
            mismatches.append(f"create {table} not verifiable: {body}")
    for table, sid, body, verify in plan_patches:
        if table == "__pd__":
            rec = _req("GET", f"{PD}/incidents/{sid}").get("incident", {})
        elif table == "__snipe__":
            rec = _req("GET", f"{SNIPE}/hardware/{sid}")
        elif table == "__pdsvc__":
            rec = _req("GET", f"{PD}/services/{sid}").get("service", {})
        else:
            rec = sn_get(table, sid)
        if not verify(rec):
            mismatches.append(f"readback mismatch {table}/{sid}: wanted {body}, got "
                              f"{ {k: rec.get(k) for k in ('version','state','close_code','install_status','status')} }")

    if mismatches:
        print("[oracle] READBACK MISMATCHES:", file=sys.stderr)
        for m in mismatches:
            print("   ", m, file=sys.stderr)
        sys.exit(1)
    print("[oracle] all writes verified. done.")

if __name__ == "__main__":
    main()
