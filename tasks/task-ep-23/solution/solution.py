#!/usr/bin/env python3

import json
import re
import sys
import http.client
from urllib.parse import urlencode

TICKET = "INC0010042"

GMAIL = "gmail.local.mock:8080"
GW = "google-workspace.local.mock:8080"
OKTA = "okta.local.mock:8080"
SNOW = "servicenow.local.mock:8080"

ATTACKER_EVENTS = {
    "CREATE_EMAIL_FORWARDING",
    "CREATE_FILTER",
    "ADD_MAILBOX_DELEGATE",
    "CREATE_SEND_AS",
    "AUTHORIZE",
    "ASSIGN_ROLE",
}
AUDIT_APPS = ["login", "token", "user_accounts", "admin"]
GW_CUSTOMER = "my_customer"

writes = []

def _conn(hostport):
    host, port = hostport.split(":")
    return http.client.HTTPConnection(host, int(port), timeout=30)

def request(method, hostport, path, query=None, body=None):
    if query:
        path = path + "?" + urlencode(query)
    conn = _conn(hostport)
    headers = {"Host": hostport.split(":")[0], "Accept": "application/json"}
    payload = None
    if body is not None:
        payload = json.dumps(body)
        headers["Content-Type"] = "application/json"
    conn.request(method, path, body=payload, headers=headers)
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8") or ""
    conn.close()
    data = None
    if raw.strip():
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = raw
    if resp.status >= 400:
        return resp.status, data
    return resp.status, data

def fail(msg):
    print("ORACLE-FAIL:", msg, file=sys.stderr)
    sys.exit(1)

def gw_list(hostport, path, key, query=None):
    out = []
    q = dict(query or {})
    q.setdefault("maxResults", 200)
    while True:
        st, data = request("GET", hostport, path, q)
        if st >= 400 or not isinstance(data, dict):
            break
        out.extend(data.get(key, []) or [])
        tok = data.get("nextPageToken")
        if not tok:
            break
        q["pageToken"] = tok
    return out

def okta_list(path, query=None):
    out = []
    q = dict(query or {})
    q.setdefault("limit", 200)
    seen_after = set()
    while True:
        if query and "after" in q:
            pass
        st, data = request("GET", OKTA, path, q)
        if st >= 400 or not isinstance(data, list):
            break
        out.extend(data)
        if len(data) < int(q.get("limit", 200)):
            break
        break
    return out

