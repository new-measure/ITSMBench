#!/usr/bin/env python3

import json
import sys
import urllib.request
import urllib.error

TRIGGER_ID = "INC0011207"

GW = "http://google-workspace.local.mock:8080"
M365 = "http://microsoft-365.local.mock:8080/v1.0"
SNOW = "http://servicenow.local.mock:8080"
SLACK = "http://slack-admin.local.mock:8080/api"
ZOOM = "http://zoom-admin.local.mock:8080"

WRITES = []

def _req(method, url, body=None):
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            payload = json.loads(raw) if raw.strip() else {}
        except Exception:
            payload = {"raw": raw}
        return e.code, payload

def GET(url):
    return _req("GET", url)

def die(msg):
    print("ORACLE-FAIL:", msg)
    sys.exit(1)

def gw_list(path, envelope):
    out = []
    token = None
    while True:
        u = f"{GW}{path}"
        u += ("&" if "?" in u else "?") + "maxResults=500"
        if token:
            u += f"&pageToken={token}"
        st, body = GET(u)
        if st != 200:
            die(f"GW list {path} -> {st} {body}")
        out.extend(body.get(envelope, []) or [])
        token = body.get("nextPageToken")
        if not token:
            return out

def m365_list(path):
    out = []
    u = f"{M365}{path}"
    u += ("&" if "?" in u else "?") + "$top=200"
    while True:
        st, body = GET(u)
        if st != 200:
            die(f"M365 list {u} -> {st} {body}")
        out.extend(body.get("value", []) or [])
        nxt = body.get("@odata.nextLink")
        if not nxt:
            return out
        u = nxt

def zoom_list(path, envelope):
    out = []
    page = 1
    while True:
        u = f"{ZOOM}{path}"
        u += ("&" if "?" in u else "?") + f"page_size=300&page_number={page}"
        st, body = GET(u)
        if st != 200:
            die(f"Zoom list {u} -> {st} {body}")
        rows = body.get(envelope, []) or []
        out.extend(rows)
        if len(rows) < 300:
            return out
        page += 1

def slack_list(method, envelope):
    out = []
    cursor = ""
    while True:
        u = f"{SLACK}/{method}?limit=200"
        if cursor:
            u += f"&cursor={cursor}"
        st, body = GET(u)
        if st != 200 or not body.get("ok", False):
            die(f"Slack {method} -> {st} {body}")
        out.extend(body.get(envelope, []) or [])
        cursor = (body.get("response_metadata") or {}).get("next_cursor") or ""
        if not cursor:
            return out

def snow_list(table, query=None):
    out = []
    offset = 0
    while True:
        u = f"{SNOW}/api/now/table/{table}?sysparm_limit=200&sysparm_offset={offset}"
        if query:
            u += f"&sysparm_query={urllib.parse.quote(query)}"
        st, body = GET(u)
        if st != 200:
            die(f"SNOW list {table} -> {st} {body}")
        rows = body.get("result", []) or []
        out.extend(rows)
        if len(rows) < 200:
            return out
        offset += 200

import urllib.parse

def email_of_m365(u):
    return str(u.get("userPrincipalName") or u.get("mail") or "").lower()

