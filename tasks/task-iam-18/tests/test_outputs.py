import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request

ENTRA = "http://entra-id.local.mock:8080/v1.0"
GH = "http://github.local.mock:8080"
SLACK = "http://slack.local.mock:8080/api"
SN = "http://servicenow.local.mock:8080/api/now/table"
ORG = "halyard-cloud"

def _h(*p):
    return hashlib.md5("|".join(str(x) for x in p).encode()).hexdigest()

def EID(k):
    return "u" + _h("entra-user", k)[:16]

def EGID(k):
    return "g" + _h("entra-group", k)[:16]

def SUID(k):
    return "U" + _h("slack", k)[:8].upper()

def _get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    return json.loads(raw) if raw else None

def _as_list(obj, *keys):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in keys + ("value", "members", "result", "results", "values", "data", "rows"):
            if isinstance(obj.get(k), list):
                return obj[k]
    return []

def _entra_enabled(k):
    u = _get(ENTRA + "/users/" + EID(k))
    if not isinstance(u, dict):
        return None
    return u.get("accountEnabled")

def _egroup_member_ids(gk):
    return {str(m.get("id")) for m in _as_list(_get(ENTRA + "/groups/%s/members" % EGID(gk)))}

def _outside_logins():
    return {str(c.get("login")) for c in _as_list(_get(GH + "/orgs/%s/outside_collaborators?per_page=100" % ORG))}

def _org_member_logins():
    return {str(m.get("login")) for m in _as_list(_get(GH + "/orgs/%s/members?per_page=100" % ORG))}

def _slack_deactivated(k):
    u = _get(SLACK + "/users.info?user=" + SUID(k))
    if not isinstance(u, dict):
        return True
    inner = u.get("user")
    if not isinstance(inner, dict):
        return True
    return bool(inner.get("deleted"))

def _review_closed():
    r = [x for x in _as_list(_get(SN + "/sc_request")) if str(x.get("number")) == "REQ0090012"]
    if not r:
        return False
    rec = r[0]
    return str(rec.get("request_state", "")).lower().startswith("closed") or str(rec.get("state")) == "3"

def test_disable_elena_expired():
    assert _entra_enabled("elena") is False

def test_disable_bruno_orphaned():
    assert _entra_enabled("bruno") is False

def test_disable_nadia_decommissioned_partner():
    assert _entra_enabled("nadia") is False

def test_disable_ivan_decommissioned_partner():
    assert _entra_enabled("ivan") is False

def test_disable_priyaguest_duplicate():
    assert _entra_enabled("priyag") is False

def test_group_elena_removed_from_external():
    assert EID("elena") not in _egroup_member_ids("g-ext")

def test_group_bruno_removed_from_external():
    assert EID("bruno") not in _egroup_member_ids("g-ext")

def test_group_priyaguest_removed_from_external():
    assert EID("priyag") not in _egroup_member_ids("g-ext")

def test_group_nadia_removed_from_helios():
    assert EID("nadia") not in _egroup_member_ids("g-helios")

def test_group_ivan_removed_from_helios():
    assert EID("ivan") not in _egroup_member_ids("g-helios")

def test_github_elena_outside_removed():
    assert "elena-fischer" not in _outside_logins()

def test_github_bruno_outside_removed():
    assert "bruno-costa" not in _outside_logins()

def test_github_nadia_outside_removed():
    assert "nadia-petrova" not in _outside_logins()

def test_github_ivan_outside_removed():
    assert "ivan-sokolov" not in _outside_logins()

def test_github_priyaguest_outside_removed():
    assert "priya-raman" not in _outside_logins()

def test_slack_elena_deactivated():
    assert _slack_deactivated("elena")

def test_slack_bruno_deactivated():
    assert _slack_deactivated("bruno")

def test_slack_nadia_deactivated():
    assert _slack_deactivated("nadia")

def test_slack_priyaguest_deactivated():
    assert _slack_deactivated("priyag")

def test_review_request_closed():
    assert _review_closed()

def test_keep_marco_guest_enabled():
    assert _entra_enabled("marco") is True

def test_keep_sofia_guest_enabled():
    assert _entra_enabled("sofia") is True

def test_keep_marco_in_external_group():
    assert EID("marco") in _egroup_member_ids("g-ext")

def test_keep_marco_outside_collab_retained():
    assert "marco-bianchi" in _outside_logins()

def test_keep_marco_slack_active():
    assert not _slack_deactivated("marco")

def test_keep_sofia_slack_active():
    assert not _slack_deactivated("sofia")

def test_keep_employee_priya_enabled():
    assert _entra_enabled("priya") is True

def test_keep_employee_priya_org_member():
    assert "priya-raman" in _org_member_logins()

def test_keep_active_employees_enabled():
    for k in ("anna", "carlos", "eva", "tomas"):
        assert _entra_enabled(k) is True, k
