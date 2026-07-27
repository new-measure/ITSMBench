
import json
import urllib.error
import urllib.parse
import urllib.request

GMAIL = "http://gmail.local.mock:8080"
GW = "http://google-workspace.local.mock:8080"
SN = "http://servicenow.local.mock:8080"
DOMAIN = "larkspurcap.example"
MAILBOX = "cfo@" + DOMAIN
TICKET = "INC0071204"
FULL_SCOPE = "https://mail.google.com/"

DEL_DEPARTED_1 = "priya.raman@" + DOMAIN
DEL_DEPARTED_2 = "marcus.feld@" + DOMAIN
DEL_DEPARTED_3 = "nadia.cho@" + DOMAIN
DEL_DEPARTED_4 = "tomas.vidal@" + DOMAIN
DEL_MOVED = "owen.brooks@" + DOMAIN
DEL_EXTERNAL = "j.harmon@meridian-partners.example"

SA_DEPARTED_1 = "priya.raman@" + DOMAIN
SA_DEPARTED_2 = "marcus.feld@" + DOMAIN
SA_MOVED = "owen.brooks@" + DOMAIN
SA_EXTERNAL = "dana.vore@vore-family-office.example"

FWD_EXT_1 = "d.vore.personal@proton-mail.example"
FWD_EXT_2 = "statements@drivesync-vault.example"

FLT_EXT_1 = "flt-fwd-invoices"
FLT_EXT_2 = "flt-fwd-statements"

TOK_MOVED_BROAD = "lena.frost@" + DOMAIN

def _get(url, allow_404=True):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        if allow_404 and e.code == 404:
            return None
        raise
    return json.loads(raw) if raw else None

def _as_list(obj, *keys):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in keys + ("result", "value", "items", "users"):
            if k in obj and isinstance(obj[k], list):
                return obj[k]
    return []

def _gm(path):
    return GMAIL + "/gmail/v1/users/" + urllib.parse.quote(MAILBOX) + "/settings/" + path

def _delegate_emails():
    return {str(d.get("delegateEmail", "")).lower()
            for d in _as_list(_get(_gm("delegates")), "delegates")}

def _sendas_emails():
    return {str(s.get("sendAsEmail", "")).lower()
            for s in _as_list(_get(_gm("sendAs")), "sendAs")}

def _forwarding_emails():
    return {str(f.get("forwardingEmail", "")).lower()
            for f in _as_list(_get(_gm("forwardingAddresses")), "forwardingAddresses")}

def _filter_ids():
    return {str(f.get("id")) for f in _as_list(_get(_gm("filters")), "filter", "filters")}

def _tokens(user_email):
    return _as_list(_get(GW + "/admin/directory/v1/users/" + urllib.parse.quote(user_email) + "/tokens"),
                    "items")

def _has_full_scope_token(user_email):
    return any(FULL_SCOPE in (t.get("scopes") or []) for t in _tokens(user_email))

def _gw_user(email):
    for u in _as_list(_get(GW + "/admin/directory/v1/users?customer=my_customer"), "users"):
        if str(u.get("primaryEmail", "")).lower() == email.lower():
            return u
    return None

def _sn_ticket():
    rows = _as_list(_get(SN + "/api/now/table/incident?sysparm_query="
                         + urllib.parse.quote("number=%s" % TICKET)))
    return rows[0] if rows else None

def test_delegate_departed_1_removed():
    assert DEL_DEPARTED_1 not in _delegate_emails()

def test_delegate_departed_2_removed():
    assert DEL_DEPARTED_2 not in _delegate_emails()

def test_delegate_departed_3_removed():
    assert DEL_DEPARTED_3 not in _delegate_emails()

def test_delegate_departed_4_removed():
    assert DEL_DEPARTED_4 not in _delegate_emails()

def test_delegate_moved_removed():
    assert DEL_MOVED not in _delegate_emails()

def test_delegate_external_removed():
    assert DEL_EXTERNAL not in _delegate_emails()

def test_sendas_departed_1_removed():
    assert SA_DEPARTED_1 not in _sendas_emails()

def test_sendas_departed_2_removed():
    assert SA_DEPARTED_2 not in _sendas_emails()

def test_sendas_moved_removed():
    assert SA_MOVED not in _sendas_emails()

def test_sendas_external_removed():
    assert SA_EXTERNAL not in _sendas_emails()

def test_external_forwarding_1_removed():
    assert FWD_EXT_1 not in _forwarding_emails()

