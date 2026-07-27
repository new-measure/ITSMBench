#!/usr/bin/env python3
import json
import os
import sys
import urllib.request
import urllib.parse
import urllib.error

TICKET_NUMBER = "SEC0001001"
GATEWAY = os.environ.get("EP13_GATEWAY")

SLUGS = {
    "teams": "microsoft-teams",
    "outlook": "outlook-calendar",
    "snow": "servicenow",
    "slack": "slack-admin",
    "zoom": "zoom-admin",
}

WRITES = []

def _host(slug):
    return f"{SLUGS.get(slug, slug)}.local.mock"

def _request(method, slug, path, query=None, body=None):
    host = _host(slug)
    if query:
        qs = urllib.parse.urlencode(query)
        path = f"{path}?{qs}"
    if GATEWAY:
        url = f"{GATEWAY}{path}"
        headers = {"Host": host}
    else:
        url = f"http://{host}:8080{path}"
        headers = {}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            if not raw:
                return {}
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return json.loads(raw)
        except Exception:
            return {"__http_error__": e.code, "__body__": raw.decode("utf-8", "replace")}

def GET(slug, path, query=None):
    return _request("GET", slug, path, query=query)

def POST(slug, path, body=None, query=None):
    return _request("POST", slug, path, query=query, body=body or {})

def PATCH(slug, path, body=None):
    return _request("PATCH", slug, path, body=body or {})

def DELETE(slug, path):
    return _request("DELETE", slug, path)

def slack_list(method_path, key, extra=None):
    out, cursor = [], ""
    while True:
        q = {"limit": 100}
        if cursor:
            q["cursor"] = cursor
        if extra:
            q.update(extra)
        r = GET("slack", method_path, q)
        out.extend(r.get(key, []) or [])
        cursor = ((r.get("response_metadata") or {}).get("next_cursor")) or ""
        if not cursor:
            break
    return out

def graph_list(slug, path):
    out = []
    q = {"$top": 100}
    while True:
        r = GET(slug, path, q)
        out.extend(r.get("value", []) or [])
        nxt = r.get("@odata.nextLink")
        if not nxt:
            break
        parsed = urllib.parse.urlparse(nxt)
        path = parsed.path
        q = dict(urllib.parse.parse_qsl(parsed.query))
    return out

def zoom_list(path, key):
    out = []
    page = 1
    while True:
        r = GET("zoom", path, {"page_size": 300, "page_number": page})
        rows = r.get(key, []) if isinstance(r, dict) else []
        out.extend(rows or [])
        total = r.get("total_records", len(out)) if isinstance(r, dict) else len(out)
        if not rows or len(out) >= total or len(rows) < 300:
            break
        page += 1
    return out

def snow_table(table, query=None):
    q = {"sysparm_limit": 1000}
    if query:
        q["sysparm_query"] = query
    r = GET("snow", f"/api/now/table/{table}", q)
    return r.get("result", []) if isinstance(r, dict) else []

def email_domain(email):
    email = str(email or "")
    return email.split("@")[-1].lower() if "@" in email else ""

def is_service_actor(actor):
    a = str(actor or "").lower()
    return a.startswith("svc")

def derive_org_domain(users):
    counts = {}
    for u in users:
        if u.get("is_restricted") or u.get("is_ultra_restricted") or u.get("is_bot"):
            continue
        d = email_domain(u.get("email"))
        if d:
            counts[d] = counts.get(d, 0) + 1
    if not counts:
        return "auric.com"
    return max(counts, key=counts.get)

