import json
import urllib.request

SLACK = "http://slack.local.mock:8080/api"
NOTION = "http://notion.local.mock:8080/v1"
SCIM = "http://notion-admin.local.mock:8080/scim/v2"
GW = "http://google-workspace.local.mock:8080/admin/directory/v1"
GH = "http://github.local.mock:8080"
ZOHO = "http://zohodesk.local.mock:8080/api/v1"

DEPARTED_EMAILS = {
    "priya.rao@ext.northwind.example", "priya.rao@meridian-design.example", "p.rao@meridian.example",
    "diego.marchetti@blueharbor.example", "sana.kapoor@cedar-analytics.example",
    "theo.vance@meridian-design.example", "lena.fischer@ext.northwind.example",
    "lena.fischer@blueharbor.example", "omar.haddad@aurora-labs.example",
}

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode()
    return json.loads(raw) if raw else None

def _post(url, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                headers={"Accept": "application/json", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode()
    return json.loads(raw) if raw else None

def _as_list(obj, *keys):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in keys + ("results", "members", "value", "data", "items"):
            if k in obj and isinstance(obj[k], list):
                return obj[k]
    return []

def _slack_deleted(uid):
    u = _get(SLACK + "/users.info?user=" + uid)
    return isinstance(u, dict) and bool((u.get("user") or {}).get("deleted"))

def _slack_channel_members(cid):
    return [str(m) for m in _as_list(_get(SLACK + "/conversations.members?channel=" + cid))]

def _gw_user(email):
    return _get(GW + "/users/" + email) or {}

def _gw_gone(email):
    u = _gw_user(email)
    return bool(u.get("suspended")) or bool(u.get("deleted"))

def _gw_group_emails(group):
    out = set()
    for m in _as_list(_get(GW + "/groups/%s/members" % group)):
        for k in ("email", "id"):
            if m.get(k):
                out.add(str(m[k]).lower())
    return out

def _scim_active(uid):
    u = _get(SCIM + "/Users/" + uid) or {}
    return u.get("active")

def _gh_array(path):
    return _as_list(_get(GH + path))

def _notion_prop_text(page, name):
    prop = (page.get("properties") or {}).get(name) or {}
    rich = prop.get("rich_text") or prop.get("title") or []
    return "".join(x.get("plain_text", "") for x in rich).strip()

def _share_emails():
    rows = _as_list(_get_query("ds-shares"))
    return {_notion_prop_text(r, "Email").lower() for r in rows}

def _get_query(ds_id):
    return _post(NOTION + "/data_sources/%s/query" % ds_id, {})

def test_priya_gw_deprovisioned():
    assert _gw_gone("priya.rao@ext.northwind.example")

def test_priya_notion_member_deactivated():
    assert _scim_active("na-priya") is False

def test_priya_slack_primary_deactivated():
    assert _slack_deleted("UPRIYA")

def test_priya_slack_primary_removed_from_atlas():
    assert _slack_deleted("UPRIYA") or "UPRIYA" not in _slack_channel_members("CATLAS")

def test_priya_notion_share_removed():
    assert "priya.rao@meridian-design.example" not in _share_emails()

def test_priya_slack_second_identity_deactivated():
    assert _slack_deleted("UPRIYA2")

def test_priya_slack_second_identity_removed_from_vendor():
    assert _slack_deleted("UPRIYA2") or "UPRIYA2" not in _slack_channel_members("CVENDOR")

def test_diego_notion_member_deactivated():
    assert _scim_active("na-diego") is False

def test_diego_github_collaborator_removed():
    assert not any(str(c.get("login")) == "diego-marchetti" for c in _gh_array("/repos/northwind/atlas-web/collaborators"))

def test_diego_notion_share_removed():
    assert "diego.marchetti@blueharbor.example" not in _share_emails()

def test_blueharbor_teamspace_retains_active_owner():
    rows = _as_list(_get_query("ds-spaces"))
    space = next((r for r in rows if _notion_prop_text(r, "Space") == "Blue Harbor Delivery"), None)
    owner = _notion_prop_text(space, "Owner").lower() if space else ""
    assert space is not None and owner and owner not in DEPARTED_EMAILS

def test_sana_notion_member_deactivated():
    assert _scim_active("na-sana") is False

def test_sana_notion_share_removed():
    assert "sana.kapoor@cedar-analytics.example" not in _share_emails()

def test_theo_slack_deactivated():
    assert _slack_deleted("UTHEO")

def test_theo_slack_removed_from_atlas():
    assert _slack_deleted("UTHEO") or "UTHEO" not in _slack_channel_members("CATLAS")

def test_theo_notion_share_board_deck_removed():
    rows = _as_list(_get_query("ds-shares"))
    assert not any(_notion_prop_text(r, "Email").lower() == "theo.vance@meridian-design.example"
                   and _notion_prop_text(r, "Resource") == "Q3 Board Deck" for r in rows)

def test_theo_notion_share_brand_assets_removed():
    rows = _as_list(_get_query("ds-shares"))
    assert not any(_notion_prop_text(r, "Email").lower() == "theo.vance@meridian-design.example"
                   and _notion_prop_text(r, "Resource") == "Brand Assets DB" for r in rows)

def test_theo_github_deploy_key_removed():
    assert not any(str((k.get("added_by") or {}).get("login")) == "theo-vance"
                   for k in _gh_array("/repos/northwind/atlas-web/keys"))

def test_lena_gw_deprovisioned():
    assert _gw_gone("lena.fischer@ext.northwind.example")

def test_lena_removed_from_helios_group():
    assert "lena.fischer@ext.northwind.example" not in _gw_group_emails("project-helios@northwind.example")

def test_lena_removed_from_finance_group():
    assert "lena.fischer@ext.northwind.example" not in _gw_group_emails("finance-ext@northwind.example")

def test_lena_slack_deactivated():
    assert _slack_deleted("ULENA")

def test_lena_slack_removed_from_helios():
    assert _slack_deleted("ULENA") or "ULENA" not in _slack_channel_members("CHELIOS")

def test_lena_notion_share_removed():
    assert "lena.fischer@ext.northwind.example" not in _share_emails()

def test_omar_github_outside_collaborator_removed():
    assert not any(str(c.get("login")) == "omar-haddad" for c in _gh_array("/orgs/northwind/outside_collaborators"))

def test_omar_github_repo_collaborator_removed():
    assert not any(str(c.get("login")) == "omar-haddad" for c in _gh_array("/repos/northwind/data-pipeline/collaborators"))

def test_omar_notion_member_deactivated():
    assert _scim_active("na-omar") is False

def test_omar_notion_share_removed():
    assert "omar.haddad@aurora-labs.example" not in _share_emails()

def test_ticket_closed():
    t = _get(ZOHO + "/tickets/501") or {}
    assert str(t.get("status", "")).lower() == "closed"
