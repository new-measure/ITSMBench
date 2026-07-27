#!/usr/bin/env python3
import json
import re
import sys
import urllib.request
import urllib.error

TRIGGER_PAGE_ID = "9400100"
CONF = "http://confluence.local.mock:8080/wiki/api/v2"
NOTION = "http://notion.local.mock:8080/v1"
SCIM = "http://notion-admin.local.mock:8080/scim/v2"
OKTA = "http://okta.local.mock:8080/api/v1"
SP = "http://sharepoint.local.mock:8080/v1.0"
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

def _req(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw.strip() else None), dict(r.headers)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            p = json.loads(raw) if raw.strip() else None
        except Exception:
            p = raw
        return e.code, p, dict(e.headers or {})

def get(url):
    return _req("GET", url)

def die(m):
    print("ORACLE-FAIL:", m)
    sys.exit(2)

def dom(e):
    return str(e).split("@")[-1].lower() if e and "@" in str(e) else ""

def emails_in(o):
    out = []
    def w(x):
        if isinstance(x, str): out.extend(EMAIL_RE.findall(x))
        elif isinstance(x, dict): [w(v) for v in x.values()]
        elif isinstance(x, list): [w(v) for v in x]
    w(o); return [e.lower() for e in out]

def okta_list(path):
    out, url = [], f"{OKTA}{path}?limit=200"
    for _ in range(100):
        st, body, hdrs = get(url)
        if st != 200 or not isinstance(body, list):
            break
        out.extend(body)
        m = re.search(r"<([^>]+)>;\s*rel=\"next\"", hdrs.get("Link", "") or hdrs.get("link", ""))
        if not m:
            break
        url = m.group(1)
    return out

def sp_list(url):
    out = []
    for _ in range(100):
        st, body, _ = get(url)
        if st != 200 or not isinstance(body, dict):
            break
        out.extend(body.get("value", []))
        url = body.get("@odata.nextLink") or body.get("odata.nextLink")
        if not url:
            break
    return out

def scim_list(kind):
    out, start = [], 1
    for _ in range(100):
        st, body, _ = get(f"{SCIM}/{kind}?startIndex={start}&count=100")
        if st != 200 or not isinstance(body, dict):
            break
        res = body.get("Resources", [])
        out.extend(res)
        total = int(body.get("totalResults", len(out)))
        if not res or start + len(res) > total:
            break
        start += len(res)
    return out

def notion_search():
    out, cursor = [], None
    for _ in range(100):
        payload = {"page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor
        st, body, _ = _req("POST", f"{NOTION}/search", payload)
        if st != 200 or not isinstance(body, dict):
            break
        out.extend(body.get("results", []))
        if not body.get("has_more"):
            break
        cursor = body.get("next_cursor")
        if not cursor:
            break
    return out

def conf_list(path):
    out, url = [], f"{CONF}{path}?limit=250"
    for _ in range(100):
        st, body, _ = get(url)
        if st != 200 or not isinstance(body, dict):
            break
        out.extend(body.get("results", []))
        nxt = (body.get("_links") or {}).get("next")
        if not nxt:
            break
        url = "http://confluence.local.mock:8080" + nxt
    return out

def main():
    writes = []

    st, trig, _ = get(f"{CONF}/pages/{TRIGGER_PAGE_ID}")
    if st != 200 or not isinstance(trig, dict):
        die(f"trigger page not found ({st})")
    m = re.search(r"named\s+([A-Za-z0-9]+)", json.dumps(trig))
    if not m:
        die("trigger does not name a flagged site")
    flagged = m.group(1)

    okta_users = okta_list("/users")
    by_email, dom_counts = {}, {}
    for u in okta_users:
        prof = u.get("profile", {})
        for k in ("email", "login"):
            e = str(prof.get(k, "")).lower()
            if e:
                by_email[e] = u
        e = str(prof.get("email", "")).lower()
        if u.get("status") == "ACTIVE" and "@" in e:
            dom_counts[dom(e)] = dom_counts.get(dom(e), 0) + 1
    internal = max(dom_counts, key=dom_counts.get)

    def deprov(e):
        u = by_email.get(str(e).lower())
        return bool(u and u.get("status") == "DEPROVISIONED")

    sites = sp_list(f"{SP}/sites")
    flagged_site = next((s for s in sites
                         if flagged.lower() in (str(s.get("name", "")).lower(),
                                                str(s.get("displayName", "")).lower())
                         or flagged.lower() in str(s.get("webUrl", "")).lower()), None)
    if not flagged_site:
        die(f"flagged site {flagged} not found")
    cohort = None
    for p in sp_list(f"{SP}/sites/{flagged_site['id']}/permissions"):
        for e in emails_in(p):
            if dom(e) and dom(e) != internal:
                cohort = dom(e)
                break
        if cohort:
            break
    if not cohort:
        die("no external principal on the flagged site")

    def okta_group_members(gid):
        st, b, _ = get(f"{OKTA}/groups/{gid}/users?limit=200")
        return b if st == 200 and isinstance(b, list) else []

    site_cls = {str(s["id"]): s.get("dataClassification") for s in sites}

    def perm_residual(perm, site_id):
        ems = emails_in(perm)
        if any(dom(e) == cohort for e in ems):
            return True
        if any(dom(e) == internal and deprov(e) for e in ems):
            return True
        g = ((perm.get("grantedToV2") or {}).get("group") or {}).get("id")
        if g:
            mem = okta_group_members(g)
            if mem and all(m.get("status") != "ACTIVE" for m in mem):
                return True
        if (perm.get("link") or {}).get("scope") == "anonymous" and site_cls.get(site_id) != "public":
            return True
        return False

    sp_removals = []
    for s in sites:
        for p in sp_list(f"{SP}/sites/{s['id']}/permissions"):
            if perm_residual(p, str(s["id"])):
                sp_removals.append((str(s["id"]), str(p["id"])))

    scim_deactivate = [str(u["id"]) for u in scim_list("Users")
                       if u.get("active") is True
                       and any(dom(e) == cohort for e in emails_in(u))]

    for site_id, perm_id in sp_removals:
        st, _, _ = _req("DELETE", f"{SP}/sites/{site_id}/permissions/{perm_id}")
        writes.append(f"sp DELETE perm {perm_id} on {site_id} -> {st}")
    for uid in scim_deactivate:
        st, _, _ = _req("PATCH", f"{SCIM}/Users/{uid}",
                        {"schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                         "Operations": [{"op": "replace", "path": "active", "value": False}]})
        writes.append(f"scim deactivate {uid} -> {st}")

    print("=== WRITE LIST ===")
    [print(" ", w) for w in writes]
    print(f"internal={internal} cohort={cohort} flagged_site={flagged}")

    problems = []
    for site_id, perm_id in sp_removals:
        if any(str(p["id"]) == perm_id for p in sp_list(f"{SP}/sites/{site_id}/permissions")):
            problems.append(f"sp perm {perm_id} still on {site_id}")
    for uid in scim_deactivate:
        st, u, _ = get(f"{SCIM}/Users/{uid}")
        if not (isinstance(u, dict) and u.get("active") is False):
            problems.append(f"scim {uid} not deactivated")
    if problems:
        [print("READBACK-FAIL:", p) for p in problems]
        sys.exit(3)
    if not sp_removals or not scim_deactivate:
        die(f"empty category: sp={len(sp_removals)} scim={len(scim_deactivate)}")
    print("ORACLE-OK")

if __name__ == "__main__":
    main()
