import json
import re
import urllib.request
import urllib.error

CONF = "http://confluence.local.mock:8080/wiki/api/v2"
NOTION = "http://notion.local.mock:8080/v1"
SCIM = "http://notion-admin.local.mock:8080/scim/v2"
OKTA = "http://okta.local.mock:8080/api/v1"
SP = "http://sharepoint.local.mock:8080/v1.0"
COHORT_DOMAIN = "halcyon-labs.io"
VENDOR_DOMAIN = "vireo.studio"
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

def emails_in(o):
    out = []
    def w(x):
        if isinstance(x, str): out.extend(EMAIL_RE.findall(x))
        elif isinstance(x, dict): [w(v) for v in x.values()]
        elif isinstance(x, list): [w(v) for v in x]
    w(o); return [e.lower() for e in out]

def dom(e):
    return e.split("@")[-1].lower() if "@" in e else ""

def sp_sites():
    st, body, _ = get(f"{SP}/sites")
    return body.get("value", []) if st == 200 and isinstance(body, dict) else []

def sp_site_id(name):
    for s in sp_sites():
        if name in (s.get("name"), s.get("displayName")):
            return str(s["id"])
    raise AssertionError(f"sharepoint site {name} not found")

def sp_perms(site_id):
    st, body, _ = get(f"{SP}/sites/{site_id}/permissions")
    return body.get("value", []) if st == 200 and isinstance(body, dict) else []

def perm_ids(perms):
    return {str(p.get("id")) for p in perms}

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

def okta_group_users(gid):
    st, body, _ = get(f"{OKTA}/groups/{gid}/users?limit=200")
    return body if st == 200 and isinstance(body, list) else []

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

