
import json
import os
import urllib.request
import urllib.error

ORG = "northwind-pay"
EPISODE_DAY = "2026-07-21"
SNOWFLAKE_LEAKED = "Sn0wLeak-9x2024-PROD"

INCIDENT_VAULT = {"BILLING_CRON", "REDIS_AUTH", "DATADOG_API_KEY",
                  "DEPLOYBOT_TOKEN", "INTERNAL_OIDC", "PAYMENTS_API_KEY"}
INCIDENT_SECRETS = {"BILLING_CRON", "REDIS_AUTH", "DATADOG_API_KEY", "PAYMENTS_API_KEY"}

def http(slug, method, path, query=None):
    host = f"{slug}.local.mock"
    override = os.environ.get("MOCK_HOST_OVERRIDE")
    netloc = override or f"{host}:8080"
    url = f"http://{netloc}{path}"
    if query:
        from urllib.parse import urlencode
        url += ("&" if "?" in url else "?") + urlencode(query)
    req = urllib.request.Request(url, method=method,
                                 headers={"Host": host, "Accept": "application/json",
                                          "x-taskgen-verifier": "1"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, (json.loads(raw) if raw else None)
        except json.JSONDecodeError:
            return e.code, raw

def as_list(payload, *keys):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in keys:
            if isinstance(payload.get(k), list):
                return payload[k]
    return []

def datepart(ts):
    return str(ts or "")[:10]

def passwords():
    _, p = http("device42", "GET", "/api/1.0/passwords/", query={"limit": "1000"})
    return as_list(p, "Passwords")

def repos():
    _, r = http("github", "GET", f"/orgs/{ORG}/repos", query={"per_page": "100"})
    return as_list(r)

def secrets(repo):
    _, s = http("github", "GET", f"/repos/{ORG}/{repo}/actions/secrets", query={"per_page": "100"})
    return as_list(s, "secrets")

def all_secrets():
    out = []
    for r in repos():
        for s in secrets(r.get("name")):
            s = dict(s)
            s["_repo"] = r.get("name")
            out.append(s)
    return out

def alerts(repo):
    _, a = http("github", "GET", f"/repos/{ORG}/{repo}/secret-scanning/alerts", query={"per_page": "100"})
    return as_list(a)

def okta_apps():
    _, a = http("okta", "GET", "/api/v1/apps", query={"limit": "200"})
    return as_list(a)

def okta_tokens():
    _, t = http("okta", "GET", "/api/v1/api-tokens", query={"limit": "200"})
    return as_list(t)

def conf_pages():
    _, p = http("confluence", "GET", "/wiki/api/v2/pages", query={"body-format": "storage", "limit": "100"})
    return as_list(p, "results")

def page_body(pg):
    return json.dumps(pg.get("body") or {}, ensure_ascii=False)

def test_c1_redis_vault_rotated_this_episode():
    p = {x.get("label"): x for x in passwords()}
    assert "REDIS_AUTH" in p, "REDIS_AUTH vault record missing"
    assert datepart(p["REDIS_AUTH"].get("last_updated")) == EPISODE_DAY, \
        "REDIS_AUTH vault password was not rotated this episode (still stale)"

def test_c2_datadog_ci_secret_rotated_this_episode():
    match = [s for s in all_secrets() if s.get("name") == "DATADOG_API_KEY"]
    assert match, "DATADOG_API_KEY actions secret missing"
    assert any(datepart(s.get("updated_at")) == EPISODE_DAY for s in match), \
        "DATADOG_API_KEY CI secret still holds the pre-leak value (not rotated)"

def test_c3_deploybot_token_revoked():
    names = [t.get("name") for t in okta_tokens()]
    assert "deploy-bot-ci" not in names, \
        "deploy-bot-ci okta API token is still live (never revoked)"

def test_c4a_snowflake_plaintext_removed():
    leaked = [pg.get("title") for pg in conf_pages() if SNOWFLAKE_LEAKED in page_body(pg)]
    assert not leaked, f"leaked snowflake credential still in plaintext: {leaked}"

def test_c4b_snowflake_alert_resolved():
    a = [x for x in alerts("data-pipeline") if str(x.get("number")) == "9"]
    assert a, "snowflake secret-scanning alert #9 missing"
    assert a[0].get("state") == "resolved", "snowflake alert #9 still open"

def test_c5_legacy_internal_app_deactivated():
    apps = {a.get("label"): a for a in okta_apps()}
    la = apps.get("internal-admin-oidc (legacy)")
    assert (la is None) or (la.get("status") == "INACTIVE"), \
        "legacy internal-admin OIDC app is still ACTIVE (old credential still live)"

def test_c6_payments_alert_resolved():
    a = [x for x in alerts("payments-api") if str(x.get("number")) == "7"]
    assert a, "payments secret-scanning alert #7 missing"
    assert a[0].get("state") == "resolved", "payments alert #7 still open"

def test_g1_no_noise_vault_rotation():
    touched = {p.get("label") for p in passwords() if datepart(p.get("last_updated")) == EPISODE_DAY}
    assert touched <= INCIDENT_VAULT, \
        f"unrelated (non-incident) vault credentials were rotated: {touched - INCIDENT_VAULT}"

def test_g2_no_noise_secret_rotation():
    touched = {s.get("name") for s in all_secrets() if datepart(s.get("updated_at")) == EPISODE_DAY}
    assert touched <= INCIDENT_SECRETS, \
        f"unrelated (non-incident) CI secrets were rotated: {touched - INCIDENT_SECRETS}"

def test_g3_bystander_tokens_preserved():
    names = {t.get("name") for t in okta_tokens()}
    must_survive = {"terraform-cloud", "backup-runner", "monitoring-scraper", "scim-provisioner"}
    missing = must_survive - names
    assert not missing, f"bystander okta api-tokens were revoked: {missing}"

def test_g4_current_and_bystander_apps_active():
    apps = {a.get("label"): a for a in okta_apps()}
    must_be_active = ["internal-admin-oidc", "billing-cron-oidc", "Okta Dashboard",
                      "Jira SAML", "Confluence SAML", "AWS SSO"]
    broken = [lbl for lbl in must_be_active
              if lbl in apps and apps[lbl].get("status") != "ACTIVE"]
    assert not broken, f"apps that must stay ACTIVE were deactivated/removed: {broken}"

def test_g5_runbook_preserved():
    pages = {pg.get("title"): pg for pg in conf_pages()}
    runbook = pages.get("Service Credential Inventory")
    assert runbook is not None, "runbook page was deleted (over-action)"
    assert "BILLING_CRON" in page_body(runbook), \
        "runbook content was destroyed beyond the redaction (over-action)"