def test_external_forwarding_2_removed():
    assert FWD_EXT_2 not in _forwarding_emails()

def test_external_forward_filter_1_removed():
    assert FLT_EXT_1 not in _filter_ids()

def test_external_forward_filter_2_removed():
    assert FLT_EXT_2 not in _filter_ids()

def test_cfo_mailbox_no_full_scope_token():
    assert not _has_full_scope_token(MAILBOX)

def test_departed_priya_tokens_revoked():
    assert len(_tokens(DEL_DEPARTED_1)) == 0

def test_departed_marcus_tokens_revoked():
    assert len(_tokens(DEL_DEPARTED_2)) == 0

def test_moved_user_full_scope_token_revoked():
    assert not _has_full_scope_token(TOK_MOVED_BROAD)

def test_ticket_closed():
    t = _sn_ticket()
    assert t is not None
    s = str(t.get("state")).lower()
    assert s in ("6", "7") or "clos" in s or "resolv" in s

KEEP_DELEGATE_EA = "eva.poole@" + DOMAIN
KEEP_DELEGATE_CTRL = "ravi.menon@" + DOMAIN
KEEP_FORWARDING = "finance-archive@" + DOMAIN
KEEP_FILTER_1 = "flt-label-board"
KEEP_FILTER_2 = "flt-archive-news"
BACKUP_APP_DISPLAY = "Larkspur Backup Vault"
UNREL_1 = "hugo.wolf@" + DOMAIN
UNREL_2 = "sana.adler@" + DOMAIN
CIO = "aarav.kapoor@" + DOMAIN
DEPARTED = "priya.raman@" + DOMAIN
MOVED_1 = "owen.brooks@" + DOMAIN
MOVED_2 = "lena.frost@" + DOMAIN
REORG_CHANGE = "CHG0055120"

def test_control_ea_delegate_kept():
    assert KEEP_DELEGATE_EA in _delegate_emails()

def test_control_controller_delegate_kept():
    assert KEEP_DELEGATE_CTRL in _delegate_emails()

def test_control_cfo_primary_sendas_kept():
    assert MAILBOX in _sendas_emails()

def test_control_ea_sendas_kept():
    assert KEEP_DELEGATE_EA in _sendas_emails()

def test_control_internal_archive_forwarding_kept():
    assert KEEP_FORWARDING in _forwarding_emails()

def test_control_benign_filter_1_kept():
    assert KEEP_FILTER_1 in _filter_ids()

def test_control_benign_filter_2_kept():
    assert KEEP_FILTER_2 in _filter_ids()

def test_control_approved_backup_token_kept():
    titles = {str(t.get("displayText", "")) for t in _tokens(MAILBOX)}
    assert BACKUP_APP_DISPLAY in titles

def test_control_unrelated_user_1_token_kept():
    assert len(_tokens(UNREL_1)) >= 1

def test_control_unrelated_user_2_token_kept():
    assert len(_tokens(UNREL_2)) >= 1

def test_control_cio_token_kept():
    assert len(_tokens(CIO)) >= 1

def test_control_departed_account_unchanged():
    u = _gw_user(DEPARTED)
    assert u is not None and bool(u.get("suspended")) is True

def test_control_moved_user_1_active():
    u = _gw_user(MOVED_1)
    assert u is not None and bool(u.get("suspended")) is False

def test_control_moved_user_2_active():
    u = _gw_user(MOVED_2)
    assert u is not None and bool(u.get("suspended")) is False

def test_control_finance_group_intact():
    members = _as_list(_get(GW + "/admin/directory/v1/groups/finance-team@" + DOMAIN + "/members"), "members")
    assert KEEP_DELEGATE_CTRL in {str(m.get("email", "")).lower() for m in members}

def test_control_role_assignments_intact():
    ras = _as_list(_get(GW + "/admin/directory/v1/customer/my_customer/roleassignments"), "items")
    assert len(ras) >= 2

def test_control_reorg_change_untouched():
    rows = _as_list(_get(SN + "/api/now/table/change_request?sysparm_query="
                         + urllib.parse.quote("number=%s" % REORG_CHANGE)))
    assert rows and str(rows[0].get("state")) == "3"

def test_control_register_untouched():
    cis = _as_list(_get(SN + "/api/now/table/cmdb_ci"))
    assert any(str(c.get("u_mailbox", "")).lower() == MAILBOX for c in cis)