def main():
    errors = []

    tickets = snow_table("u_security_exception", f"number={TICKET_NUMBER}")
    if not tickets:
        print(f"FATAL: trigger ticket {TICKET_NUMBER} not found", file=sys.stderr)
        sys.exit(2)
    ticket = tickets[0]
    print(f"[trigger] {ticket.get('number')}: {ticket.get('short_description')}")

    slack_channels = slack_list("/api/admin.conversations.search", "channels")
    slack_users = slack_list("/api/admin.users.list", "users")
    approved_apps = slack_list("/api/admin.apps.approved.list", "approved_apps")
    org_domain = derive_org_domain(slack_users)
    print(f"[derived] org domain = {org_domain}")

    teams = graph_list("teams", "/v1.0/teams")
    zoom_users = zoom_list("/users", "users")
    outlook_events = graph_list("outlook", "/v1.0/me/events")

    plan_disconnect, plan_remove_user = [], []
    plan_restrict = []
    plan_zoom = []
    plan_team_member_remove, plan_team_channel_delete = [], []
    plan_outlook = []

    for ch in slack_channels:
        if ch.get("is_ext_shared") and is_service_actor(ch.get("shared_by")):
            plan_disconnect.append(ch)

    for u in slack_users:
        if u.get("deleted"):
            continue
        dom = email_domain(u.get("email"))
        if dom and dom != org_domain and is_service_actor(u.get("added_by")):
            plan_remove_user.append(u)

    for a in approved_apps:
        if is_service_actor(a.get("approved_by")):
            plan_restrict.append(a)

    seen_mtg = set()
    for zu in zoom_users:
        uid = zu.get("id") or zu.get("email")
        if not uid:
            continue
        for m in zoom_list(f"/users/{urllib.parse.quote(str(uid))}/meetings", "meetings"):
            mid = str(m.get("id") or m.get("uuid") or "")
            if mid and mid not in seen_mtg:
                seen_mtg.add(mid)
                full = GET("zoom", f"/meetings/{urllib.parse.quote(mid)}")
                if isinstance(full, dict) and full.get("id"):
                    m = full
            settings = m.get("settings") or {}
            alt = str(settings.get("alternative_hosts") or "")
            ext = [e.strip() for e in alt.replace(";", ",").split(",")
                   if e.strip() and email_domain(e) and email_domain(e) != org_domain]
            if ext and is_service_actor(m.get("last_configured_by")):
                plan_zoom.append((m, ext, settings))

    for t in teams:
        tid = t.get("id")
        for mem in graph_list("teams", f"/v1.0/teams/{urllib.parse.quote(str(tid))}/members"):
            dom = email_domain(mem.get("email"))
            if dom and dom != org_domain and is_service_actor(mem.get("addedBy")):
                plan_team_member_remove.append((tid, mem))
        for ch in graph_list("teams", f"/v1.0/teams/{urllib.parse.quote(str(tid))}/channels"):
            if ch.get("membershipType") == "shared" and is_service_actor(ch.get("addedBy")):
                plan_team_channel_delete.append((tid, ch))

    for ev in outlook_events:
        if not is_service_actor(ev.get("configuredBy")):
            continue
        att = ev.get("attendees") or []
        keep, dropped = [], []
        for a in att:
            addr = ((a.get("emailAddress") or {}).get("address"))
            dom = email_domain(addr)
            if dom and dom != org_domain:
                dropped.append(addr)
            else:
                keep.append(a)
        if dropped:
            plan_outlook.append((ev, keep, dropped))

    print("\n=== PLAN ===")
    for ch in plan_disconnect:
        print(f"  slack disconnectShared {ch['id']} ({ch.get('name')})")
    for u in plan_remove_user:
        print(f"  slack users.remove {u['id']} ({u.get('email')})")
    for a in plan_restrict:
        print(f"  slack apps.restrict {a.get('app_id')}")
    for (m, ext, _s) in plan_zoom:
        print(f"  zoom fix meeting {m['id']} ({m.get('topic')}) strip {ext} + auth on")
    for (tid, mem) in plan_team_member_remove:
        print(f"  teams remove member {mem['id']} ({mem.get('email')}) from {tid}")
    for (tid, ch) in plan_team_channel_delete:
        print(f"  teams delete shared channel {ch['id']} from {tid}")
    for (ev, _k, dropped) in plan_outlook:
        print(f"  outlook drop {dropped} from event {ev['id']} ({ev.get('subject')})")
    print("=== END PLAN ===\n")

    for ch in plan_disconnect:
        POST("slack", "/api/admin.conversations.disconnectShared", {"channel_id": ch["id"]})
        WRITES.append(("slack.disconnect", ch["id"]))
    for u in plan_remove_user:
        team_ids = u.get("team_ids") or []
        tid = team_ids[0] if team_ids else None
        POST("slack", "/api/admin.users.remove", {"user_id": u["id"], "team_id": tid})
        WRITES.append(("slack.users.remove", u["id"]))
    for a in plan_restrict:
        POST("slack", "/api/admin.apps.restrict",
             {"app_id": a.get("app_id"), "team_id": a.get("team_id")})
        WRITES.append(("slack.apps.restrict", a.get("app_id")))
    for (m, ext, settings) in plan_zoom:
        alt = str(settings.get("alternative_hosts") or "")
        parts = [e.strip() for e in alt.replace(";", ",").split(",") if e.strip()]
        kept = [p for p in parts if email_domain(p) == org_domain]
        new_settings = dict(settings)
        new_settings["alternative_hosts"] = ";".join(kept)
        new_settings["meeting_authentication"] = True
        PATCH("zoom", f"/meetings/{urllib.parse.quote(str(m['id']))}",
              {"settings": new_settings})
        WRITES.append(("zoom.meeting.fix", m["id"]))
    for (tid, mem) in plan_team_member_remove:
        DELETE("teams", f"/v1.0/teams/{urllib.parse.quote(str(tid))}/members/{urllib.parse.quote(str(mem['id']))}")
        WRITES.append(("teams.member.remove", mem["id"]))
    for (tid, ch) in plan_team_channel_delete:
        DELETE("teams", f"/v1.0/teams/{urllib.parse.quote(str(tid))}/channels/{urllib.parse.quote(str(ch['id']))}")
        WRITES.append(("teams.channel.delete", ch["id"]))
    for (ev, keep, _dropped) in plan_outlook:
        PATCH("outlook", f"/v1.0/me/events/{urllib.parse.quote(str(ev['id']))}",
              {"attendees": keep})
        WRITES.append(("outlook.event.fix", ev["id"]))

    slack_channels2 = slack_list("/api/admin.conversations.search", "channels")
    by_id = {c["id"]: c for c in slack_channels2}
    for ch in plan_disconnect:
        c = by_id.get(ch["id"], {})
        if c.get("is_ext_shared"):
            errors.append(f"channel {ch['id']} still ext_shared")
    slack_users2 = {u["id"]: u for u in slack_list("/api/admin.users.list", "users")}
    for u in plan_remove_user:
        if u["id"] in slack_users2:
            errors.append(f"guest {u['id']} still listed")
    approved2 = {a.get("app_id") for a in slack_list("/api/admin.apps.approved.list", "approved_apps")}
    for a in plan_restrict:
        if a.get("app_id") in approved2:
            errors.append(f"app {a.get('app_id')} still approved")
    for (m, ext, _s) in plan_zoom:
        full = GET("zoom", f"/meetings/{urllib.parse.quote(str(m['id']))}")
        s = full.get("settings") or {}
        alt = str(s.get("alternative_hosts") or "")
        if any(email_domain(e) and email_domain(e) != org_domain
               for e in alt.replace(";", ",").split(",")):
            errors.append(f"meeting {m['id']} still has external alt host")
        if not s.get("meeting_authentication"):
            errors.append(f"meeting {m['id']} auth still off")
    for (tid, mem) in plan_team_member_remove:
        members2 = graph_list("teams", f"/v1.0/teams/{urllib.parse.quote(str(tid))}/members")
        if any(mm.get("id") == mem["id"] for mm in members2):
            errors.append(f"team member {mem['id']} still present")
    for (tid, ch) in plan_team_channel_delete:
        chans2 = graph_list("teams", f"/v1.0/teams/{urllib.parse.quote(str(tid))}/channels")
        if any(cc.get("id") == ch["id"] for cc in chans2):
            errors.append(f"shared channel {ch['id']} still present")
    ev_by = {e["id"]: e for e in graph_list("outlook", "/v1.0/me/events")}
    for (ev, _k, dropped) in plan_outlook:
        e2 = ev_by.get(ev["id"], {})
        addrs = [((a.get("emailAddress") or {}).get("address")) for a in (e2.get("attendees") or [])]
        if any(email_domain(x) and email_domain(x) != org_domain for x in addrs) and not e2.get("isCancelled"):
            errors.append(f"event {ev['id']} still has external attendee")

    print(f"\n[writes] {len(WRITES)} performed")
    if errors:
        print("READBACK MISMATCHES:", file=sys.stderr)
        for e in errors:
            print("  " + e, file=sys.stderr)
        sys.exit(1)
    print("OK: oracle end-state verified, zero readback mismatches")

if __name__ == "__main__":
    main()
