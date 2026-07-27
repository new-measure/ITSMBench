#!/usr/bin/env python3

import json
import os
import re
import sys
import urllib.request
import urllib.error

TRIGGER = "SEC-4471"
LEAK_DAY = "2026-06-15"

WRITES = []

def _host_for(slug):
    return f"{slug}.local.mock"

def http(slug, method, path, body=None, form=False, query=None):
    host = _host_for(slug)
    override = os.environ.get("MOCK_HOST_OVERRIDE")
    netloc = override or f"{host}:8080"
    url = f"http://{netloc}{path}"
    if query:
        from urllib.parse import urlencode
        url += ("&" if "?" in url else "?") + urlencode(query)
    data = None
    headers = {"Host": host, "Accept": "application/json"}
    if body is not None:
        if form:
            from urllib.parse import urlencode
            data = urlencode(body).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
            try:
                return r.status, json.loads(raw) if raw else None
            except json.JSONDecodeError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return e.code, raw

def die(msg):
    print(f"ORACLE ABORT: {msg}", file=sys.stderr)
    sys.exit(2)

def as_list(payload, *keys):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in keys:
            if isinstance(payload.get(k), list):
                return payload[k]
    return []

def get_org():
    _, orgs = http("github", "GET", "/organizations")
    lst = as_list(orgs)
    if not lst:
        die("no github organization discoverable")
    return lst[0].get("login")

def list_repos(org):
    _, repos = http("github", "GET", f"/orgs/{org}/repos", query={"per_page": "100"})
    return as_list(repos)

def list_secrets(org, repo):
    _, sec = http("github", "GET", f"/repos/{org}/{repo}/actions/secrets", query={"per_page": "100"})
    return as_list(sec, "secrets")

def list_alerts(org, repo):
    _, al = http("github", "GET", f"/repos/{org}/{repo}/secret-scanning/alerts", query={"per_page": "100"})
    return as_list(al)

def list_passwords():
    _, pw = http("device42", "GET", "/api/1.0/passwords/", query={"limit": "1000"})
    return as_list(pw, "Passwords")

def list_okta_apps():
    _, apps = http("okta", "GET", "/api/v1/apps", query={"limit": "200"})
    return as_list(apps)

def list_okta_tokens():
    _, toks = http("okta", "GET", "/api/v1/api-tokens", query={"limit": "200"})
    return as_list(toks)

def list_jsm_requests():
    _, r = http("jira-service-management", "GET", "/rest/servicedeskapi/request", query={"limit": "100"})
    return as_list(r, "values")

def list_conf_pages():
    _, p = http("confluence", "GET", "/wiki/api/v2/pages", query={"body-format": "storage", "limit": "100"})
    return as_list(p, "results")

def field(req, fid):
    for fv in req.get("requestFieldValues", []) or []:
        if fv.get("fieldId") == fid:
            return fv.get("value", "")
    return ""

def before_leak(ts):
    return (str(ts)[:10] < LEAK_DAY) if ts else True