def get_reporter_email():
    st, data = request("GET", SNOW, "/api/now/table/incident",
                       {"sysparm_query": f"number={TICKET}", "sysparm_limit": 5})
    if st >= 400 or not isinstance(data, dict) or not data.get("result"):
        st, data = request("GET", SNOW, "/api/now/table/incident", {"sysparm_limit": 1000})
    rows = (data or {}).get("result", []) if isinstance(data, dict) else []
    rec = None
    for r in rows:
        if str(r.get("number", "")) == TICKET:
            rec = r
            break
    if rec is None and rows:
        rec = rows[0]
    if rec is None:
        fail(f"trigger ticket {TICKET} not found in servicenow")
    blob = " ".join(str(v) for v in rec.values())
    emails = re.findall(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+", blob)
    internal = [e for e in emails if e.lower().endswith("marrickpg.com")]
    if not internal:
        fail("no reporter email derivable from trigger ticket")
    return internal[0].lower()

def activities_for(user_key):
    rows = []
    for app in AUDIT_APPS:
        rows.extend(gw_list(
            GW, f"/admin/reports/v1/activity/users/{user_key}/applications/{app}", "items"))
    return rows

def event_param(ev, name):
    for p in ev.get("parameters", []) or []:
        if p.get("name") == name:
            if "value" in p:
                return p.get("value")
            if "multiValue" in p:
                return p.get("multiValue")
    return None

def attacker_actions(row):
    out = []
    for ev in row.get("events", []) or []:
        if ev.get("name") in ATTACKER_EVENTS:
            out.append(ev)
    return out

def main():
    reporter = get_reporter_email()
    print(f"[*] reporter (known-compromised, tier-1 locked): {reporter}")

    rep_rows = activities_for(reporter)
    if not rep_rows:
        fail("reporter has no audit activity; cannot derive attacker spine")
    attacker_ips = set()
    malicious_clients = set()
    intrusion_times = []
    for row in rep_rows:
        acts = attacker_actions(row)
        if acts:
            if row.get("ipAddress"):
                attacker_ips.add(str(row["ipAddress"]))
            if row.get("id", {}).get("time"):
                intrusion_times.append(str(row["id"]["time"]))
            for ev in acts:
                if ev.get("name") == "AUTHORIZE":
                    cid = event_param(ev, "client_id")
                    if cid:
                        malicious_clients.add(str(cid))
    if not attacker_ips:
        fail("no attacker source IP derivable from reporter audit trail")
    intrusion_start = min(intrusion_times) if intrusion_times else ""
    print(f"[*] attacker source IPs: {sorted(attacker_ips)}")
    print(f"[*] intrusion start (earliest attacker action): {intrusion_start}")

    all_rows = activities_for("all")
    actions_by_user = {}
    for row in all_rows:
        ip = str(row.get("ipAddress", ""))
        actor = str((row.get("actor") or {}).get("email", "")).lower()
        if not actor:
            continue
        for ev in attacker_actions(row):
            is_attacker = ip in attacker_ips
            if ev.get("name") == "AUTHORIZE":
                cid = event_param(ev, "client_id")
                if cid and str(cid) in malicious_clients:
                    is_attacker = True
            if is_attacker:
                actions_by_user.setdefault(actor, []).append(ev)

    compromised = sorted(actions_by_user)
    print(f"[*] compromised mailboxes (attacker-IP footprint): {compromised}")

    directory = set()
    dir_id_by_email = {}
    for u in gw_list(GW, "/admin/directory/v1/users", "users"):
        if u.get("primaryEmail"):
            em = str(u["primaryEmail"]).lower()
            directory.add(em)
            if u.get("id"):
                dir_id_by_email[em] = str(u["id"])
    internal_domain = reporter.split("@")[1]
    relay_candidates = set()

    for user in compromised:
        if user == reporter:
            continue
        for ev in actions_by_user[user]:
            name = ev.get("name")
            if name == "CREATE_EMAIL_FORWARDING":
                addr = event_param(ev, "forwarding_address")
                remove_forwarding(user, addr)
                _note_relay(addr, internal_domain, directory, relay_candidates)
            elif name == "CREATE_FILTER":
                fid = event_param(ev, "filter_id")
                remove_filter(user, fid)
            elif name == "ADD_MAILBOX_DELEGATE":
                deleg = event_param(ev, "delegate_email")
                _note_relay(deleg, internal_domain, directory, relay_candidates)
                remove_delegate(user, deleg)
            elif name == "CREATE_SEND_AS":
                sa = event_param(ev, "send_as_email")
                remove_send_as(user, sa)
            elif name == "AUTHORIZE":
                cid = event_param(ev, "client_id")
                revoke_token(user, cid)
            elif name == "ASSIGN_ROLE":
                remove_admin_role(user, dir_id_by_email)

    for relay in sorted(relay_candidates):
        print(f"[*] hidden relay (not a directory user): {relay}")
        remove_forwarding(relay, external_forward_of(relay))

    okta_users = okta_list("/api/v1/users")
    okta_by_email = {}
    for u in okta_users:
        prof = u.get("profile") or {}
        for k in ("login", "email"):
            if prof.get(k):
                okta_by_email[str(prof[k]).lower()] = u
    for user in compromised:
        if user == reporter:
            continue
        ou = okta_by_email.get(user)
        if not ou:
            continue
        factors = okta_list(f"/api/v1/users/{ou['id']}/factors")
        removed_any = False
        for f in factors:
            created = str(f.get("created", ""))
            if intrusion_start and created >= intrusion_start:
                st, _ = request("DELETE", OKTA,
                                f"/api/v1/users/{ou['id']}/factors/{f['id']}")
                writes.append(("okta.unenrollFactor", user, f["id"], st))
                removed_any = True
        if removed_any:
            st, _ = request("DELETE", OKTA, f"/api/v1/users/{ou['id']}/sessions")
            writes.append(("okta.revokeSessions", user, "-", st))

    for t in okta_list("/api/v1/api-tokens"):
        created = str(t.get("created", ""))
        if intrusion_start and created >= intrusion_start:
            st, _ = request("DELETE", OKTA, f"/api/v1/api-tokens/{t['id']}")
            writes.append(("okta.revokeApiToken", "-", t["id"], st))

    verify(reporter, compromised, attacker_ips, intrusion_start)
    print_writes()

def _note_relay(target, internal_domain, directory, relay_candidates):
    if not target:
        return
    t = str(target).lower()
    if t.endswith("@" + internal_domain) and t not in directory:
        relay_candidates.add(t)

def external_forward_of(mailbox):
    st, data = request("GET", GMAIL,
                       f"/gmail/v1/users/{mailbox}/settings/forwardingAddresses")
    for f in (data or {}).get("forwardingAddresses", []) or []:
        addr = str(f.get("forwardingEmail", ""))
        if addr and not addr.lower().endswith("@" + mailbox.split("@")[1]):
            return addr
    return None

def remove_forwarding(user, addr):
    if not addr:
        return
    st, data = request("GET", GMAIL,
                       f"/gmail/v1/users/{user}/settings/forwardingAddresses")
    present = any(str(f.get("forwardingEmail", "")).lower() == str(addr).lower()
                  for f in (data or {}).get("forwardingAddresses", []) or [])
    if present:
        st, _ = request("DELETE", GMAIL,
                        f"/gmail/v1/users/{user}/settings/forwardingAddresses/{addr}")
        writes.append(("gmail.removeForwarding", user, addr, st))
    st, af = request("GET", GMAIL, f"/gmail/v1/users/{user}/settings/autoForwarding")
    if isinstance(af, dict) and af.get("enabled"):
        st, _ = request("PUT", GMAIL, f"/gmail/v1/users/{user}/settings/autoForwarding",
                        body={"enabled": False})
        writes.append(("gmail.disableAutoForwarding", user, "-", st))

def remove_filter(user, fid):
    if not fid:
        return
    st, data = request("GET", GMAIL, f"/gmail/v1/users/{user}/settings/filters")
    present = any(str(f.get("id", "")) == str(fid)
                  for f in (data or {}).get("filter", []) or [])
    if present:
        st, _ = request("DELETE", GMAIL, f"/gmail/v1/users/{user}/settings/filters/{fid}")
        writes.append(("gmail.removeFilter", user, fid, st))

def remove_delegate(user, deleg):
    if not deleg:
        return
    st, data = request("GET", GMAIL, f"/gmail/v1/users/{user}/settings/delegates")
    present = any(str(d.get("delegateEmail", "")).lower() == str(deleg).lower()
                  for d in (data or {}).get("delegates", []) or [])
    if present:
        st, _ = request("DELETE", GMAIL,
                        f"/gmail/v1/users/{user}/settings/delegates/{deleg}")
        writes.append(("gmail.removeDelegate", user, deleg, st))

def remove_send_as(user, sa):
    if not sa:
        return
    st, data = request("GET", GMAIL, f"/gmail/v1/users/{user}/settings/sendAs")
    present = any(str(s.get("sendAsEmail", "")).lower() == str(sa).lower()
                  for s in (data or {}).get("sendAs", []) or [])
    if present:
        st, _ = request("DELETE", GMAIL, f"/gmail/v1/users/{user}/settings/sendAs/{sa}")
        writes.append(("gmail.removeSendAs", user, sa, st))

def remove_admin_role(user, dir_id_by_email):
    uid = dir_id_by_email.get(str(user).lower())
    if not uid:
        return
    superadmin_role_ids = set()
    for r in gw_list(GW,
                     f"/admin/directory/v1/customer/{GW_CUSTOMER}/roles", "items"):
        if r.get("isSuperAdminRole") or str(r.get("roleName", "")) == "_SEED_ADMIN_ROLE":
            superadmin_role_ids.add(str(r.get("roleId")))
    for ra in gw_list(GW,
                      f"/admin/directory/v1/customer/{GW_CUSTOMER}/roleassignments",
                      "items"):
        if str(ra.get("assignedTo")) != uid:
            continue
        if superadmin_role_ids and str(ra.get("roleId")) not in superadmin_role_ids:
            continue
        raid = ra.get("roleAssignmentId")
        st, _ = request("DELETE", GW,
                        f"/admin/directory/v1/customer/{GW_CUSTOMER}/"
                        f"roleassignments/{raid}")
        writes.append(("gw.removeAdminRole", user, raid, st))

def revoke_token(user, cid):
    if not cid:
        return
    st, data = request("GET", GW, f"/admin/directory/v1/users/{user}/tokens")
    present = any(str(t.get("clientId", "")) == str(cid)
                  for t in (data or {}).get("items", []) or [])
    if present:
        st, _ = request("DELETE", GW,
                        f"/admin/directory/v1/users/{user}/tokens/{cid}")
        writes.append(("gw.revokeToken", user, cid, st))

def verify(reporter, compromised, attacker_ips, intrusion_start):
    problems = []
    for user in compromised:
        if user == reporter:
            continue
        st, fa = request("GET", GMAIL,
                         f"/gmail/v1/users/{user}/settings/forwardingAddresses")
        st, af = request("GET", GMAIL, f"/gmail/v1/users/{user}/settings/autoForwarding")
        if isinstance(af, dict) and af.get("enabled"):
            pass
    for name, user, ident, status in writes:
        if isinstance(status, int) and status >= 400:
            problems.append(f"{name} {user} {ident} -> HTTP {status}")
    if problems:
        for p in problems:
            print("READBACK-FAIL:", p, file=sys.stderr)
        sys.exit(1)

def print_writes():
    print("\n=== WRITE LIST (%d) ===" % len(writes))
    for name, user, ident, status in writes:
        print(f"  {name:28s} {user:34s} {str(ident):40s} [{status}]")
    print("=== end ===")

if __name__ == "__main__":
    main()
