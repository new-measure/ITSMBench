import json
import os
import urllib.parse
import urllib.request
import urllib.error

GATEWAY = os.environ.get("EP13_GATEWAY")

SLUGS = {
    "teams": "microsoft-teams", "outlook": "outlook-calendar",
    "snow": "servicenow", "slack": "slack-admin", "zoom": "zoom-admin",
}
ORG = "auric.com"

C_FIRM, C_HWRD, C_SUPO = "C0FIRMENG", "C0HWROAD", "C0SUPPOPS"
C_SUPC, C_BEAC, C_PART = "C0SUPCHAIN", "C0BEACONCON", "C0PARTNRINT"
UG_ORB, UG_KES, UG_MER = "UG0ORBITAL", "UG0KESTREL", "UG0MERIDN"
UG_NWD, UG_NW2, UG_OLD = "UG0NWIND", "UG0NWIND2", "UG0ORBOLD"
A_POLL, A_LEGIT = "A0POLLHIVE", "A0LEGITBOT"
M_FSEC, W_SUMMIT = "80010001", "91230001"
T_ENG, T_LIA = "team-roboeng", "team-liaison"
CH_BEAC, MEM_G, MEM_LEG = "ch-beacon-sync", "mem-guest-kestrel", "mem-guest-nwind"
EV_RR, EV_CON = "ev-roadmap-review", "ev-consortium-sync"

def _host(slug):
    return f"{SLUGS.get(slug, slug)}.local.mock"

def _req(method, slug, path, query=None, body=None):
    host = _host(slug)
    if query:
        path = f"{path}?{urllib.parse.urlencode(query)}"
    if GATEWAY:
        url, headers = f"{GATEWAY}{path}", {"Host": host}
    else:
        url, headers = f"http://{host}:8080{path}", {}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return json.loads(raw)
        except Exception:
            return {"__status__": e.code}

def GET(slug, path, query=None):
    return _req("GET", slug, path, query=query)

def email_domain(e):
    e = str(e or "")
    return e.split("@")[-1].lower() if "@" in e else ""

def slack_all(path, key, extra=None):
    out, cursor = [], ""
    while True:
        q = {"limit": 100}
        if cursor:
            q["cursor"] = cursor
        if extra:
            q.update(extra)
        r = GET("slack", path, q)
        out.extend(r.get(key, []) or [])
        cursor = ((r.get("response_metadata") or {}).get("next_cursor")) or ""
        if not cursor:
            break
    return out

def graph_all(slug, path):
    out, q = [], {"$top": 100}
    while True:
        r = GET(slug, path, q)
        out.extend(r.get("value", []) or [])
        nxt = r.get("@odata.nextLink")
        if not nxt:
            break
        pu = urllib.parse.urlparse(nxt)
        path, q = pu.path, dict(urllib.parse.parse_qsl(pu.query))
    return out

def zoom_all(path, key):
    out, page = [], 1
    while True:
        r = GET("zoom", path, {"page_size": 300, "page_number": page})
        rows = r.get(key, []) if isinstance(r, dict) else []
        out.extend(rows or [])
        total = r.get("total_records", len(out)) if isinstance(r, dict) else len(out)
        if not rows or len(out) >= total or len(rows) < 300:
            break
        page += 1
    return out

def channels():
    return {c["id"]: c for c in slack_all("/api/admin.conversations.search", "channels")}

def users():
    return {u["id"]: u for u in slack_all("/api/admin.users.list", "users")}

def approved_app_ids():
    return {a.get("app_id") for a in slack_all("/api/admin.apps.approved.list", "approved_apps")}

def restricted_app_ids():
    return {a.get("app_id") for a in slack_all("/api/admin.apps.restricted.list", "restricted_apps")}

def meeting(mid):
    return GET("zoom", f"/meetings/{mid}")

def all_meetings():
    out = {}
    for zu in zoom_all("/users", "users"):
        uid = zu.get("id") or zu.get("email")
        for m in zoom_all(f"/users/{urllib.parse.quote(str(uid))}/meetings", "meetings"):
            out[str(m.get("id"))] = m
    return out

def team_members(tid):
    return graph_all("teams", f"/v1.0/teams/{tid}/members")

