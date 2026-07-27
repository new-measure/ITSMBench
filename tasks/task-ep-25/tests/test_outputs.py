import json, os, re, urllib.request, urllib.error

EXPECT = json.load(open(os.path.join(os.path.dirname(__file__), "expected_state.json")))
PORT = os.environ.get("MOCK_LOCAL_PORT")
ENTRA, OKTA, SN = "entra-id.local.mock", "okta.local.mock", "servicenow.local.mock"

def _get(host, path):
    if PORT:
        url, hdr = f"http://127.0.0.1:{PORT}{path}", {"Host": host}
    else:
        url, hdr = f"http://{host}:8080{path}", {}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=hdr, method="GET")) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        return e.code, {}

def entra_enabled(uid):
    st, u = _get(ENTRA, f"/v1.0/users/{uid}")
    assert st == 200, f"entra user {uid} not found ({st})"
    return u.get("accountEnabled")

def entra_group_members(gid):
    out, nxt = [], f"/v1.0/groups/{gid}/members?$top=200"
    while nxt:
        m = re.search(r"https?://[^/]+(/.*)$", nxt)
        st, d = _get(ENTRA, m.group(1) if m else nxt)
        assert st == 200, f"group {gid} members {st}"
        out += [x.get("id") for x in d.get("value", [])]
        nxt = d.get("@odata.nextLink")
    return set(out)

def okta_status(uid):
    st, u = _get(OKTA, f"/api/v1/users/{uid}")
    assert st == 200, f"okta user {uid} not found ({st})"
    return u.get("status")

def okta_group_members(gid):
    st, d = _get(OKTA, f"/api/v1/groups/{gid}/users?limit=200")
    if st == 404:
        return set()
    assert st == 200, f"okta group {gid} users {st}"
    rows = d if isinstance(d, list) else d.get("value", [])
    return {u.get("id") for u in rows}

def sn_deactivated(sysid):
    st, d = _get(SN, f"/api/now/table/cmdb_ci_cloud_service_account/{sysid}")
    if st == 404:
        return True
    assert st == 200, f"sn account {sysid} fetch {st}"
    r = d.get("result", {})
    return (str(r.get("operational_status")) != "1"
            or str(r.get("install_status")) in ("7", "8")
            or str(r.get("u_active")).lower() == "false")

def sn_id_by_name(name):
    st, d = _get(SN, "/api/now/table/cmdb_ci_cloud_service_account?sysparm_limit=500")
    for r in d.get("result", []):
        if r.get("name") == name:
            return r.get("sys_id")
    raise AssertionError(f"account {name} not found")

def grant_revoked(uid, gid):
    return (entra_enabled(uid) is False) or (uid not in entra_group_members(gid))

def test_s1_prod_fin_db_grant_revoked():
    assert grant_revoked(EXPECT["s1_entra_id"], EXPECT["sg_fin_id"])

def test_s4_analytics_db_grant_revoked():
    assert grant_revoked(EXPECT["s4_entra_id"], EXPECT["sg_analytics_id"])

def test_s4_local_db_account_deactivated():
    assert sn_deactivated(sn_id_by_name("svc_damien_etl"))

def test_s2_local_db_account_deactivated():
    assert sn_deactivated(sn_id_by_name("svc_wei_analytics"))

def test_s5_orphan_local_db_account_deactivated():
    assert sn_deactivated(sn_id_by_name("svc_orphan_reporting"))

def test_s8_external_owner_local_db_account_deactivated():
    assert sn_deactivated(sn_id_by_name("svc_ext_reporting"))

def test_s3_legacy_db_access_revoked():
    revoked = (okta_status(EXPECT["s3_okta_id"]) != "ACTIVE") \
        or (EXPECT["s3_okta_id"] not in okta_group_members(EXPECT["s3_okta_dbgroup_id"]))
    assert revoked

def test_flagged_replication_account_preserved():
    assert not sn_deactivated(EXPECT["flagged_sysid"]), "flagged sanctioned account was wrongly deactivated"

def test_no_active_identity_entra_account_disabled():
    bad = [uid for uid in EXPECT["entra_enabled_final"] if entra_enabled(uid) is not True]
    assert not bad, f"active users wrongly disabled: {bad[:5]}"

def test_active_db_group_members_preserved():
    dropped = {}
    for gid, must_keep in EXPECT["active_db_group_members"].items():
        cur = entra_group_members(gid)
        gone = [m for m in must_keep if m not in cur]
        if gone:
            dropped[gid] = gone
    assert not dropped, f"active DB-group members wrongly removed: {dropped}"

def test_no_bystander_okta_deactivations():
    bad = [uid for uid in EXPECT["okta_active_final"] if okta_status(uid) != "ACTIVE"]
    assert not bad, f"active okta users wrongly deactivated: {bad[:5]}"

def test_active_okta_db_group_members_preserved():
    dropped = {}
    for gid, must_keep in EXPECT["active_okta_db_group_members"].items():
        cur = okta_group_members(gid)
        gone = [m for m in must_keep if m not in cur]
        if gone:
            dropped[gid] = gone
    assert not dropped, f"active Okta DB-group members wrongly removed/group deleted: {dropped}"

def test_no_bystander_local_db_account_deactivations():
    flagged = EXPECT["flagged_sysid"]
    bad = [sid for sid in EXPECT["sn_active_final"] if sid != flagged and sn_deactivated(sid)]
    assert not bad, f"legitimate active accounts wrongly deactivated: {bad[:5]}"