def main():
    st, body = GET(f"{SNOW}/api/now/table/incident?sysparm_query=number={TRIGGER_ID}")
    if st != 200 or not (body.get("result")):
        die(f"trigger {TRIGGER_ID} not found: {st} {body}")
    print(f"[trigger] {TRIGGER_ID} present.")

    m365_users = m365_list("/users")
    gw_users = gw_list("/admin/directory/v1/users", "users")
    print(f"[enum] M365 users={len(m365_users)} GW users={len(gw_users)}")

    gone_emails = set()
    m365_gone = []
    for u in m365_users:
        if u.get("accountEnabled") is False:
            e = email_of_m365(u)
            if e:
                gone_emails.add(e)
            m365_gone.append((u, e))
    gw_gone_emails = set()
    for u in gw_users:
        if u.get("suspended") is True:
            e = str(u.get("primaryEmail") or "").lower()
            if e:
                gone_emails.add(e)
                gw_gone_emails.add(e)

    divested_aliases = set(gone_emails)
    for u in snow_list("sys_user"):
        if u.get("department") == "Meridian" and str(u.get("active")).lower() == "false":
            for k in ("email", "user_name", "u_legacy_email"):
                v = str(u.get(k) or "").lower()
                if v:
                    divested_aliases.add(v)
    print(f"[gone] {len(gone_emails)} directory-gone; {len(divested_aliases)} divested aliases")

    plan = []

    for u, e in m365_gone:
        lics = u.get("assignedLicenses") or []
        skus = [l.get("skuId") for l in lics if l.get("skuId")]
        if skus:
            uid = u["id"]
            def do_m365(uid=uid, skus=skus, e=e):
                st, _ = _req("POST", f"{M365}/users/{uid}/assignLicense",
                             {"addLicenses": [], "removeLicenses": skus})
                if st != 200:
                    die(f"M365 removeLicenses {e} -> {st}")
            plan.append((f"M365 remove {len(skus)} license(s) from {e} [{','.join(skus)}]", do_m365))

    assignments = []
    seen_products = set()
    def load_assignments():
        found = []
        products = list(seen_products)
        for pid in products:
            found.extend(gw_list(f"/apps/licensing/v1/product/{pid}/users", "items"))
        return found

    for pid_guess in ["Google-Apps"]:
        seen_products.add(pid_guess)
    assignments = load_assignments()
    more = {a.get("productId") for a in assignments if a.get("productId")} - seen_products
    if more:
        seen_products |= more
        assignments = load_assignments()
    gw_email_suspended = gw_gone_emails
    for a in assignments:
        uid = str(a.get("userId") or "").lower()
        if uid in divested_aliases:
            pid, sid = a.get("productId"), a.get("skuId")
            real_uid = a.get("userId")
            def do_gw(pid=pid, sid=sid, real_uid=real_uid, uid=uid):
                st, _ = _req("DELETE", f"{GW}/apps/licensing/v1/product/{pid}/sku/{sid}/user/{real_uid}")
                if st != 200:
                    die(f"GW delete assignment {uid} -> {st}")
            plan.append((f"GW delete license assignment {uid} ({pid}/{sid})", do_gw))

    zoom_users = zoom_list("/users", "users")
    for u in zoom_users:
        if u.get("type") == 2 and str(u.get("email") or "").lower() in divested_aliases:
            zid, e = u["id"], str(u.get("email")).lower()
            def do_zoom(zid=zid, e=e):
                st, _ = _req("PATCH", f"{ZOOM}/users/{zid}", {"type": 1})
                if st not in (200, 204):
                    die(f"Zoom downgrade {e} -> {st}")
            plan.append((f"Zoom downgrade {e} type 2->1", do_zoom))

    slack_users = slack_list("admin.users.list", "users")
    for u in slack_users:
        if u.get("deleted"):
            continue
        if u.get("is_restricted") or u.get("is_ultra_restricted"):
            continue
        e = str(u.get("email") or "").lower()
        if e in divested_aliases:
            uid = u.get("id") or u.get("user_id")
            teams = list(u.get("team_ids") or [])
            def do_slack(uid=uid, teams=teams, e=e):
                for tid in (teams or [None]):
                    st, body = _req("POST", f"{SLACK}/admin.users.remove",
                                    {"user_id": uid, "team_id": tid})
                    if st != 200 or not body.get("ok", False):
                        die(f"Slack remove {e} (team {tid}) -> {st} {body}")
            plan.append((f"Slack remove {e} from {len(teams) or 1} team(s)", do_slack))

    print(f"\n[plan] {len(plan)} write(s):")
    for desc, _ in plan:
        print("   -", desc)
    print()
    for desc, fn in plan:
        fn()
        WRITES.append(desc)
        print("[write]", desc)

    verify(m365_gone, gw_email_suspended, seen_products, divested_aliases)
    print(f"\nOK: {len(WRITES)} writes applied and verified.")

def verify(m365_gone, gw_email_suspended, products, divested_aliases):
    for u, e in m365_gone:
        st, body = GET(f"{M365}/users/{u['id']}")
        if st == 200 and (body.get("assignedLicenses") or []):
            die(f"verify M365 {e} still holds licenses: {body.get('assignedLicenses')}")
    for pid in products:
        for a in gw_list(f"/apps/licensing/v1/product/{pid}/users", "items"):
            if str(a.get("userId") or "").lower() in divested_aliases:
                die(f"verify GW assignment still present for {a.get('userId')}")
    for u in zoom_list("/users", "users"):
        if str(u.get("email") or "").lower() in divested_aliases and u.get("type") == 2:
            die(f"verify Zoom {u.get('email')} still type 2")
    for u in slack_list("admin.users.list", "users"):
        e = str(u.get("email") or "").lower()
        if e in divested_aliases and not u.get("deleted") and not (
            u.get("is_restricted") or u.get("is_ultra_restricted")
        ):
            die(f"verify Slack {e} still billable")
    print("[verify] all reclaim surfaces clean.")

if __name__ == "__main__":
    main()