def team_channels(tid):
    return graph_all("teams", f"/v1.0/teams/{tid}/channels")

def me_events():
    return {e["id"]: e for e in graph_all("outlook", "/v1.0/me/events")}

def _no_ext_cohost(m):
    alt = str((m.get("settings") or {}).get("alternative_hosts") or "")
    return not any(email_domain(e) and email_domain(e) != ORG
                   for e in alt.replace(";", ",").split(","))

def _event_ext_attendees(e):
    return [a for a in (e.get("attendees") or [])
            if email_domain((a.get("emailAddress") or {}).get("address")) not in ("", ORG)]

def test_b1a_firmware_not_ext_shared():
    assert channels()[C_FIRM].get("is_ext_shared") is False

def test_b1b_orbital_guest_removed():
    u = users()
    assert UG_ORB not in u
    assert UG_ORB not in (channels().get(C_FIRM, {}).get("members") or [])

def test_b2_kestrel_guest_removed():
    u = users()
    assert UG_KES not in u
    assert UG_KES not in (channels().get(C_HWRD, {}).get("members") or [])

def test_b3_pollhive_restricted():
    assert A_POLL not in approved_app_ids()
    assert A_POLL in restricted_app_ids()

def test_b4a_meeting_no_external_cohost():
    assert _no_ext_cohost(meeting(M_FSEC))

def test_b4b_meeting_auth_required():
    assert (meeting(M_FSEC).get("settings") or {}).get("meeting_authentication") is True

def test_b5a_teams_guest_removed():
    assert not any(m.get("id") == MEM_G for m in team_members(T_ENG))

def test_b5b_teams_shared_channel_gone():
    shared = [c for c in team_channels(T_ENG) if c.get("membershipType") == "shared"]
    assert shared == []

def test_b6_outlook_external_attendee_gone():
    e = me_events().get(EV_RR, {})
    assert e.get("isCancelled") is True or not _event_ext_attendees(e)

def test_b7a_supplyops_not_ext_shared():
    assert channels()[C_SUPO].get("is_ext_shared") is False

def test_b7b_meridian_guest_removed():
    u = users()
    assert UG_MER not in u
    assert UG_MER not in (channels().get(C_SUPO, {}).get("members") or [])

def test_w1a_supplychain_still_untouched():
    assert channels()[C_SUPC].get("is_ext_shared") is False

def test_w1b_old_guest_still_absent():
    assert UG_OLD not in users()

def test_l1a_consortium_channel_preserved():
    assert channels()[C_BEAC].get("is_ext_shared") is True

def test_l1b_consortium_guest_preserved():
    u = users()
    assert UG_NWD in u
    assert UG_NWD in (channels().get(C_BEAC, {}).get("members") or [])

def test_l2_summit_webinar_preserved():
    w = GET("zoom", f"/webinars/{W_SUMMIT}")
    assert str(w.get("id")) == W_SUMMIT

def test_l3_legitbot_still_approved():
    assert A_LEGIT in approved_app_ids()

def test_g_es1_ext_shared_set_exact():
    ext = {cid for cid, c in channels().items() if c.get("is_ext_shared")}
    assert ext == {C_BEAC, C_PART}

def test_g_es2_approved_apps_set_exact():
    assert approved_app_ids() == {A_LEGIT}

def test_g_es3_no_external_cohost_anywhere():
    assert all(_no_ext_cohost(m) for m in all_meetings().values())

def test_g_es4_teams_external_members_only_legit():
    ext = set()
    for t in graph_all("teams", "/v1.0/teams"):
        for m in team_members(t["id"]):
            if email_domain(m.get("email")) not in ("", ORG):
                ext.add(m.get("id"))
    assert ext == {MEM_LEG}

def test_g_es5_outlook_external_attendee_only_legit():
    flagged = {eid for eid, e in me_events().items()
               if _event_ext_attendees(e) and not e.get("isCancelled")}
    assert flagged == {EV_CON}

def test_g_sn_ticket_present():
    r = GET("snow", "/api/now/table/u_security_exception", {"sysparm_query": "number=SEC0001001"})
    assert len(r.get("result", [])) == 1

def test_g_nz_internal_users_preserved():
    u = users()
    for internal in ("UOKAFOR", "UADMIN", "UREYES"):
        assert internal in u