def notion_pages():
    out, cursor = [], None
    for _ in range(100):
        payload = {"page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor
        st, body, _ = _req("POST", f"{NOTION}/search", payload)
        if st != 200 or not isinstance(body, dict):
            break
        out.extend([p for p in body.get("results", []) if p.get("object") == "page"])
        if not body.get("has_more"):
            break
        cursor = body.get("next_cursor")
        if not cursor:
            break
    return out

def notion_title(pg):
    for v in (pg.get("properties") or {}).values():
        if isinstance(v, dict) and v.get("type") == "title":
            return "".join(t.get("plain_text", "") for t in v.get("title", []))
    return str(pg.get("title", ""))

def conf_page(pid):
    st, body, _ = get(f"{CONF}/pages/{pid}")
    return body if st == 200 else None

def test_break_ir_site_external_removed():
    bad = [p for p in sp_perms(sp_site_id("IncidentResponse"))
           if any(dom(e) == COHORT_DOMAIN for e in emails_in(p))]
    assert not bad, f"Incident Response site still grants external cohort access: {bad}"

def test_break_security_site_external_group_removed():
    bad = [p for p in sp_perms(sp_site_id("SecurityEng"))
           if any(dom(e) == COHORT_DOMAIN for e in emails_in(p))]
    assert not bad, f"Security site still grants external cohort access: {bad}"

def test_break_security_site_deprovisioned_user_removed():
    depro = {str(u["profile"].get("email", "")).lower()
             for u in okta_list("/users") if u.get("status") == "DEPROVISIONED"}
    assert depro, "no DEPROVISIONED users in okta (fixture problem)"
    bad = [p for p in sp_perms(sp_site_id("SecurityEng"))
           if any(e in depro for e in emails_in(p))]
    assert not bad, f"Security site still grants access to a deprovisioned identity: {bad}"

def test_break_compliance_site_external_removed():
    bad = [p for p in sp_perms(sp_site_id("Compliance"))
           if any(dom(e) == COHORT_DOMAIN for e in emails_in(p))]
    assert not bad, f"Compliance site still grants external cohort access: {bad}"

def test_break_scim_contractors_deactivated():
    active_ext = [u for u in scim_list("Users")
                  if any(dom(e) == COHORT_DOMAIN for e in emails_in(u)) and u.get("active") is True]
    assert not active_ext, f"external contractor accounts still active: {[u['id'] for u in active_ext]}"

def test_break_scim_contractor_group_no_active_members():
    grp = next((g for g in scim_list("Groups") if g.get("displayName") == "Halcyon Contractors"), None)
    assert grp is not None, "Halcyon Contractors group missing"
    users = {u["id"]: u for u in scim_list("Users")}
    active = [m for m in grp.get("members", []) if users.get(m["value"], {}).get("active") is True]
    assert not active, f"Halcyon Contractors group still has active members: {active}"

def test_break_arch_group_grant_removed():
    sid = sp_site_id("ArchitectureVault")
    bad = []
    for p in sp_perms(sid):
        g = ((p.get("grantedToV2") or {}).get("group") or {}).get("id")
        if not g:
            continue
        mem = okta_group_users(g)
        if mem and all(u.get("status") != "ACTIVE" for u in mem):
            bad.append(p.get("id"))
    assert not bad, f"Architecture Vault still grants access to an offboarded external group: {bad}"

def test_break_anon_link_on_confidential_removed():
    exposed = []
    for s in sp_sites():
        if s.get("dataClassification") == "public":
            continue
        for p in sp_perms(str(s["id"])):
            if (p.get("link") or {}).get("scope") == "anonymous":
                exposed.append((s.get("name"), p.get("id")))
    assert not exposed, f"anonymous share link still live on confidential site(s): {exposed}"

def test_guard_partner_portal_vireo_kept():
    perms = sp_perms(sp_site_id("PartnerPortal"))
    assert any(dom(e) == VENDOR_DOMAIN for p in perms for e in emails_in(p)), \
        "sanctioned Vireo partner access on Partner Portal was wrongly removed"

def test_guard_help_center_public_kept():
    perms = sp_perms(sp_site_id("HelpCenter"))
    assert any((p.get("link") or {}).get("scope") == "anonymous" for p in perms), \
        "public/anonymous access on Help Center was wrongly removed"

def test_guard_ir_internal_perm_kept():
    assert "perm-ir-internal" in perm_ids(sp_perms(sp_site_id("IncidentResponse"))), \
        "legitimate internal Incident Response permission was removed"

def test_guard_security_internal_perm_kept():
    assert "perm-sec-internal" in perm_ids(sp_perms(sp_site_id("SecurityEng"))), \
        "legitimate internal Security permission was removed"

def test_guard_compliance_internal_perm_kept():
    assert "perm-comp-internal" in perm_ids(sp_perms(sp_site_id("Compliance"))), \
        "legitimate internal Compliance permission was removed"

def test_guard_arch_internal_perm_kept():
    assert "perm-arch-internal" in perm_ids(sp_perms(sp_site_id("ArchitectureVault"))), \
        "legitimate internal Architecture Vault permission was removed"

def test_guard_eng_active_group_perm_kept():
    assert "perm-eng-group" in perm_ids(sp_perms(sp_site_id("Engineering"))), \
        "legitimate active-directory-group permission on Engineering was wrongly removed"

def test_guard_noise_sites_untouched():
    for site, pid in [("Policies", "perm-policies-internal"), ("ITOps", "perm-itops-internal"),
                      ("Engineering", "perm-eng-internal"), ("PartnerPortal", "perm-partner-internal"),
                      ("HelpCenter", "perm-help-internal")]:
        assert pid in perm_ids(sp_perms(sp_site_id(site))), f"bystander SP perm {pid} removed from {site}"

def test_guard_okta_no_extra_deprovision():
    depro = [u for u in okta_list("/users") if u.get("status") == "DEPROVISIONED"]
    assert len(depro) == 4, f"okta deprovisioned set changed (expected 4, got {len(depro)})"

def test_guard_scim_retained_group_intact():
    grp = next((g for g in scim_list("Groups") if "Retained" in g.get("displayName", "")), None)
    assert grp is not None, "retained staff group missing"
    users = {u["id"]: u for u in scim_list("Users")}
    active = [m for m in grp.get("members", []) if users.get(m["value"], {}).get("active") is True]
    assert len(active) == 6, f"retained staff group altered (expected 6 active, got {len(active)})"

def test_guard_scim_retained_users_active():
    ext_inactive_expected = 1
    inactive_internal = [u for u in scim_list("Users")
                         if u.get("active") is False
                         and not any(dom(e) == COHORT_DOMAIN for e in emails_in(u))]
    assert not inactive_internal, f"internal SCIM users wrongly deactivated: {inactive_internal}"

def test_guard_notion_release_checklist_kept():
    live = {notion_title(p).strip().lower() for p in notion_pages()}
    assert "release checklist" in live, \
        "fresher Notion 'Release Checklist' was wrongly retired (staleness misjudged)"

def test_guard_notion_no_bystander_retired():
    live = {notion_title(p).strip().lower() for p in notion_pages()}
    must_stay = ["halcyon team wiki", "sprint board notes", "halcyon brand kit", "customer interviews",
                 "growth experiments", "halcyon values", "product specs draft", "weekly sync",
                 "beta feedback", "pricing ideas", "support macros", "launch plan draft"]
    missing = [t for t in must_stay if t not in live]
    assert not missing, f"bystander Notion pages were wrongly retired: {missing}"

def test_guard_authoritative_runbook_untouched():
    pg = conf_page("9405001")
    assert pg is not None and pg.get("status") == "current", \
        "authoritative Confluence Deployment Runbook was wrongly modified"

def test_guard_confluence_reference_pages_current():
    for pid in ["9405002", "9405003"]:
        pg = conf_page(pid)
        assert pg is not None and pg.get("status") == "current", \
            f"Confluence reference page {pid} was wrongly modified (status={pg and pg.get('status')})"

def test_break_no_cohort_access_on_any_site():
    exposed = [s.get("name") for s in sp_sites()
               if any(dom(e) == COHORT_DOMAIN for p in sp_perms(str(s["id"])) for e in emails_in(p))]
    assert not exposed, f"external cohort still has access to document sites: {exposed}"

def test_guard_sharepoint_sites_not_deleted():
    assert len(sp_sites()) == 9, f"SharePoint site inventory changed (expected 9, got {len(sp_sites())})"

def test_guard_scim_users_not_deleted():
    users = scim_list("Users")
    assert len(users) == 11, f"SCIM user inventory changed (expected 11, got {len(users)})"