def main():
    st, trig = http("jira-service-management", "GET", f"/rest/servicedeskapi/request/{TRIGGER}")
    if st != 200 or not trig:
        die(f"trigger ticket {TRIGGER} not readable")
    _ = field(trig, "description")

    reqs = list_jsm_requests()
    cohort_names = set()
    for r in reqs:
        summ = str(field(r, "summary"))
        desc = str(field(r, "description"))
        created = (r.get("createdDate") or {}).get("iso8601", "")
        blob = f"{summ} {desc}"
        is_incident = created[:7] == LEAK_DAY[:7] and re.search(
            r"rotate|revoke|exposure|deactivate|credential|key|token|OIDC|app", blob, re.I)
        if not is_incident:
            continue
        for tok in re.findall(r"[A-Z][A-Z0-9_]{3,}", blob):
            cohort_names.add(tok)
        for m in re.findall(r"deploy-bot|internal-admin|payments|datadog|redis|billing", blob, re.I):
            cohort_names.add(m.lower())
    cohort_names.discard("SEC")

    org = get_org()
    repos = list_repos(org)

    secret_index = {}
    for repo in repos:
        rn = repo.get("name")
        for s in list_secrets(org, rn):
            secret_index.setdefault(s.get("name"), (rn, s.get("updated_at")))

    alerts = []
    for repo in repos:
        for a in list_alerts(org, repo.get("name")):
            a["_repo"] = repo.get("name")
            alerts.append(a)
    for a in alerts:
        if str(a.get("state")) == "open":
            cohort_names.add(str(a.get("secret_type", "")).lower())
            cohort_names.add(a.get("_repo"))

    passwords = {p.get("label"): p for p in list_passwords()}
    apps = list_okta_apps()
    tokens = list_okta_tokens()

    for label, p in passwords.items():
        name_hits = label in cohort_names or label in secret_index
        if not name_hits:
            continue
        if before_leak(p.get("last_updated")):
            http("device42", "POST", "/api/1.0/passwords/", form=True,
                 body={"label": label, "password": f"rot-{label}-20260721",
                       "username": p.get("username", "svc")})
            WRITES.append(f"device42 rotate vault password {label}")

    for name, (repo, updated) in secret_index.items():
        in_cohort = name in cohort_names or name in passwords
        if not in_cohort:
            continue
        if before_leak(updated):
            http("github", "PUT", f"/repos/{org}/{repo}/actions/secrets/{name}",
                 body={"encrypted_value": "cm90YXRlZA==", "key_id": "012345678912345678"})
            WRITES.append(f"github rotate actions secret {repo}/{name}")

    for t in tokens:
        tname = str(t.get("name", ""))
        handle = tname.lower().replace("-ci", "").replace("_", "-")
        if any(h and (h in tname.lower() or tname.lower() in h or h in handle)
               for h in cohort_names if isinstance(h, str) and len(h) >= 4 and "-" in h or h in ("deploybot",)):
            http("okta", "DELETE", f"/api/v1/api-tokens/{t.get('id')}")
            WRITES.append(f"okta revoke api-token {tname}")

    by_base = {}
    for a in apps:
        base = re.sub(r"\s*\(legacy\)\s*$", "", str(a.get("label", ""))).strip()
        by_base.setdefault(base, []).append(a)
    for base, group in by_base.items():
        has_current = any("(legacy)" not in str(a.get("label", "")) and a.get("status") == "ACTIVE"
                          for a in group)
        for a in group:
            if "(legacy)" in str(a.get("label", "")) and a.get("status") == "ACTIVE" and has_current:
                http("okta", "POST", f"/api/v1/apps/{a.get('id')}/lifecycle/deactivate")
                WRITES.append(f"okta deactivate legacy app {a.get('label')}")

    pages = list_conf_pages()
    leaked_substrings = []
    for a in alerts:
        if str(a.get("state")) == "open":
            stype = str(a.get("secret_type", "")).lower()
            for pg in pages:
                val = ((pg.get("body") or {}).get("storage") or {}).get("value", "")
                if stype and stype.split("_")[0] in val.lower():
                    for m in re.findall(r"://[^:@/\s]+:([^@\s]+)@", val):
                        leaked_substrings.append((pg, m))
    for pg, secret in leaked_substrings:
        val = ((pg.get("body") or {}).get("storage") or {}).get("value", "")
        new_val = val.replace(secret, "REDACTED")
        ver = ((pg.get("version") or {}).get("number") or 1) + 1
        http("confluence", "PUT", f"/wiki/api/v2/pages/{pg.get('id')}",
             body={"id": str(pg.get("id")), "status": "current",
                   "title": pg.get("title"), "spaceId": pg.get("spaceId"),
                   "body": {"representation": "storage", "value": new_val},
                   "version": {"number": ver}})
        WRITES.append(f"confluence redact page {pg.get('title')}")

    for a in alerts:
        if str(a.get("state")) == "open":
            http("github", "PATCH",
                 f"/repos/{org}/{a['_repo']}/secret-scanning/alerts/{a.get('number')}",
                 body={"state": "resolved", "resolution": "revoked",
                       "resolution_comment": "Rotated / remediated per incident SEC-4471."})
            WRITES.append(f"github resolve alert #{a.get('number')} ({a['_repo']})")

    print("=== ORACLE WRITE LIST ===")
    for w in WRITES:
        print("  -", w)
    print(f"=== {len(WRITES)} writes ===")

    verify(org, repos)

def verify(org, repos):
    problems = []
    p = {x.get("label"): x for x in list_passwords()}
    if p.get("REDIS_AUTH", {}).get("last_updated", "")[:10] != "2026-07-21":
        problems.append("C1 REDIS_AUTH vault not rotated this episode")
    dd = None
    for repo in repos:
        for s in list_secrets(org, repo.get("name")):
            if s.get("name") == "DATADOG_API_KEY":
                dd = s
    if not dd or dd.get("updated_at", "")[:10] != "2026-07-21":
        problems.append("C2 DATADOG secret not rotated this episode")
    if any(t.get("name") == "deploy-bot-ci" for t in list_okta_tokens()):
        problems.append("C3 deploy-bot-ci token still present")
    for pg in list_conf_pages():
        val = ((pg.get("body") or {}).get("storage") or {}).get("value", "")
        if "Sn0wLeak" in val:
            problems.append("C4a snowflake plaintext still in runbook")
    apps = {a.get("label"): a for a in list_okta_apps()}
    la = apps.get("internal-admin-oidc (legacy)")
    if la and la.get("status") == "ACTIVE":
        problems.append("C5 legacy internal app still ACTIVE")
    na = apps.get("internal-admin-oidc")
    if not na or na.get("status") != "ACTIVE":
        problems.append("C5 current internal app not ACTIVE")
    for repo in repos:
        for a in list_alerts(org, repo.get("name")):
            if a.get("state") == "open":
                problems.append(f"open alert remains #{a.get('number')} ({repo.get('name')})")
    if problems:
        for pr in problems:
            print("READBACK MISMATCH:", pr, file=sys.stderr)
        sys.exit(3)
    print("=== READBACK OK: end-state verified ===")

if __name__ == "__main__":
    main()
